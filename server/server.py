import socket
import threading
import os
import shutil
import random
import MyCrypto
import uuid
import time

# 服务端数据缓冲池
msg_buf = []
logIO_buf = [] # 储存有关用户进出的信息, 服务端并不需要知道有哪些用户，只需要转发进出信息
roll_buf = [] # 需要撤回的用户名列表
kick_buf = []
filename_buf = [] # 服务端本地有的文件
face_buf = [] # 储存待发送的用户名+表情包uuid名

groupLeader = None

msg_num = 0
logIO_num = 0
roll_num = 0
filename_num = 0
face_num = 0

msg_lock = threading.Lock()
logIO_lock = threading.Lock()
roll_lock = threading.Lock()
kick_lock = threading.Lock()
file_lock = threading.Lock()
face_lock = threading.Lock()

# 标志记号，规定为8位
END  =   '__END___'
DIV  =   '__DIV___'
MSG  =   '__MSG___'
USER =   '__USER__'
LOGIN =  '__LOGI__'
LOGOUT=  '__LOGO__'
INIT =   '__INIT__'
HIS  =   '__HIS___'
ROLL =   '__ROLL__'
NAME =   '__NAME__'
GRANT=   '__GRANT_'
KICK =   '__KICK__'
UPLOAD=  '__UPL___'
FNAME  = '__FNAME_'
DOWNLOAD='__DOWNL_'
FILE =   '__FILE__'
KEY  =   '__KEY___'
FACE =   '__FACE__'
mark_len = 8


