import pickle
import sys
import os
import socket
from tqdm import tqdm

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('localhost',9000))

file = open("metainfo.txt", "rb")
file_size= os.path.getsize("metainfo.txt")


client.send("received_metainfo.txt".encode())
client.send(str(file_size).encode())

data = file.read()
client.sendall(data)
client.send(b"EOF")

file.close()
client.close()

