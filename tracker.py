import re
import tor
import socket
from threading import Thread
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


def server_program(host, port):
    serversocket = socket.socket()
    serversocket.bind((host, port))

    serversocket.listen(10)
    while True:
        addr, conn = serversocket.accept()
        nconn = Thread(target=new_connection, args=(addr, conn))
        nconn.start()

def continuous_write_to_file(file_path, data_queue):
    with open(file_path, 'a') as f:
        while True:
            data = data_queue.get()
            if data is None:  # Use None as a signal to stop the thread
                break
            f.write(data)
            f.flush() #cancel the data in buffer 

def perpetual_metainfo(data_queue):
    while True:
        data = input("Enter data to write to file (or 'exit' to stop): ")
        if data == 'exit':
            data_queue.put(None)  # Signal the thread to stop
            break
        data_queue.put(data + '\n')

if __main__ == "__main__":
    print("Hello World!")