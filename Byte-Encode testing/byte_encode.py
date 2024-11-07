import sys

import re #regex
'''
 open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None)
'''
 
with open('Reference_NetApp.pdf', 'rb') as file: #raw byte reading
    raw_byte = file.read()  
    print(raw_byte)
