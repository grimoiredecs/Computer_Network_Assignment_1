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

class Peer:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
    
        self.peer_id = hashlib.sha1(str(random.random()).encode()).hexdigest()
    
    def upload(self, file_path, ip,port):
        torrent = self.generate_torrent(file_path)
        print('Torrent generated')
        client_socket = self.innit_connection(ip, port)
        print('Connection established')
        client_socket.send(torrent)
        print('Torrent sent')
        client_socket.close()
        print('Connection closed')
        