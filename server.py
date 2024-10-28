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

