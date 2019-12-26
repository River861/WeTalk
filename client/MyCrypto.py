from Crypto.Cipher import AES
from binascii import b2a_hex, a2b_hex
import random

# 如果text不足16位的倍数就用空格补足为16位
def add_to_16(text):
    add = (16 - (len(text.encode('utf-8')) % 16)) % 16
    text = text + ('\0' * add)
    return text.encode('utf-8')


# 加密函数
def encrypt(text, K, IV):
    key = K.encode('utf-8')
    mode = AES.MODE_CBC
    iv = IV.encode('utf-8')
    text = add_to_16(text)
    cryptos = AES.new(key, mode, iv)
    cipher_text = cryptos.encrypt(text)
    # 因为AES加密后的字符串不一定是ascii字符集的，输出保存可能存在问题，所以这里转为16进制字符串
    return b2a_hex(cipher_text)


# 解密后，去掉补足的空格用strip() 去掉
def decrypt(text, K, IV):
    key = K.encode('utf-8')
    iv = IV.encode('utf-8')
    mode = AES.MODE_CBC
    cryptos = AES.new(key, mode, iv)
    plain_text = cryptos.decrypt(a2b_hex(text))
    return plain_text.rstrip('\0'.encode('utf-8'))


if __name__ == '__main__':
    pass