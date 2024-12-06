import json
import mmap
import pickle
import sys
'''

class Torrent:
    def __init__(self, tracker_ip, piece_length, files, total_size, pieces):
        """
        Initialize the torrent structure.
        :param tracker_ip: Tracker URL or IP address.
        :param piece_length: Size of each piece in bytes.
        :param files: List of file metadata (name and size).
        :param total_size: Total size of all files.
        :param pieces: List of SHA-1 hashes of the pieces.
        """
        self.tracker_ip = tracker_ip
        self.piece_length = piece_length
        self.files = files  # List of {"name": filename, "length": file_length}
        self.total_size = total_size
        self.pieces = pieces  # List of hashes (or concatenated bytes)

    def to_dict(self):
        """
        Convert the torrent object to a dictionary suitable for JSON export.
        """
        return {
            "tracker_ip": self.tracker_ip,
            "piece_length": self.piece_length,
            "files": self.files,
            "total_size": self.total_size,
            "pieces": [piece.hex() for piece in self.pieces],  # Convert binary hashes to hex
        }

    def export_to_json_with_mmap(self, output_file):
        """
        Export the torrent structure to a JSON file using mmap.
        :param output_file: Path to the output JSON file.
        """
        # Convert the torrent data to JSON string
        json_data = json.dumps(self.to_dict(), indent=4)

        # Create and memory-map the output file
        with open(output_file, "wb") as f:
            # Preallocate space for the JSON data
            f.write(b'\x00' * len(json_data))
        
        with open(output_file, "r+b") as f:
            with mmap.mmap(f.fileno(), len(json_data), access=mmap.ACCESS_WRITE) as mmap_file:
                mmap_file.write(json_data.encode("utf-8"))
        print(f"Torrent data successfully exported to {output_file}")


# Example usage:
if __name__ == "__main__":
    # Simulated torrent data
    tracker_ip = "tracker.example.com"
    piece_length = 512 * 1024  # 512 KB
    files = [{"name": "main.txt", "length": 1024}, {"name": "image.jpg", "length": 2048}]
    total_size = sum(file["length"] for file in files)
    pieces = [b'\x12\x34\x56\x78' * 5, b'\x90\xab\xcd\xef' * 5]  # Simulated hashes

    torrent = Torrent(tracker_ip, piece_length, files, total_size, pieces)
    torrent.export_to_json_with_mmap("torrent_data_mmap.json")

'''

json.dump(['foo', {'bar': ('baz', None, 1.0, 2)}],sys.stdout)



