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
        self.tracker_host = None
        self.tracker_port = None
        self.available_torrents = {}  # {torrent_id: (info_hash, torrent_info)}

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

    def connect_to_tracker(self, tracker_host, tracker_port):
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        print(f"Connected to tracker at {self.tracker_host}:{self.tracker_port}")

    def get_torrent_list(self):
        if not self.tracker_host or not self.tracker_port:
            print("Not connected to any tracker. Please connect to a tracker first.")
            return
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.tracker_host, self.tracker_port))
                message = {
                    'type': 'get_torrents'
                }
                s.sendall(pickle.dumps(message))
                response_data = s.recv(8192)
                response = pickle.loads(response_data)
                torrents = response.get('torrents', {})
                if torrents:
                    print("Available torrents:")
                    self.available_torrents = {}  # Reset available torrents
                    for idx, (info_hash, torrent_info) in enumerate(torrents.items()):
                        self.available_torrents[idx] = (info_hash, torrent_info)
                        print(f"ID: {idx}")
                        print(f"  Info Hash: {info_hash}")
                        print(f"  Name: {torrent_info['name']}")
                        print(f"  Size: {torrent_info['length']} bytes")
                        print(f"  Seeders: {torrent_info['seeders']}")
                        print(f"  Leechers: {torrent_info['leechers']}\n")
                else:
                    print("No torrents available.")
        except Exception as e:
            print(f"Failed to get torrent list from tracker: {e}")
            # Remove the tracker from connected_trackers
            self.connected_trackers.discard((self.tracker_host, self.tracker_port))
            # Reset tracker_host and tracker_port
            self.tracker_host = None
            self.tracker_port = None

    def start_download_by_id(self, torrent_id):
        if not self.tracker_host or not self.tracker_port:
            print("Not connected to any tracker. Please connect to a tracker first.")
            return
        try:
            # Request the torrent info from the tracker
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.tracker_host, self.tracker_port))
                message = {
                    'type': 'get_torrent_info',
                    'torrent_id': torrent_id
                }
                s.sendall(pickle.dumps(message))
                response_data = s.recv(8192)
                response = pickle.loads(response_data)
                if 'error' in response:
                    print(f"Error: {response['error']}")
                    return
                info_hash = response['info_hash']
                info = response['info']
                # Create the torrent dictionary
                torrent = {
                    'announce': {
                        'host': self.tracker_host,
                        'port': self.tracker_port
                    },
                    'info': info
                }
                # Calculate the info_hash
                info_str = json.dumps(info, sort_keys=True)
                calculated_info_hash = hashlib.sha1(info_str.encode()).hexdigest()
                if info_hash != calculated_info_hash:
                    print("Error: Info hash mismatch.")
                    return
                # Proceed to download using the torrent info
                self.start_download_from_info(info_hash, torrent)
        except Exception as e:
            print(f"Failed to get torrent info from tracker: {e}")
            # Remove the tracker from connected_trackers
            self.connected_trackers.discard((self.tracker_host, self.tracker_port))
            # Reset tracker_host and tracker_port
            self.tracker_host = None
            self.tracker_port = None

    def start_download_from_info(self, info_hash, torrent):
        threading.Thread(target=self.download_file_from_info, args=(info_hash, torrent), daemon=True).start()
    def download_file_from_info(self, info_hash, torrent):
        # Set tracker information
        if not self.tracker_host or not self.tracker_port:
            self.tracker_host = torrent['announce']['host']
            self.tracker_port = torrent['announce']['port']
            print(f"Using tracker from torrent info: {self.tracker_host}:{self.tracker_port}")
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
        peers = self.announce_to_tracker(info_hash, event='started')
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
        self.announce_to_tracker(info_hash, event='completed')
    def start_download(self, torrent_file_path):
        threading.Thread(target=self.download_file, args=(torrent_file_path,), daemon=True).start()
    def download_file(self, torrent_file_path):
        # Load the torrent file
        with open(torrent_file_path, 'r') as tf:
            torrent = json.load(tf)
        # Calculate info_hash
        info_str = json.dumps(torrent['info'], sort_keys=True)
        info_hash = hashlib.sha1(info_str.encode()).hexdigest()
        # Set tracker information from the torrent file if not already connected
        if not self.tracker_host or not self.tracker_port:
            self.tracker_host = torrent['announce']['host']
            self.tracker_port = torrent['announce']['port']
            print(f"Using tracker from torrent file: {self.tracker_host}:{self.tracker_port}")
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
        peers = self.announce_to_tracker(info_hash, event='started')
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
        self.announce_to_tracker(info_hash, event='completed')

    def download_piece(self, info_hash, piece_index):
        while True:
            with self.lock:
                if info_hash not in self.active_downloads:
                    return  # Download has been cancelled or completed
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
            download_info = self.active_downloads.get(info_hash)
            if not download_info:
                print(f"Download info not found for {info_hash}")
                return
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
        # Set tracker information from the torrent file if not already connected
        if not self.tracker_host or not self.tracker_port:
            self.tracker_host = torrent['announce']['host']
            self.tracker_port = torrent['announce']['port']
            print(f"Using tracker from torrent file: {self.tracker_host}:{self.tracker_port}")
        # Announce to tracker
        self.announce_to_tracker(info_hash, event='completed')

    def create_torrent_file(self, file_path, piece_length=512*1024):
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
        # If tracker_host and tracker_port are set, use them; else, ask the user
        if not self.tracker_host or not self.tracker_port:
            tracker_host = input("Enter the tracker's IP address: ").strip()
            tracker_port = int(input("Enter the tracker's port number: ").strip())
            self.connect_to_tracker(tracker_host, tracker_port)
        else:
            tracker_host = self.tracker_host
            tracker_port = self.tracker_port
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

    def announce_to_tracker(self, info_hash, event=None):
        if not self.tracker_host or not self.tracker_port:
            print("Not connected to any tracker. Please connect to a tracker first.")
            return []
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # Set a timeout for the connection
                s.connect((self.tracker_host, self.tracker_port))
                message = {
                    'type': 'announce',
                    'info_hash': info_hash,
                    'host': self.host,
                    'port': self.port,
                    'event': event  # Optional event parameter
                }
                # Include torrent_info when sharing a file or completing a download
                if event in ('completed',):
                    if info_hash in self.shared_files:
                        torrent_info = self.shared_files[info_hash]['info']
                        message['torrent_info'] = torrent_info  # Send full 'info' dictionary
                s.sendall(pickle.dumps(message))
                response_data = s.recv(4096)
                response = pickle.loads(response_data)
                peers = response.get('peers', [])
                print(f"Received peers list for {info_hash}: {peers}")
                # Add the tracker to the connected trackers set
                self.connected_trackers.add((self.tracker_host, self.tracker_port))
                return peers
        except Exception as e:
            print(f"Failed to announce to tracker at {self.tracker_host}:{self.tracker_port}: {e}")
            # Remove the tracker from connected_trackers
            self.connected_trackers.discard((self.tracker_host, self.tracker_port))
            # Reset tracker_host and tracker_port
            self.tracker_host = None
            self.tracker_port = None
            return []

    def stop_all_transfers(self):
        # Announce 'stopped' event for all shared files
        for info_hash in list(self.shared_files.keys()):
            if (self.tracker_host, self.tracker_port) in self.connected_trackers:
                self.announce_to_tracker(info_hash, event='stopped')
        # Announce 'stopped' event for all active downloads
        for info_hash in list(self.active_downloads.keys()):
            if (self.tracker_host, self.tracker_port) in self.connected_trackers:
                self.announce_to_tracker(info_hash, event='stopped')

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
            print("1. Connect to a tracker")
            print("2. Get list of available torrents")
            print("3. Share a file")
            print("4. Download a file using torrent file")
            print("5. Download a file by ID")
            print("6. Quit")

            choice = input("Enter your choice: ").strip()
            if choice == '1':
                tracker_host = input("Enter the tracker's IP address: ").strip()
                tracker_port = int(input("Enter the tracker's port number: ").strip())
                peer.connect_to_tracker(tracker_host, tracker_port)
            elif choice == '2':
                peer.get_torrent_list()
            elif choice == '3':
                file_path = input("Enter the file path to share: ").strip()
                if os.path.isfile(file_path):
                    peer.share_file(file_path)
                else:
                    print("File not found.")
            elif choice == '4':
                torrent_file_path = input("Enter the torrent file path: ").strip()
                if os.path.isfile(torrent_file_path):
                    peer.start_download(torrent_file_path)
                else:
                    print("Torrent file not found.")
            elif choice == '5':
                if not peer.available_torrents:
                    print("No available torrents. Please get the list of available torrents first.")
                    continue
                torrent_id_str = input("Enter the torrent ID to download: ").strip()
                if torrent_id_str.isdigit():
                    torrent_id = int(torrent_id_str)
                    if torrent_id in peer.available_torrents:
                        peer.start_download_by_id(torrent_id)
                    else:
                        print("Invalid torrent ID.")
                else:
                    print("Invalid torrent ID.")
            elif choice == '6':
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
