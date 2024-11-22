import hashlib
#import bencode
import mmap
''''
a Json-ish torrent format
but we only need the hash of the file, piece length (total),
                ip of the peer and the port of the peer
'''

def split_to_pieces(file_paths, piece_length=512 * 1024):
    """
    Split the files into fixed-sized pieces using mmap. 
    Handles residual pieces separately.

    :param file_paths: List of file paths to read.
    :param piece_length: Size of each piece in bytes (default: 512 KB).
    :return: Generator yielding file chunks.
    """
    for file_path in file_paths:
        with open(file_path, "rb") as file:
            # Memory-map the file for efficient access
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mmapped_file:
                offset = 0
                file_size = mmapped_file.size()

                # Process full-sized pieces
                while offset + piece_length <= file_size:
                    yield mmapped_file[offset:offset + piece_length]
                    offset += piece_length

                # Handle the residual piece
                if offset < file_size:
                    yield mmapped_file[offset:file_size]

def hash_pieces(pieces):
    return b"".join([hashlib.sha1(piece).digest() for piece in pieces])


def file_to_pieces(file_path):
    """
    Calculate the SHA-1 hash of each piece of the file.
    :param file_path: Path to the file to process.
    :return: SHA-1 hashes of the file pieces.
    """
    pieces = split_to_pieces([file_path])
    return hash_pieces(pieces)
class Torrent:
    def __init__(self, tracker_ip, piece_length , files, total_size):
        """
        Initialize the torrent class to mimic the .torrent structure.
        :param tracker_ip: Tracker URL.
        :param piece_length: Size of each piece in bytes.
        :param files: List of file metadata (name and size).
        :param total_size: Total size of all files.
        """
        self.tracker_ip = tracker_ip
     #   self.piece_length = piece_length
        self.files = files  # A list of {'name': file_name, 'length': file_size}
        self.total_size = total_size
        self.pieces = b""  # SHA-1 hashes of pieces (to be calculated)
    
            

    def calculate_pieces(self, file_paths):
        """
        Calculate the SHA-1 hashes for each piece of the files using mmap.
        :param file_paths: List of file paths to process.
        """
        pieces = split_to_pieces(file_paths)
        self.pieces = hash_pieces(pieces)

    def decode(self):
        """
        Build the dictionary structure for the .torrent file.
        :return: Dictionary containing torrent metadata.
        """
        info_dict = {
            "piece length": self.piece_length,
            "pieces": self.pieces,
        }

        if len(self.files) == 1:
            # Single-file torrent
            info_dict["name"] = self.files[0]["name"]
            info_dict["length"] = self.files[0]["length"]
        else:
            # Multi-file torrent
            info_dict["name"] = "multi_file_torrent"
            info_dict["files"] = [
                {"path": [file["name"]], "length": file["length"]}
                for file in self.files
            ]

        return {
            "announce": self.tracker_ip,
            "info": info_dict,
        }
    def encode(self, output_path):
        """
        Save the dictionary structure as a .torrent file.
        :param output_path: Path to save the .torrent file.
        """
        torrent_dict = self.decode()
        with open(output_path, "wb") as f:
            f.write(bencode.encode(torrent_dict))
            
   
        


             
    