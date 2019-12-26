from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWebEngineWidgets import QWebEngineView
import sys

import socket
import threading
import time
import random
import os
import MyCrypto
import base64


# 客户端发送数据格式：
#       消息：MSG (用户名) DIV (消息内容) END
#       用户：   LOGIN (用户名) END
#               LOGOUT (用户名) END
#       历史：HIS END
#       撤回：ROLL (用户名) END
#       踢人：KICK (对象名) END
#       上传：UPLOAD (文件名) DIV (文件大小) END
#            利用文件大小，文件字节序列直接传输...
#       下载：DOWNLOAD (文件名) END
#       表情：FACE (用户名) DIV (图片大小) END
#            利用图片大小，图片字节序列直接传输...


# 服务端发送数据格式：
#       消息：MSG (用户名) DIV (消息内容) END
#       用户：   USER  (+/-用户名) END
#               INIT  (用户列表) DIV (文件名列表) END
#       历史：HIS (历史记录列表) END
#       撤回：ROLL (用户名) END
#       重名：NAME (新用户名) END
#       任免：GRANT END
#       被踢：KICK END
#   新文件信息：FNAME (文件名) END
#       文件：FILE (文件名) DIV (文件大小) END
#            利用文件大小，文件字节序列直接传输...
#       表情：FACE (用户名) DIV (图片大小) END
#            利用图片大小，图片字节序列直接传输...



# 全局变量
msg_buf = []
logIO_buf = []
history_buf = []
roll_buf = []
filename_buf = []
face_buf = [] # 待显示的用户名+表情图片base64编码

msg_num = 0
logIO_num = 0
roll_num = 0
filename_num = 0
face_num = 0

msg_lock = threading.Lock()
logIO_lock = threading.Lock()
history_lock = threading.Lock()
roll_lock = threading.Lock()
file_lock = threading.Lock()
face_lock = threading.Lock()

conn = None
nickname = None
newname = None
WeTalk = None
client = None
isKicked = False

# 群主权限
getLeaderPower = False
leaderPower = False

# 全局变量
login_widget = None
no_history = False
download_dir = None

# 大素数p 原根g 秘钥a 公开秘钥A
p = 1945555039024054273
g = 5
a = None
A = None
# 共享秘钥K
K = None
IV = None

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


