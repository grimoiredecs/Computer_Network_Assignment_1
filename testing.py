import socket
import threading
import pickle
import time
import argparse
import json
import hashlib
import os
import random

class Peer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.active_downloads = {}  # {info_hash: download_info}
        self.shared_files = {}      # {info_hash: torrent_info}
        self.lock = threading.Lock()
        self.connected_trackers = set()  # Set of trackers the peer has connected to

    def start_server(self):
        threading.Thread(target=self._server, daemon=True).start()

    def _server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"Peer listening on {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn, addr):
        try:
            data = conn.recv(4096)
            message = pickle.loads(data)
            if message['type'] == 'request_piece':
                info_hash = message['info_hash']
                piece_index = message['index']
                # Check if we have the file
                if info_hash in self.shared_files:
                    torrent_info = self.shared_files[info_hash]
                    piece_length = torrent_info['info']['piece_length']
                    file_name = torrent_info['info']['name']
                    with open(file_name, 'rb') as f:
                        f.seek(piece_index * piece_length)
                        piece_data = f.read(piece_length)
                    response = {'data': piece_data}
                    conn.sendall(pickle.dumps(response))
                    print(f"Sent piece {piece_index} to {addr}")
                else:
                    print(f"Requested piece not found: {info_hash}")
            else:
                print(f"Unknown message type from {addr}")
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            conn.close()

    def announce_to_tracker(self, info_hash, tracker_host, tracker_port, event=None):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # Set a timeout for the connection
                s.connect((tracker_host, tracker_port))
                message = {
                    'type': 'announce',
                    'info_hash': info_hash,
                    'host': self.host,
                    'port': self.port,
                    'event': event  # Optional event parameter
                }
                s.sendall(pickle.dumps(message))
                response_data = s.recv(4096)
                response = pickle.loads(response_data)
                peers = response.get('peers', [])
                print(f"Received peers list for {info_hash}: {peers}")
                # Add the tracker to the connected trackers set
                self.connected_trackers.add((tracker_host, tracker_port))
                return peers
        except Exception as e:
            print(f"Failed to announce to tracker at {tracker_host}:{tracker_port}: {e}")
            return []

    def start_download(self, torrent_file_path):
        threading.Thread(target=self.download_file, args=(torrent_file_path,), daemon=True).start()

    def download_file(self, torrent_file_path):
        # Load the torrent file
        with open(torrent_file_path, 'r') as tf:
            torrent = json.load(tf)
        # Calculate info_hash
        info_str = json.dumps(torrent['info'], sort_keys=True)
        info_hash = hashlib.sha1(info_str.encode()).hexdigest()
        tracker_host = torrent['announce']['host']
        tracker_port = torrent['announce']['port']
        # Register the torrent in active downloads
        with self.lock:
            self.active_downloads[info_hash] = {
                'torrent': torrent,
                'pieces_downloaded': set(),
                'total_pieces': len(torrent['info']['pieces']),
                'file_data': {},  # {piece_index: piece_data}
                'peers': []
            }
        # Announce to tracker and get peers
        peers = self.announce_to_tracker(info_hash, tracker_host, tracker_port, event='started')
        with self.lock:
            self.active_downloads[info_hash]['peers'] = peers
        # Start downloading pieces
        total_pieces = len(torrent['info']['pieces'])
        piece_indices = list(range(total_pieces))
        random.shuffle(piece_indices)
        threads = []
        for piece_index in piece_indices:
            t = threading.Thread(target=self.download_piece, args=(info_hash, piece_index), daemon=True)
            t.start()
            threads.append(t)
        # Wait for all pieces to be downloaded
        for t in threads:
            t.join()
        # Assemble the file
        self.assemble_file(info_hash)
        # Announce completion to tracker
        self.announce_to_tracker(info_hash, tracker_host, tracker_port, event='completed')

    def download_piece(self, info_hash, piece_index):
        while True:
            with self.lock:
                if piece_index in self.active_downloads[info_hash]['pieces_downloaded']:
                    return  # Piece already downloaded
                peers = self.active_downloads[info_hash]['peers']
            for peer in peers:
                peer_host, peer_port = peer
                if (peer_host, peer_port) == (self.host, self.port):
                    continue  # Skip self
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(5)  # Set a timeout for the connection
                        s.connect((peer_host, peer_port))
                        message = {
                            'type': 'request_piece',
                            'info_hash': info_hash,
                            'index': piece_index
                        }
                        s.sendall(pickle.dumps(message))
                        response_data = s.recv(4096)
                        response = pickle.loads(response_data)
                        piece_data = response.get('data')
                        # Verify piece hash
                        torrent_info = self.active_downloads[info_hash]['torrent']
                        piece_hash = torrent_info['info']['pieces'][piece_index]
                        actual_hash = hashlib.sha1(piece_data).hexdigest()
                        if actual_hash == piece_hash:
                            print(f"Piece {piece_index} from {peer_host}:{peer_port} verified.")
                            with self.lock:
                                self.active_downloads[info_hash]['pieces_downloaded'].add(piece_index)
                                self.active_downloads[info_hash]['file_data'][piece_index] = piece_data
                            return
                        else:
                            print(f"Piece {piece_index} hash mismatch from {peer_host}:{peer_port}")
                except Exception as e:
                    print(f"Failed to download piece {piece_index} from {peer_host}:{peer_port}: {e}")
            time.sleep(1)  # Wait before retrying

    def assemble_file(self, info_hash):
        with self.lock:
            download_info = self.active_downloads[info_hash]
            total_pieces = download_info['total_pieces']
            if len(download_info['pieces_downloaded']) == total_pieces:
                torrent_info = download_info['torrent']
                file_name = torrent_info['info']['name']
                # Write the file data
                with open(f"downloaded_{file_name}", 'wb') as f:
                    for piece_index in range(total_pieces):
                        f.write(download_info['file_data'][piece_index])
                print(f"File {file_name} assembled successfully.")
                # Move the file to shared files
                self.shared_files[info_hash] = torrent_info
                # Remove from active downloads
                del self.active_downloads[info_hash]
            else:
                print(f"File assembly failed. Not all pieces were downloaded.")

    def share_file(self, file_path):
        # Create a torrent file and add to shared files
        torrent = self.create_torrent_file(file_path)
        info_str = json.dumps(torrent['info'], sort_keys=True)
        info_hash = hashlib.sha1(info_str.encode()).hexdigest()
        self.shared_files[info_hash] = torrent
        print(f"Sharing file {file_path} with info_hash {info_hash}")
        # Save the torrent file
        torrent_file_name = file_path + ".torrent"
        with open(torrent_file_name, 'w') as tf:
            json.dump(torrent, tf, indent=4)
        print(f"Torrent file created: {torrent_file_name}")
        # Announce to tracker
        tracker_host = torrent['announce']['host']
        tracker_port = torrent['announce']['port']
        self.announce_to_tracker(info_hash, tracker_host, tracker_port, event='completed')

    def create_torrent_file(self, file_path, piece_length=51200):
        # Read the file and calculate piece hashes
        pieces = []
        total_length = 0
        with open(file_path, 'rb') as f:
            while True:
                piece = f.read(piece_length)
                if not piece:
                    break
                piece_hash = hashlib.sha1(piece).hexdigest()
                pieces.append(piece_hash)
                total_length += len(piece)
        # Use tracker's IP and port (adjust as needed)
        tracker_host = '192.168.1.100'  # Replace with actual tracker IP
        tracker_port = 8000             # Replace with actual tracker port
        torrent = {
            "announce": {
                "host": tracker_host,
                "port": tracker_port
            },
            "info": {
                "name": os.path.basename(file_path),
                "length": total_length,
                "piece_length": piece_length,
                "pieces": pieces
            },
            "comment": "Simplified torrent file.",
            "created_by": "P2P System"
        }
        return torrent

    def stop_all_transfers(self):
        # Announce 'stopped' event for all shared files
        for info_hash in list(self.shared_files.keys()):
            torrent_info = self.shared_files[info_hash]
            tracker_host = torrent_info['announce']['host']
            tracker_port = torrent_info['announce']['port']
            if (tracker_host, tracker_port) in self.connected_trackers:
                self.announce_to_tracker(info_hash, tracker_host, tracker_port, event='stopped')
        # Announce 'stopped' event for all active downloads
        for info_hash in list(self.active_downloads.keys()):
            torrent_info = self.active_downloads[info_hash]['torrent']
            tracker_host = torrent_info['announce']['host']
            tracker_port = torrent_info['announce']['port']
            if (tracker_host, tracker_port) in self.connected_trackers:
                self.announce_to_tracker(info_hash, tracker_host, tracker_port, event='stopped')

