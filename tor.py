import hashlib
import sys
piece_size = 512000

class torrent:
    def __init__(self, tracker_IP, piece_lngth, piece_cnt):
        self.tracker_ip = tracker_IP
        self.piece_length = piece_lngth
        self.piece_count = piece_cnt
        