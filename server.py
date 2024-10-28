from socket import*
from threading import thread

'''
identifier includes both IP address
and port numbers associated with
process on host.
abstraction for easy access later!
'''
def identify_conn(port,addr):
    return port, addr
'''
I'm pulling this code from our Kurose textbook
just simulating and experimenting purposes only
'''
server_port = 12000
server_socket = socket(AF_INET, SOCK_DGRAM)
serverSocket.bind(('', server_port))
print('The server is ready to receive')