if __name__ == "__main__":
    # Command-line arguments
    parser = argparse.ArgumentParser(description='P2P Peer')
    parser.add_argument('--host', default='127.0.0.1', help='Peer host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, required=True, help='Peer port')
    args = parser.parse_args()

    # Initialize peer with its host and port
    peer = Peer(host=args.host, port=args.port)
    peer.start_server()
    time.sleep(1)  # Give the server time to start

    # Interactive menu
    try:
        while True:
            print("\nOptions:")
            print("1. Share a file")
            print("2. Download a file")
            print("3. Quit")

            choice = input("Enter your choice: ").strip()
            if choice == '1':
                file_path = input("Enter the file path to share: ").strip()
                if os.path.isfile(file_path):
                    peer.share_file(file_path)
                else:
                    print("File not found.")
            elif choice == '2':
                torrent_file_path = input("Enter the torrent file path: ").strip()
                if os.path.isfile(torrent_file_path):
                    peer.start_download(torrent_file_path)
                else:
                    print("Torrent file not found.")
            elif choice == '3':
                print("Exiting.")
                break
            else:
                print("Invalid choice. Please try again.")
            time.sleep(0.1)  # Slight delay
    except KeyboardInterrupt:
        print("\nPeer shutting down.")
    finally:
        # Clean up: Announce to tracker that we're stopping
        if peer.connected_trackers:
            peer.stop_all_transfers()
        else:
            print("No trackers connected. Exiting immediately.")
