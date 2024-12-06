import socket
import threading
import pickle
import time
import argparse
import json
import hashlib
import os

class Peer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.shared_files = {}      # {info_hash: torrent}
        self.tracker_host = None
        self.tracker_port = None
        self.available_torrents = {}  # {torrent_id: (info_hash, {name, length, peers})}
        self.connected_trackers = set()

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
            if msg_type == 'handshake_test':
                # Respond with handshake_ack
                response = {'type': 'handshake_ack'}
                conn.sendall(pickle.dumps(response))
            elif msg_type == 'request_file':
                info_hash = message['info_hash']
                if info_hash in self.shared_files:
                    torrent_info = self.shared_files[info_hash]['info']
                    file_name = torrent_info['name']
                    # Send file_info first
                    file_size = torrent_info['length']
                    file_info_msg = {
                        'type': 'file_info',
                        'name': file_name,
                        'length': file_size
                    }
                    conn.sendall(pickle.dumps(file_info_msg))

                    # Then send the file in chunks
                    with open(file_name, 'rb') as f:
                        chunk_size = 1024*64
                        bytes_sent = 0
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            conn.sendall(chunk)
                            bytes_sent += len(chunk)
                    print(f"Sent entire file {file_name} to {addr}")
                    return #done
                else:
                    response = {'error': 'File not found here.'}
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
            print("Not connected to any tracker. Please connect first.")
            return
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.tracker_host, self.tracker_port))
                message = {'type': 'get_torrents'}
                s.sendall(pickle.dumps(message))
                response_data = s.recv(8192)
                response = pickle.loads(response_data)
                torrents = response.get('torrents', {})
                if torrents:
                    print("Available torrents:")
                    self.available_torrents = {}
                    for idx, (info_hash, t_info) in enumerate(torrents.items()):
                        # t_info includes 'peers': a list of (host, port)
                        self.available_torrents[idx] = (info_hash, t_info)
                        print(f"ID: {idx}")
                        print(f"  Info Hash: {info_hash}")
                        print(f"  Name: {t_info['name']}")
                        print(f"  Size: {t_info['length']} bytes")
                        print("  Peers holding this file:")
                        for p_host, p_port in t_info['peers']:
                            print(f"    {p_host}:{p_port}")
                        print()
                else:
                    print("No torrents available.")
        except Exception as e:
            print(f"Failed to get torrent list from tracker: {e}")
            self.connected_trackers.discard((self.tracker_host, self.tracker_port))
            self.tracker_host = None
            self.tracker_port = None

    def handshake_with_peer(self, peer_host, peer_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((peer_host, peer_port))
                message = {'type': 'handshake_test'}
                s.sendall(pickle.dumps(message))
                data = s.recv(4096)
                if not data:
                    print("No response from peer during handshake.")
                    return False
                response = pickle.loads(data)
                if response.get('type') == 'handshake_ack':
                    print("Handshake successful with the peer!")
                    return True
                else:
                    print("Peer did not acknowledge the handshake.")
                    return False
        except Exception as e:
            print(f"Failed to handshake with peer {peer_host}:{peer_port}: {e}")
            return False

    def download_from_peer(self, info_hash, file_name, peer_host, peer_port):
        # First handshake test
        if not self.handshake_with_peer(peer_host, peer_port):
            print("Handshake failed, cannot download.")
            return
        # Now request the file
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((peer_host, peer_port))
                # Directly send request_file
                req_msg = {'type': 'request_file', 'info_hash': info_hash}
                s.sendall(pickle.dumps(req_msg))

                # First receive the file_info message
                file_info_data = s.recv(4096)
                if not file_info_data:
                    print("No file info received from peer.")
                    return
                file_info = pickle.loads(file_info_data)
                if file_info.get('type') != 'file_info':
                    print("Did not receive file_info message.")
                    return
                remote_file_name = file_info['name']
                file_length = file_info['length']

                # Prepare to receive the file in chunks
                received = 0
                chunk_size = 1024*64
                # Open output file
                with open(f"downloaded_{remote_file_name}", 'wb') as f:
                    while received < file_length:
                        chunk = s.recv(min(chunk_size, file_length - received))
                        if not chunk:
                            print("Connection lost during file transfer.")
                            return
                        f.write(chunk)
                        received += len(chunk)
                        self.show_progress(received, file_length)
                print(f"\nFile {remote_file_name} downloaded successfully.")
        except Exception as e:
            print(f"Failed to download from {peer_host}:{peer_port}: {e}")

    def show_progress(self, downloaded, total):
        # Simple text progress bar
        percent = (downloaded / total) * 100
        bar_length = 50
        filled_length = int(bar_length * downloaded // total)
        bar = '=' * filled_length + '-' * (bar_length - filled_length)
        print(f"\rDownloading: |{bar}| {percent:.2f}% ({downloaded}/{total} bytes)", end='', flush=True)

    def start_download_by_id(self, torrent_id):
        if torrent_id not in self.available_torrents:
            print("Invalid torrent ID.")
            return
        info_hash, t_info = self.available_torrents[torrent_id]
        if not t_info['peers']:
            print("No peers have this file.")
            return
        # Let user choose a peer to download from
        print("Choose a peer to download from:")
        for i, p in enumerate(t_info['peers']):
            print(f"{i}. {p[0]}:{p[1]}")
        choice_str = input("Enter peer number: ").strip()
        if not choice_str.isdigit():
            print("Invalid choice.")
            return
        choice = int(choice_str)
        if choice < 0 or choice >= len(t_info['peers']):
            print("Invalid choice.")
            return
        peer_host, peer_port = t_info['peers'][choice]
        self.download_from_peer(info_hash, t_info['name'], peer_host, peer_port)

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
        with open(file_path, 'rb') as f:
            file_data = f.read()
        piece_hash = hashlib.sha1(file_data).hexdigest()
        total_length = len(file_data)
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
                "piece_length": total_length,
                "pieces": [piece_hash]
            },
            "comment": "Simple torrent file.",
            "created_by": "P2P System"
        }
        return torrent

    def announce_to_tracker(self, info_hash, event=None):
        if not self.tracker_host or not self.tracker_port:
            print("Not connected to any tracker. Please connect to a tracker first.")
            return []
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.tracker_host, self.tracker_port))
                message = {
                    'type': 'announce',
                    'info_hash': info_hash,
                    'host': self.host,
                    'port': self.port,
                    'event': event
                }
                if event == 'completed' and info_hash in self.shared_files:
                    torrent_info = self.shared_files[info_hash]['info']
                    message['torrent_info'] = torrent_info
                s.sendall(pickle.dumps(message))
                response_data = s.recv(4096)
                response = pickle.loads(response_data)
                peers = response.get('peers', [])
                self.connected_trackers.add((self.tracker_host, self.tracker_port))
                return peers
        except Exception as e:
            print(f"Failed to announce to tracker at {self.tracker_host}:{self.tracker_port}: {e}")
            self.connected_trackers.discard((self.tracker_host, self.tracker_port))
            self.tracker_host = None
            self.tracker_port = None
            return []

    def stop_all_transfers(self):
        # In this simplified version: no 'stopped' event logic implemented
        pass

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
            print("4. Download a file by ID (choose peer)")
            print("5. Handshake with a peer (test connectivity)")
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
                # If needed, implement start_download(torrent_file_path)
                torrent_file_path = input("Enter the torrent file path: ").strip()
                if os.path.isfile(torrent_file_path):
                    peer.start_download(torrent_file_path)
                else:
                    print("Torrent file not found.")
            elif choice == '4':
                if not peer.available_torrents:
                    print("No available torrents. Please get the list first.")
                    continue
                torrent_id_str = input("Enter the torrent ID to download: ").strip()
                if torrent_id_str.isdigit():
                    torrent_id = int(torrent_id_str)
                    peer.start_download_by_id(torrent_id)
                else:
                    print("Invalid torrent ID.")
            elif choice == '5':
                peer_host = input("Enter the peer's IP address: ").strip()
                peer_port = int(input("Enter the peer's port number: ").strip())
                peer.handshake_with_peer(peer_host, peer_port)
            elif choice == '6':
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
