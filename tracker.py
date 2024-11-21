import re
import tor
import mmap
import socket
import random 
from threading import Thread

predefined_size = 8192
meta_file = "META"
def new_connection(addr, conn):
    print(addr)

def get_host_default_interface_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
       s.connect(('8.8.8.8',1))
       ip = s.getsockname()[0]
    except Exception:
       ip = '127.0.0.1'
    finally:
       s.close()
    return ip

def create_magnet(path_file, content):
    content_ut = content.encode("utf-8")
    size = len(content_ut)

    with open(path_file, "r+b") as f:
        with mmap.mmap(f.fileno(), size , access = mmap.ACCESS_WRITE) as mmm:
            mmm[:] = content_ut
            mmm.flush()
    return mmm






def server_program(host, port):
    serversocket = socket.socket()
    serversocket.bind((host, port))

    serversocket.listen(10)
    while True:
        addr, conn = serversocket.accept()
        nconn = Thread(target=new_connection, args=(addr, conn))
        nconn.start()


if __name__ == "__main__":
    print("hellow")
    