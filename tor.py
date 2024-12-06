import hashlib
#import bencode
import mmap
import json

PIECE_SIZE = 512*1024
class tor:
    def __init__(self, piece_num,peerid):
        self.piece_num = piece_num
        self.peerid = peerid
        self.piece_hashes = []
        self.piece_data = []
        self.piece_status = [0] * piece_num
    
    def load_torrent(self, torrent):
        # Load the torrent file
        with open(torrent, "rb") as f:
            self.torrent = json.load(f)
        
        # Get the piece hashes
        self.piece_hashes = self.torrent["info"]["pieces"]
        self.piece_num = len(self.piece_hashes) // 20
        self.piece_status = [0] * self.piece_num

        