class Client(object):
    '''接收线程 专门负责传输数据 和 数据处理
    '''
    def __init__(self):
        # 接收线程
        self.__receiver = threading.Thread(target=self.recv_proc, daemon=True)
        self.__receiver.start()


    def update_files(self, mark, text):
        '''若不是文件请求，返回False; 是则下载文件，返回True
        '''
        FILE_bytes = bytes(FILE, encoding='utf-8')
        DIV_bytes = bytes(DIV, encoding='utf-8')
        global download_dir, conn
        if mark == FILE_bytes:
            temp = text.split(DIV_bytes, 1)
            filename = str(temp[0], encoding='utf-8')
            bytes_total = int(str(temp[1], encoding='utf-8'))

            filebytes = b''
            bytes_received = 0
            while(bytes_received < bytes_total): # 按照长度接收文件
                data = conn.recv(bytes_total - bytes_received)
                bytes_received += len(data)
                filebytes += data

            with open(download_dir + filename, 'wb') as f:
                f.write(filebytes)

            print('FileDownload: ' + filename)
            return True
        else:
            return False


    def update_buf(self, text):        # 这个类什么都不知道，转存数据到本地就好了
        '''更新客户端本地数据缓冲池
        '''
        global msg_buf, msg_num, msg_lock, logIO_buf, logIO_num, logIO_lock
        global roll_buf, roll_num, roll_lock
        global filename_buf, filename_num, file_lock
        global face_buf, face_lock, face_num
        mark = text[:mark_len]
        text = text[mark_len:]

        if self.update_files(mark, text):
            return
        else:
            mark = str(mark, encoding='utf-8')
            text = str(text, encoding='utf-8')
        
        # -----接收文件要用bytes格式处理，其他信息用str处理------

        if mark == INIT:
            temp = text.split(DIV, 1)
            with logIO_lock:
                logIO_buf = eval(temp[0])
                logIO_num = len(logIO_buf)
                print(f'Init: {logIO_buf}')
            with file_lock:
                filename_buf = eval(temp[1])
                filename_num = len(filename_buf)
                print(f'Init: {filename_buf}')

        elif mark == USER:
            with logIO_lock:
                logIO_buf.append(text)
                logIO_num += 1
                print(text)


        elif mark == MSG: 
            with msg_lock:
                msg_buf.append(text)
                msg_num += 1
                print(text)

        elif mark == FACE:
            temp = text.split(DIV, 2)
            user_name = temp[0]
            face_name = temp[1]
            bytes_total = int(temp[2])

            facebytes = b''
            bytes_received = 0
            global conn
            while(bytes_received < bytes_total): # 按照长度接收文件
                data = conn.recv(bytes_total - bytes_received)
                bytes_received += len(data)
                facebytes += data

            s = base64.b64encode(facebytes).decode()
            
            with face_lock:
                face_buf.append(user_name + DIV + s)
                face_num += 1

        elif mark == HIS:
            global history_buf, history_lock
            if text == '[]':
                global no_history
                no_history = True
                return

            with history_lock:
                history_buf = eval(text)
            print(text)
        
        elif mark == ROLL:
            with roll_lock:
                roll_buf.append(text)
                roll_num += 1
                print(f'Roll: {text}')

        elif mark == FNAME:
            with file_lock:
                filename_buf.append(text)
                filename_num += 1
                print(f'newFile: {text}')


        elif mark == NAME:
            global newname
            newname = text # 强制改名

        elif mark == GRANT:
            global getLeaderPower
            getLeaderPower = True

        elif mark == KICK:
            global isKicked
            isKicked = True


    def __recv_key(self):
        global conn, K, IV, a, p
        recv_text = ''
        while True:
            recv_text += str(conn.recv(4096), encoding='utf-8')
            index = recv_text.find(END)
            if index != -1:
                break
        start = recv_text.find(KEY)
        text = recv_text[start + mark_len: index]
        B = int(text)
        K = pow(B, a, p)
        IV = str(K)[-16:]
        K = str(K)[:16]

    def recv_proc(self):
        '''【接收工作线程】 接收服务端群发的更新数据，以此更新本地数据
        '''
        # 首先进行密钥交换
        self.__recv_key()

        END_bytes = bytes(END, encoding='utf-8')
        recvBytes = b''
        while True:
            recvBytes += recv_bytes()
            try:
                index = recvBytes.find(END_bytes)
                if index == -1:              # 针对不完整情况
                    continue
                while index != -1:           # 针对合并情况
                    self.update_buf(recvBytes[:index])
                    recvBytes = recvBytes[index + mark_len:]
                    index = recvBytes.find(END_bytes)
                recvBytes = b''

            except Exception as err:
                print(f'[update_buf ERROR] {err}')


class UserListWidget(QWebEngineView):
    '''用户列表部件

    显示用户列表的地方 维护用户列表
    '''
    def __init__(self, father):
        super().__init__(father)
        with open('./css/UserWidget.html', 'r') as f:
            self.html_head = f.read()
        self.html_tail = '</html>'

        self.__user_buf = []   # 维护user_buf!
        self.__refresh()


    def add(self, name):
        if name not in self.__user_buf:
            self.__user_buf.append(name)
            self.__refresh()

    def delete(self, name):
        if name in self.__user_buf:
            self.__user_buf.remove(name)
            self.__refresh()

    def __refresh(self):
        user_html = ''
        for name in self.__user_buf:
            user_html += name + '\n<br>\n'

        self.setHtml(self.html_head + '<body>' + user_html + '</body>' + self.html_tail)




