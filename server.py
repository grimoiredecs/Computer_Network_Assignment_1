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
'''
Notes abbout the parameters:
AF_INET - address family
A pair (host, port) is used for the AF_INET address family, 
where host is a string representing either a hostname in internet domain notation 
like 'daring.cwi.nl' or an IPv4 address like '100.50.200.5', and port is an integer.

SOCK_DGRAM
- UDP protocol type!

'''
'''
OSError: [WinError 10022] An invalid argument was supplied
'''
#how to make the process lives until a termination is entered??


print('The server is ready to receive')

