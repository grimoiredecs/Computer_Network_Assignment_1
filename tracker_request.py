import re

import sys
import os
'''
torrent file structure
Dictionary:
    announce: tracker URL
    info: dictionary containing the following keys:
        name: name of the file
        piece length: number of bytes in each piece
        pieces: concatenation of each piece's SHA-1 hash
        length: length of the file in bytes
        files: list of dictionaries, each containing the following keys:
            length: length of the file in bytes
            
            
Note: the infohash is for check of the integrity of the file (checksum)
'''

