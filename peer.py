import socket
import time
import hashlib
import bencode
import argparse
import tor
import mmap
from threading import Thread
import os
import random
import re

PIECE_SIZE = 512*1024

#class handshake:
   
def est_conn():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect()
            return client_socket.getsockname()[0]
class Peer:
    def __init__(self):
        conn = est_conn()
        self.ip , self.port = conn
        self.peer_id = hashlib.sha1(str(random.random()).encode()).hexdigest()
    
    def handshake(self, ip, port):
        handsk_msg = "Hello from {}:{}\n".format(self.ip, self.port)
        client_socket = self.innit_connection(ip, port)
        client_socket.send(handsk_msg.encode())
    
    def upload(self, file_path, ip,port):
        torrent = self.generate_torrent(file_path)
        print('Torrent generated')
        client_socket = self.innit_connection(ip, port)
        print('Connection established')
        client_socket.send(torrent)
        print('Torrent sent')
        client_socket.close()
        print('Connection closed')
    
    def send_file(self, file_path, ip, port):
        client_socket = self.innit_connection(ip, port)
        with open(file_path, "rb") as f:
            file_data = f.read()
            client_socket.send(file_data)
        client_socket.close()
    
    def connect_to_peer(self, ip, port):
        client_socket = self.innit_connection(ip, port)
        client_socket.close()
    
    def download(self,peer):
         
     