class MessageWidget(QWebEngineView):
    '''消息框部件

    显示用户们的消息的地方 维护本地消息序列
    '''
    def __init__(self, father):
        super().__init__(father)

        with open('./css/MsgWidget.html', 'r') as f:
            self.html_head = f.read()
        self.html_tail = '</body></html>'

        self.LBubble_head = ''' <div class="LBubble-container">
                                    <div class="LBubble">
                                        <p>
                                            <span class="msg">'''
        self.LBubble_tail = '''             </span>
                                            <span class="bottomLevel left"></span>
                                            <span class="topLevel"></span>
                                        </p>
                                        <br>
                                    </div>
                                </div>'''
        self.RBubble_head = ''' <div class="RBubble-container">
                                    <div class="RBubble">
                                        <p>
                                            <span class="msg">'''
        self.RBubble_tail = '''             </span>
                                            <span class="bottomLevel right"></span>
                                            <span class="topLevel"></span>
                                        </p>
                                        <br>
                                    </div>
                                </div>'''
        self.init_UI()
        
    def init_UI(self):
        self.__refresh()

    def addMine(self, msg, getRes=False):
        if getRes is False:
            self.html_head += self.RBubble_head + msg + self.RBubble_tail
            self.__refresh()
        else:
            name_html = '''<strong style="font-family:cursive,'Microsoft Yahei'">You: </strong>'''
            return self.RBubble_head + name_html + msg + self.RBubble_tail


    def addOthers(self, name, msg, getRes=False):
        name_html = '''<strong style="font-family:cursive,'Microsoft Yahei'">'''+ name +''': </strong>'''
        if getRes is False:
            self.html_head += self.LBubble_head + name_html + msg + self.LBubble_tail
            self.__refresh()
        else:
            return self.LBubble_head + name_html + msg + self.LBubble_tail

    def __refresh(self):
        self.setHtml(self.html_head + self.html_tail)

    def getHistoryHtml(self):
        '''渲染历史记录
        '''
        history_html = self.html_head
        global history_buf
        for seq in history_buf:
            text = seq.split(DIV, 1)
            if text[0] == nickname:
                history_html += self.addMine(text[1], getRes=True)
            else:
                history_html += self.addOthers(text[0], text[1], getRes=True)
        return history_html + self.html_tail

    def roll(self, name):
        if name != nickname: #从别人屏幕上撤回
            key_seq = '''<strong style="font-family:cursive,'Microsoft Yahei'">'''+ name +''': </strong>'''
            L_index = self.html_head.rfind(key_seq) - len(self.LBubble_head)
            R_index = L_index + self.html_head[L_index:].find(self.LBubble_tail) + len(self.LBubble_tail)
        
        else: # 从自己屏幕上撤回
            L_index = self.html_head.rfind(self.RBubble_head)
            R_index = self.html_head.rfind(self.RBubble_tail) + len(self.RBubble_tail)

        if L_index < 0: # 如果找不到
            return

        self.html_head = self.html_head[:L_index] + self.html_head[R_index:]
        self.__refresh()


class InputWidget(QWidget):
    '''输入部件

    用户输入消息的地方
    '''
    def __init__(self, parent):
        super().__init__(parent)
        self.init_UI()
        
    def init_UI(self):
        submitButton = QPushButton()
        submitButton.setStyleSheet( "QPushButton{width:25px; height:25px; border-image: url(./image/ok.ico)}"
                                    "QPushButton:hover{border-image: url(./image/ok_h.ico)}"
                                    "QPushButton:pressed{border-image: url(./image/ok_h.ico)}")
        submitButton.clicked.connect(self.submit)
        self.inputLine = QLineEdit()
        self.inputLine.returnPressed.connect(self.submit)

        hbox = QHBoxLayout()
        hbox.addWidget(self.inputLine)
        hbox.addSpacing(10)
        hbox.addWidget(submitButton)

        self.setLayout(hbox) 

    def submit(self):
        if self.inputLine.text() != '':
            send_UTF8(MSG + nickname + DIV + self.inputLine.text() + END)
        self.inputLine.clear()



class MainWidget(QWidget):
    '''主部件

    负责安排各部件的布局
    '''
    def __init__(self, father):
        super().__init__(father)
        self.msg_widget = MessageWidget(self)
        self.userlist_widget = UserListWidget(self)
        self.input_widget = InputWidget(self)

        self.initUI()


    def initUI(self):                 
        # 布局
        vbox = QVBoxLayout()
        vbox.addWidget(self.msg_widget, stretch=8)
        vbox.addWidget(self.input_widget, stretch=1)

        hbox = QHBoxLayout()
        hbox.addLayout(vbox, stretch=5)
        hbox.addSpacing(3)
        hbox.addWidget(self.userlist_widget, stretch=1)

        self.setLayout(hbox) 

        self.show() 



class HistoryWidget(QWebEngineView):

    def __init__(self):
        super().__init__()
        self.init_UI()

    def init_UI(self):
        self.setWindowTitle('History')
        self.setGeometry(450, 150, 420, 500)



