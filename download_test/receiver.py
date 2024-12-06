import tqdm
import socket


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('localhost', 9000))
server.listen()

client, addr = server.accept()

file_name = client.recv(2048).decode()
print(file_name)
file_size = client.recv(2048).decode()
print(file_size)

file = open(file_name, "wb")

filebytes = b""

finsihed = False
progress = tqdm.tqdm(unit = "B", unit_scale = True, unit_divisor=1024, total = int(file_size))
while not done:
    data = client.recv(2048)
    if filebytes[-5:] == b"EOF":
        done = True
    else:
        filebytes += data
        progress.update(2048)
        

file.write(filebytes)

file.close()
server.close() 
