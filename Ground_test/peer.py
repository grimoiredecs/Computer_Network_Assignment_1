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
            if not data:
                conn.close()
                return
            message = pickle.loads(data)
            msg_type = message.get('type', None)

            if msg_type == 'request_piece':
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
            elif msg_type == 'handshake_test':
                # Respond to handshake test
                response = {'type': 'handshake_ack'}
                conn.sendall(pickle.dumps(response))
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
                        # Assuming 'seeders' and 'leechers' are available in torrent_info if previously implemented
                        if 'seeders' in torrent_info and 'leechers' in torrent_info:
                            print(f"  Size: {torrent_info['length']} bytes")
                            print(f"  Seeders: {torrent_info['seeders']}")
                            print(f"  Leechers: {torrent_info['leechers']}\n")
                        else:
                            # If not implemented in the tracker, just print length
                            print(f"  Size: {torrent_info['length']} bytes\n")
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
        # Download logic with pieces etc. (as previously implemented)
        # For brevity, let's assume it's unchanged.
        pass

    def start_download(self, torrent_file_path):
        # Download using a torrent file logic (unchanged)
        pass

    def download_file(self, torrent_file_path):
        # Actual piece-by-piece download logic (unchanged)
        pass

    def download_piece(self, info_hash, piece_index):
        # Actual piece downloading logic (unchanged)
        pass

    def assemble_file(self, info_hash):
        # File assembly logic (unchanged)
        pass

    def share_file(self, file_path):
        torrent = self.create_torrent_file(file_path)
        info_str = json.dumps(torrent['info'], sort_keys=True)
        info_hash = hashlib.sha1(info_str.encode()).hexdigest()
        self.shared_files[info_hash] = torrent
        print(f"Sharing file {file_path} with info_hash {info_hash}")
        torrent_file_name = file_path + ".torrent"
        with open(torrent_file_name, 'w') as tf:
            json.dump(torrent, tf, indent=4)
        print(f"Torrent file created: {torrent_file_name}")
        if not self.tracker_host or not self.tracker_port:
            tracker_host = input("Enter the tracker's IP address: ").strip()
            tracker_port = int(input("Enter the tracker's port number: ").strip())
            self.connect_to_tracker(tracker_host, tracker_port)
        # Announce to tracker
        self.announce_to_tracker(info_hash, event='completed')

    def create_torrent_file(self, file_path, piece_length=512*1024):
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
                if event == 'completed' and info_hash in self.shared_files:
                    torrent_info = self.shared_files[info_hash]['info']
                    message['torrent_info'] = torrent_info
                s.sendall(pickle.dumps(message))
                response_data = s.recv(4096)
                response = pickle.loads(response_data)
                peers = response.get('peers', [])
                # print(f"Received peers list for {info_hash}: {peers}")
                self.connected_trackers.add((self.tracker_host, self.tracker_port))
                return peers
        except Exception as e:
            print(f"Failed to announce to tracker at {self.tracker_host}:{self.tracker_port}: {e}")
            self.connected_trackers.discard((self.tracker_host, self.tracker_port))
            self.tracker_host = None
            self.tracker_port = None
            return []

    def stop_all_transfers(self):
        for info_hash in list(self.shared_files.keys()):
            if (self.tracker_host, self.tracker_port) in self.connected_trackers:
                self.announce_to_tracker(info_hash, event='stopped')
        for info_hash in list(self.active_downloads.keys()):
            if (self.tracker_host, self.tracker_port) in self.connected_trackers:
                self.announce_to_tracker(info_hash, event='stopped')

    def handshake_with_peer(self, peer_host, peer_port):
        # New method: Attempt to handshake with a given peer.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((peer_host, peer_port))
                # Send 'handshake_test'
                message = {'type': 'handshake_test'}
                s.sendall(pickle.dumps(message))
                # Wait for response
                data = s.recv(4096)
                if not data:
                    print("No response from peer.")
                    return
                response = pickle.loads(data)
                if response.get('type') == 'handshake_ack':
                    print("Handshake successful with the peer!")
                else:
                    print("Handshake failed or unexpected response.")
        except Exception as e:
            print(f"Failed to handshake with peer {peer_host}:{peer_port}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='P2P Peer')
    parser.add_argument('--host', default='127.0.0.1', help='Peer host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, required=True, help='Peer port')
    args = parser.parse_args()

    peer = Peer(host=args.host, port=args.port)
    peer.start_server()
    time.sleep(1)  # Give the server time to start

    try:
        while True:
            print("\nOptions:")
            print("1. Connect to a tracker")
            print("2. Get list of available torrents")
            print("3. Share a file")
            print("4. Download a file using torrent file")
            print("5. Download a file by ID")
            print("6. Handshake with a peer (test connectivity)")
            print("7. Quit")

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
                    print("No available torrents. Please get the list first.")
                    continue
                torrent_id_str = input("Enter the torrent ID to download: ").strip()
                if torrent_id_str.isdigit():
                    torrent_id = int(torrent_id_str)
                    peer.start_download_by_id(torrent_id)
                else:
                    print("Invalid torrent ID.")
            elif choice == '6':
                # Handshake with a peer
                peer_host = input("Enter the peer's IP address: ").strip()
                peer_port = int(input("Enter the peer's port number: ").strip())
                peer.handshake_with_peer(peer_host, peer_port)
            elif choice == '7':
                print("Exiting.")
                break
            else:
                print("Invalid choice. Please try again.")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nPeer shutting down.")
    finally:
        if peer.connected_trackers:
            peer.stop_all_transfers()
        else:
            print("No trackers connected. Exiting immediately.")