class DownloadWidget(QWidget):
    '''下载窗口 选择下载的文件+选择下载位置
    '''
    def __init__(self):
        super().__init__()
        self.__filenameChosen = '<choose a file>'
        self.__cwd = os.getcwd()
        self.init_UI()

    def init_UI(self):
        self.setStyleSheet("DownloadWidget{background: #4a4a4a;}")
        self.combo = QComboBox(self)
        self.combo.addItem('<choose a file>')
        self.combo.activated[str].connect(self.onActivated)

        self.lineEdit = QLineEdit(self)

        browserBtn = QPushButton(self)
        browserBtn.setText('Browse')
        browserBtn.clicked.connect(self.setDownloadPath)

        startBtn = QPushButton(self)
        startBtn.setText('Download !')
        startBtn.clicked.connect(self.startDownload)

        # 布局
        box1 = QHBoxLayout()
        box1.addStretch(1)
        box1.addWidget(self.combo, stretch=3)
        box1.addStretch(1)

        box2 = QHBoxLayout()
        box2.addWidget(self.lineEdit, stretch=3)
        box2.addWidget(browserBtn,stretch=1)

        box3 = QHBoxLayout()
        box3.addStretch(1)
        box3.addWidget(startBtn)
        box3.addStretch(1)

        vbox = QVBoxLayout()
        vbox.addLayout(box1)
        vbox.addLayout(box2)
        vbox.addLayout(box3)

        self.setLayout(vbox) 


        self.setGeometry(500, 280, 300, 200)
        self.setWindowTitle('Download File')

    def onActivated(self, text):
        self.__filenameChosen = text

    def setDownloadPath(self):
        global download_dir
        download_dir = QFileDialog.getExistingDirectory(self,  
                                    "Download to...",  
                                    self.__cwd) + '/'
        self.lineEdit.setText(download_dir)


    def startDownload(self):
        global download_dir
        if self.__filenameChosen != '<choose a file>' and download_dir is not None:
            send_UTF8(DOWNLOAD + self.__filenameChosen + END)
            # 忽略等待
            QMessageBox.information(self, 'Success', "Download successfully.")
            self.close()
        else:
            QMessageBox.warning(self, 'warning', "You didn't choose a file or the path.")



