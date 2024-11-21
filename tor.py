import hashlib
import sys
import piece

piece_size = 512000


class torrent:
    def __init__(self, tracker_IP, piece_lngth, piece_cnt, file_num, tot_siz):
        self.tracker_ip = tracker_IP
        self.piece_length = piece_lngth
        self.file_num = file_num
        self.total_size = tot_siz
        self.piece_count = piece_cnt
        
    def get_tracker_ip(self):
        return self.tracker_ip
    def get_piece_lngth(self):
        return self.piece_length
    def get_piece_count(self):
        return self.piece_count
    
    def set_piece_count(self,cnt):
        self.piece_count = cnt
    
    def set_piece_lngth(self, length):
        self.piece_length = length
        
    def set_tracker(self, trackerip):
        self.tracker_ip = trackerip

    