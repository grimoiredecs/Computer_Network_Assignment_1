import socket
import time
import hashlib
import bencode
import argparse
import tor
import random
import mmap
from threading import Thread



class peer:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.peer_id = hashlib.sha1(str(random.random()).encode()).hexdigest()

    def innit_connection(self, host, port):
        print('Connecting to {}:{:d}'.format(host, port))
        client_socket = socket.socket()
        client_socket.connect((host, port))
        print('Connected to {}:{:d}'.format(host, port))
        return client_socket
    
    def generate_torrent(self, file_path):
        with open(file_path, "rb") as f:
            file_data = f.read()
            total_size = len(file_data)
            files = [{"name": file_path, "length": total_size}]
            torrent = tor.Torrent(self.ip + ":" + str(self.port), 1024*512, files, total_size)
            torrent.calculate_pieces([file_path])
            return torrent.encode()
    
        
    
        