class MainWin(QMainWindow):
    '''主界面

    负责实现菜单栏功能 以及 启动【界面刷新线程】
    '''
    def __init__(self):
        super().__init__()
        # 初始化主窗口
        self.main_widget = MainWidget(self)
        self.setCentralWidget(self.main_widget)
        # 初始化下载器
        self.downloader = DownloadWidget()
        self.__cwd = os.getcwd()

        with msg_lock:
            self.__next_msg = 0    # 每个用户都维护了下一次要在界面刷新的数据
        with logIO_lock:
            self.__next_logIO = 0
        with roll_lock:
            self.__next_roll = 0
        with file_lock:
            self.__next_file = 0
        with face_lock:
            self.__next_face = 0


        # 起refresher线程
        self.timer = QTimer()
        self.timer.timeout.connect(self.__refresh)
        self.timer.start(20)

        # 请求历史记录
        send_UTF8(HIS + END)
        self.history_widget = HistoryWidget()
        self.history_ok = False

        self.initUI()


    def initUI(self):               
        # 菜单栏
        # 退出
        exitAct = QAction(QIcon('./image/logout.ico'), 'QuickExit', self)
        exitAct.setShortcut('Ctrl+Q')
        exitAct.triggered.connect(qApp.quit)
        self.toolbar = self.addToolBar('QuickExit') # 避开询问 直接退出
        self.toolbar.addAction(exitAct)

        # 历史记录
        hisAct = QAction(QIcon('./image/history.ico'), 'History', self)
        hisAct.triggered.connect(self.checkHistory)
        self.toolbar = self.addToolBar('History')
        self.toolbar.addAction(hisAct)

        # 撤回消息
        rollAct = QAction(QIcon('./image/rollback.ico'), 'Rollback', self)
        rollAct.triggered.connect(self.rollBack)
        self.toolbar = self.addToolBar('Rollback')
        self.toolbar.addAction(rollAct)


        # 表情包
        faceAct = QAction(QIcon('./image/face.ico'), 'SendFace', self)
        faceAct.triggered.connect(self.sendFace)
        self.toolbar = self.addToolBar('SendFace')
        self.toolbar.addAction(faceAct)


        # 踢出群聊
        kickAct = QAction(QIcon('./image/kick.ico'), 'KickOut', self)
        kickAct.triggered.connect(self.kickOut)
        self.toolbar = self.addToolBar('KickOut')
        self.toolbar.addAction(kickAct)

        # 上传文件
        uploadAct = QAction(QIcon('./image/upload.ico'), 'Upload', self)
        uploadAct.triggered.connect(self.upLoad)
        self.toolbar = self.addToolBar('Upload')
        self.toolbar.addAction(uploadAct)

        # 下载文件
        downloadAct = QAction(QIcon('./image/download.ico'), 'Download', self)
        downloadAct.triggered.connect(self.downLoad)
        self.toolbar = self.addToolBar('Download')
        self.toolbar.addAction(downloadAct)
        
        # 基本信息
        self.setGeometry(330, 170, 700, 510)
        self.setWindowTitle('WeTalk')    
        self.setStyleSheet("QMainWindow {background: #4a4a4a;}")

        self.show()


    def checkHistory(self):
        '''打开历史消息框
        '''
        global no_history
        if no_history:
            QMessageBox.information(self, 'Info', f'No history.')
        if self.history_ok is True:
            self.history_widget.show()

    def rollBack(self):
        '''发送撤回请求
        '''
        send_UTF8(ROLL + nickname + END)

    def kickOut(self):
        '''踢人
        '''
        global leaderPower
        if not leaderPower:
            QMessageBox.warning(self, 'warning', f'You are not the Group Leader.')
            return
        else:
            badGuy, ok = QInputDialog.getText(self, 'Kick out someone', 
                'Enter his name:')
            if ok:
                send_UTF8(KICK + badGuy + END)

    def upLoad(self):
        filename, _ = QFileDialog.getOpenFileName(self,  
                                    "选取文件",  
                                    self.__cwd, # 起始路径 
                                    "All Files (*);;Text Files (*.txt)")   # 设置文件扩展名过滤,用双分号间隔

        if filename == "":
            print("取消选择")
            return
        
        with open(filename, 'rb') as f:
            filebytes = f.read()
        
        if sendFile(os.path.basename(filename), filebytes):
            # 忽略等待
            QMessageBox.information(self, 'Success', f'Upload successfully.')
        else:
            QMessageBox.critical(self, 'error', f'Upload fail.')

    def sendFace(self):
        filename, _ = QFileDialog.getOpenFileName(self,  
                                    "选取文件",  
                                    self.__cwd + "/myFace", # 起始路径 
                                    " IMG Files (*.jpg *.JPG)")   # 设置文件扩展名过滤,用双分号间隔

        if filename == "":
            print("取消选择")
            return
        
        with open(filename, 'rb') as f:
            filebytes = f.read()
        
        sendFace(filebytes)


    def downLoad(self):
        self.downloader.show()


    def __refresh(self):
        '''
        refresh线程（由Qtimer维护）
        '''
        global msg_buf, msg_num, msg_lock, logIO_buf, logIO_num, logIO_lock
        global history_buf, history_lock
        global newname, nickname
        global getLeaderPower, leaderPower, isKicked
        global roll_buf, roll_num, roll_lock
        global filename_buf, filename_num, file_lock
        global face_buf, face_lock, face_num
        try:
            with logIO_lock:
                while self.__next_logIO < logIO_num:
                    opera = logIO_buf[self.__next_logIO]
                    if opera[0] == '+':
                        self.main_widget.userlist_widget.add(opera[1:])
                    elif opera[0] == '-':
                        self.main_widget.userlist_widget.delete(opera[1:])
                    self.__next_logIO += 1

            with msg_lock:
                while self.__next_msg < msg_num:
                    text = msg_buf[self.__next_msg].split(DIV, 1)
                    if text[0] == nickname:
                        self.main_widget.msg_widget.addMine(text[1])
                    else:
                        self.main_widget.msg_widget.addOthers(text[0], text[1])
                    self.__next_msg += 1

            with face_lock:
                while self.__next_face < face_num:
                    text = face_buf[self.__next_face].split(DIV, 1)
                    s = text[1]

                    if text[0] == nickname:
                        img_html = f'<img src="data:image/jpeg;base64,{s}" width="200" alt="图像加载失败...">'
                        self.main_widget.msg_widget.addMine(img_html)
                    else:
                        img_html = f'<br><img style="margin-top: 5px;" src="data:image/jpeg;base64,{s}" width="200" alt="图像加载失败...">'
                        self.main_widget.msg_widget.addOthers(text[0], img_html)
                    self.__next_face += 1

            with roll_lock:
                while self.__next_roll < roll_num:
                    self.main_widget.msg_widget.roll(roll_buf[self.__next_roll])
                    self.__next_roll += 1

            with file_lock:
                while self.__next_file < filename_num:
                    self.downloader.combo.addItem(filename_buf[self.__next_file])
                    self.__next_file += 1

            # -----------------上面为针对群发的刷新，下面为针对单发的刷新-------------------

            with history_lock:
                if self.history_ok is False and len(history_buf) != 0:
                    html = self.main_widget.msg_widget.getHistoryHtml()
                    self.history_widget.setHtml(html)
                    self.history_ok = True
            
            if newname is not None:
                nickname = newname
                QMessageBox.information(self, 'Info', f'To avoid duplication, your nickname have changed to [{newname}]')
                newname = None

            if getLeaderPower is True:
                leaderPower = True
                QMessageBox.information(self, 'Info', f'You become the [Group Leader].')
                getLeaderPower = False

            if isKicked is True:
                QMessageBox.critical(self, 'Announce', f'You have been kicked out by the Group Leader.')
                qApp.quit()



        except Exception as err:
            print(f'[timer ERROR] {err}')

    def closeEvent(self, event):
        reply = QMessageBox.question(self,
                                    'Exit',
                                    "Are you sure to quit？",
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()



class LoginWidget(QWidget):
    '''登录界面

    负责确定用户名、建立连接、搭建主界面和 启动【消息接收线程】
    '''
    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.init_UI()
        
    def init_UI(self):
    
        self.setWindowTitle('Enter WeTalk')
        self.setGeometry(550, 350, 300, 150)
        self.setStyleSheet("LoginWidget{background: #4a4a4a;}")

        self.loginLine = QLineEdit(self)
        self.loginLine.setPlaceholderText('Enter your nickname')
        self.loginLine.setGeometry(30, 35, 240, 30)
        
        self.loginBtn = QPushButton('Go', self)
        self.loginBtn.move(105, 95)
        self.loginBtn.clicked.connect(self.__setUp)
        self.loginLine.returnPressed.connect(self.__setUp)

        self.show()
    
    def __setUp(self):
        global nickname, conn, WeTalk, client, g, p, a, A, K
        if self.loginLine.text() != '':
            self.close()
            # 填名字
            nickname = self.loginLine.text()
            # 建立连接
            conn = socket.socket()
            conn.connect((self.host, self.port))
            # 开始交换秘钥
            a = random.randint(0, p - 1)
            A = pow(g, a, p)
            conn.sendall(bytes(KEY + str(g) + DIV + str(p) + DIV + str(A) + END, encoding='utf-8')) # 发送 g, p, A给服务端
            # 起receiver线程
            client = Client()
            while K is None: # 等待秘钥接收
                pass
            # 起界面
            WeTalk = MainWin()
            # 我来了
            send_UTF8(LOGIN + nickname + END)



def send_UTF8(text):
    global conn, K, IV
    try:
        conn.sendall(MyCrypto.encrypt(text, K, IV))
    except Exception as err:
        print(f'[send ERROR] {err}')



def sendFile(filename, filebytes):
    global conn, K, IV
    try:
        conn.sendall(MyCrypto.encrypt(UPLOAD + filename + DIV + str(len(filebytes)) + END, K, IV)) # 先发文件名和大小
        conn.sendall(filebytes)
        return True
    except Exception as err:
        print(f'[sendFile ERROR] {err}')
        return False


def sendFace(filebytes):
    global conn, K, IV, nickname
    try:
        conn.sendall(MyCrypto.encrypt(FACE + nickname + DIV + str(len(filebytes)) + END, K, IV)) # 先发用户名和图片大小
        conn.sendall(filebytes)
        return True
    except Exception as err:
        print(f'[sendFace ERROR] {err}')
        return False


def recv_bytes():
    global conn, K, IV
    try:
        text = conn.recv(4096)
        print(f'Recving Cipher: {text}')
        return MyCrypto.decrypt(text, K, IV)
    except Exception as err:
        print(f'[recv_file ERROR] {err}')



if __name__ == '__main__':
    app = QApplication(sys.argv)
    host = '127.0.0.1'
    port = 5555

    # 登录界面
    login_widget = LoginWidget(host, port)

    app.exec_()
    if nickname is not None:
        print('LOGOUT.')
        # 我走了
        send_UTF8(LOGOUT + nickname + END)
        conn.close()