class Server(object):
    '''针对每一个连接用户的服务类
    '''
    def __init__(self, conn, addr):
        # 建立连接
        self.__conn = conn
        self.__addr = addr
        self.__nickname = None

        # 群发相关
        with msg_lock:
            self.__next_msg = len(msg_buf)     # 每个用户的server都维护了下一次要发送的数据下标
        with logIO_lock:
            self.__next_logIO = len(logIO_buf) 
        with roll_lock:
            self.__next_roll = len(roll_buf)
        with file_lock:
            self.__next_file = len(filename_buf)
        with face_lock:
            self.__next_face = len(face_buf)

        # 单独发送相关变量
        self.require_history = False
        self.name_change = None
        self.become_leader = False
        self.require_files = []

        # 公开秘钥 和 共享秘钥
        self.__B = None
        self.__K = None
        self.__IV = None

        self.__receiver = threading.Thread(target=self.recv_proc, daemon=True)
        self.__sender = threading.Thread(target=self.send_proc, daemon=True)
        self.__receiver.start()
        self.__sender.start()        



    def __send_UTF8(self, text):
        try:
            self.__conn.sendall(MyCrypto.encrypt(text, self.__K, self.__IV))
        except Exception as err:
            self.__debugInfo(err)
            

    def __recvBytes(self):
        try:
            return MyCrypto.decrypt(self.__conn.recv(4096), self.__K, self.__IV)

        except Exception as err:
            self.__debugInfo(err)



    def __debugInfo(self, text):
        print(str(self.__addr) + ': ' + text)


    def __getFirstMember(self):
        user_list = []
        for logio in logIO_buf:
            if logio[0] == '+':
                user_list.append(logio[1:])
            elif logio[1:] in user_list:
                user_list.remove(logio[1:])
        
        return user_list[0] if len(user_list) != 0 else None


    def __changeDupName(self, name):
        user_list = []
        for logio in logIO_buf:
            if logio[0] == '+':
                user_list.append(logio[1:])
            elif logio[1:] in user_list:
                user_list.remove(logio[1:])
        
        if name in user_list:
            self.__nickname = self.name_change = name + '#'
            return name + '#'  # 若有重复用户名，则当前要增加的用户名变为 ...#

        self.__nickname = name # 记录本连接的用户名
        return name

    def __isInUserList(self, name):
        user_list = []
        for logio in logIO_buf:
            if logio[0] == '+':
                user_list.append(logio[1:])
            elif logio[1:] in user_list:
                user_list.remove(logio[1:])
        
        return name in user_list


    def __cleanBuf(self):
        '''清空缓存池
        '''
        global msg_buf, logIO_buf, roll_buf, kick_buf, filename_buf
        global groupLeader, msg_num, logIO_num, roll_num, filename_num
        shutil.rmtree('./files_buf')
        os.mkdir('./files_buf')
        shutil.rmtree('./face_buf')
        os.mkdir('./face_buf')
        msg_buf = []
        logIO_buf = []
        roll_buf = []
        kick_buf = []
        filename_buf = []
        groupLeader = None
        msg_num = 0
        logIO_num = 0
        roll_num = 0
        filename_num = 0
        print('NOTE: Clean ALL bufs done.')


    def update_files(self, mark, text):
        '''更新文件池 若不是文件请求，返回False; 是则返回True
        '''
        global file_lock, filename_buf, filename_num
        UPLOAD_bytes = bytes(UPLOAD, encoding='utf-8')
        DIV_bytes = bytes(DIV, encoding='utf-8')
        if mark == UPLOAD_bytes:
            temp = text.split(DIV_bytes, 1)
            filename = str(temp[0], encoding='utf-8')
            bytes_total = int(str(temp[1], encoding='utf-8'))

            filebytes = b''
            bytes_received = 0
            while(bytes_received < bytes_total): # 按照长度接收文件
                data = self.__conn.recv(bytes_total - bytes_received)
                bytes_received += len(data)
                filebytes += data

            with open('./files_buf/' + filename, 'wb') as f:
                f.write(filebytes)
            with file_lock:
                filename_buf.append(filename)
                filename_num += 1
            self.__debugInfo('File+ -> ' + filename)
            return True
        else:
            return False


    def update_buf(self, text):
        '''更新全局的数据缓冲池
        '''
        global msg_buf, msg_num, msg_lock
        global logIO_buf, logIO_num, logIO_lock
        mark = text[:mark_len]
        text = text[mark_len:]

        if self.update_files(mark, text):
            return
        else:
            mark = str(mark, encoding='utf-8')
            text = str(text, encoding='utf-8')
        
        # -----接收文件要用bytes格式处理，其他信息用str处理------

        if mark == LOGIN:
            with logIO_lock:
                name = self.__changeDupName(text)
                logIO_buf.append('+' + name)
                logIO_num += 1
            self.__debugInfo('User+ -> ' + text)

        elif mark == LOGOUT:
            with logIO_lock:
                logIO_buf.append('-' + text)
                logIO_num += 1
                if self.__nickname == text:   # 若群主退出，则移交群主权限
                    global groupLeader
                    groupLeader = None

            self.__debugInfo('User- -> ' + text)

        elif mark == MSG:
            with msg_lock:
                msg_buf.append(text)
                msg_num += 1
            self.__debugInfo(text)

        elif mark == FACE:
            global face_lock, face_buf, face_num
            temp = text.split(DIV, 1)
            user_name = temp[0]
            bytes_total = int(temp[1])

            facebytes = b''
            bytes_received = 0
            while(bytes_received < bytes_total): # 按照长度接收文件
                data = self.__conn.recv(bytes_total - bytes_received)
                bytes_received += len(data)
                facebytes += data

            face_name = str(uuid.uuid1())
            with open('./face_buf/' + face_name + '.jpg', 'wb') as f:
                f.write(facebytes)
            with face_lock:
                face_buf.append(user_name + DIV + face_name)
                face_num += 1
            self.__debugInfo('Face+ -> ' + face_name)

        elif mark == HIS:
            with msg_lock:
                self.require_history = True

        elif mark == ROLL:
            global roll_buf, roll_lock, roll_num
            with roll_lock:
                roll_buf.append(text)
                roll_num += 1
            with msg_lock:
                for i in range(len(msg_buf) - 1, -1, -1):
                    if msg_buf[i].split(DIV, 1)[0] == text: # 覆盖该用户的最后一条信息，若删除的话会有下标麻烦
                        msg_buf[i] = 'NOTE' + DIV + '[==This Message Has Been Withdrawed.==]'
                        break
            self.__debugInfo('RollBack -> ' + text)

        elif mark == KICK: # 强制退出
            with logIO_lock:
                if not self.__isInUserList(text): # 若踢的人不在列表中，则什么事都不会发生
                    return
                logIO_buf.append('-' + text)
                logIO_num += 1
            with kick_lock:
                kick_buf.append(text)
            self.__debugInfo('User- -> ' + text)

        elif mark == DOWNLOAD:
            self.require_files.append(text)
            self.__debugInfo('RequireFile: ' + text)


        return mark == LOGOUT

    def __recv_key(self):
        recv_text = ''
        while True:
            recv_text += str(self.__conn.recv(4096), encoding='utf-8')
            index = recv_text.find(END)
            if index != -1:
                break
        start = recv_text.find(KEY)
        text = recv_text[start + mark_len: index]
        gpA = text.split(DIV, 2)
        g, p, A = int(gpA[0]), int(gpA[1]), int(gpA[2])
        b = random.randint(0, p - 1)
        self.__B = pow(g, b, p)
        self.__K = pow(A, b, p)
        self.__IV = str(self.__K)[-16:]
        self.__K = str(self.__K)[:16]


    def recv_proc(self):
        '''【接收工作线程】接收所针对用户的信息请求
        '''
        # 首先进行密钥交换
        self.__recv_key()

        END_bytes = bytes(END, encoding='utf-8')
        recv_bytes = b''
        while True:
            recv_bytes += self.__recvBytes()
            try:
                index = recv_bytes.find(END_bytes)
                if index == -1:              # 针对不完整情况，当发送超长串时会出现
                    continue
                while index != -1:           # 针对合并情况, 当本用户发送密集短串时会出现合并
                    if self.update_buf(recv_bytes[:index]): # 判断是否为LOGOUT信号，如果是结束线程
                        return
                    recv_bytes = recv_bytes[index + mark_len:] # mark为字母，bytes长度不变
                    index = recv_bytes.find(END_bytes)
                recv_bytes = b''

                if not self.__sender.isAlive():
                    if(len(threading.enumerate()) == 2): # 当所有用户都退出时，清空缓存文件
                        self.__cleanBuf()
                    self.__conn.close()
                    return

            except Exception as err:
                print(f'[update_buf ERROR] {err}')



    def send_proc(self):
        '''【发送工作线程】将缓冲池的更新“群发”出去
        '''
        global msg_buf, msg_num, msg_lock, logIO_buf, logIO_num, logIO_lock
        global roll_buf, roll_num, roll_lock
        global groupLeader
        global kick_buf, kick_lock
        global filename_buf, filename_num, file_lock
        global face_buf, face_num, face_lock

        while self.__B is None: # 等待
            pass
        self.__conn.sendall(bytes(KEY + str(self.__B) + END, encoding='utf-8'))    # 发送公开秘钥

        try:
            if self.__next_logIO != 0 or self.__next_file != 0: # 发送用户初始化数据
                self.__send_UTF8(INIT + str(logIO_buf[:self.__next_logIO]) + DIV + str(filename_buf[:self.__next_file]) + END)
        except Exception as err:
            self.__debugInfo(f'[init_send ERROR] {err}')

        while True: # 注意存在合并发送....
            try:
                with logIO_lock:
                    while self.__next_logIO < logIO_num:
                        self.__send_UTF8(USER + logIO_buf[self.__next_logIO] + END)
                        self.__next_logIO += 1

                with msg_lock:
                    while self.__next_msg < msg_num:
                        self.__send_UTF8(MSG + msg_buf[self.__next_msg] + END)
                        self.__next_msg += 1

                with face_lock:
                    while self.__next_face < face_num:
                        temp = face_buf[self.__next_face]
                        face_name = temp.split(DIV, 1)[1]
                        with open('./face_buf/' + face_name + '.jpg', 'rb') as f:
                            filebytes = f.read()

                        self.__send_UTF8(FACE + temp + DIV + str(len(filebytes)) + END)
                        time.sleep(0.5)
                        self.__conn.sendall(filebytes)
                        self.__next_face += 1

                with roll_lock:
                    while self.__next_roll < roll_num:
                        self.__send_UTF8(ROLL + roll_buf[self.__next_roll] + END)
                        self.__next_roll += 1

                with file_lock:
                    while self.__next_file < filename_num:
                        self.__send_UTF8(FNAME + filename_buf[self.__next_file] + END)
                        self.__next_file += 1

                # ----------------上面为群发，下面为单发---------------
                with msg_lock:
                    if self.require_history is True:
                        seq = str(msg_buf[:self.__next_msg])
                        self.__send_UTF8(HIS + seq + END)
                    self.require_history = False

                with kick_lock:
                    if self.__nickname in kick_buf:
                        kick_buf.remove(self.__nickname)
                        self.__send_UTF8(KICK + END)
                        return

                if self.name_change is not None:
                    self.__send_UTF8(NAME + self.name_change + END)
                    self.name_change = None

                if groupLeader is None:
                    with logIO_lock:
                        groupLeader = self.__getFirstMember()

                if self.__nickname == groupLeader and self.become_leader is False:
                    self.__send_UTF8(GRANT + END)
                    self.become_leader = True

                if len(self.require_files) != 0:
                    with open('./files_buf/' + self.require_files[0], 'rb') as f:
                        filebytes = f.read()
                    
                    filename = self.require_files[0]
                    self.__send_UTF8(FILE + filename + DIV + str(len(filebytes)) + END)
                    self.__conn.sendall(filebytes)
                    self.require_files.pop(0)


                if not self.__receiver.isAlive():
                    if(len(threading.enumerate()) == 2):  # 当所有用户都退出时，清空缓存文件
                        self.__cleanBuf()
                    self.__conn.close()
                    return

            except Exception as err:
                self.__debugInfo(f'[sender ERROR] {err}')

        


if __name__ == '__main__':
    # 连接设置
    s = socket.socket()
    host = '127.0.0.1'
    port = 5555
    s.bind((host, port))
    s.listen(5)
    print('server ready.')

    # 等待连接
    while True:
        conn, addr = s.accept()
        print(f'new connection: addr={addr}')
        _ = Server(conn, addr)
