from socket import*
# I was wrong about the import


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

server_socket.bind(('', server_port))#wrong syntax lmao
print('The server is ready to receive')

