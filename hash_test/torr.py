import pickle
import sys
import socket 
import json

class Torrent:
    def __init__(self):
        self.tracker_ip = None
        self.piece_length = None
        self.files = None
        self.total_size = None
        self.pieces = None


    def to_dict(self):
        return {
            "tracker_ip": self.tracker_ip,
            "piece_length": self.piece_length,
            "files": self.files,
            "total_size": self.total_size,
            "pieces": [piece.hex() for piece in self.pieces],
        }
    
    def pickle_serialized(self):
        return pickle.dumps(self.to_dict())
    
    def export_to_json(self, output_file):
        with open(output_file, "w") as f:
            json.dump(self.to_dict(), f, indent=4)
        print(f"Torrent data successfully exported to {output_file}")  