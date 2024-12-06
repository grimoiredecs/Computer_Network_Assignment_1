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
        self.available_torrents = {}  # {torrent_id: (info_hash, torrent_info_dict_with_peers)}
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
                    try:
                        with open(file_name, 'rb') as f:
                            file_data = f.read()
                        response = {'file_data': file_data}
                        conn.sendall(pickle.dumps(response))
                        print(f"Sent entire file {file_name} to {addr}")
                    except Exception as e:
                        response = {'error': f"Could not read file: {e}"}
                        conn.sendall(pickle.dumps(response))
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
                        # t_info includes 'peers' now
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

    def start_download_by_id(self, torrent_id):
        if torrent_id not in self.available_torrents:
            print("Invalid torrent ID.")
            return
        info_hash, t_info = self.available_torrents[torrent_id]
        # t_info includes 'peers': a list of (host, port) who have the file
        if not t_info['peers']:
            print("No peers have this file.")
            return
        # Let's pick the first peer for simplicity
        target_peer = t_info['peers'][0]
        self.simple_download(info_hash, t_info['name'], target_peer)

    def simple_download(self, info_hash, file_name, target_peer):
        peer_host, peer_port = target_peer
        # First do a handshake test
        if not self.handshake_with_peer(peer_host, peer_port):
            print("Handshake failed. Cannot download.")
            return
        # If handshake succeeded, request the file
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((peer_host, peer_port))
                # Already handshaked before? The instructions didn't specify a persistent connection.
                # We'll do the handshake test again or skip straight to request_file?
                # For simplicity, do a second handshake (or trust that peer is ready)
                # Actually, to follow instructions strictly: handshake again isn't stated.
                # Let's trust the peer. If we need a real scenario, we'd do handshake again.
                # Just send 'request_file' now.
                message = {'type': 'request_file', 'info_hash': info_hash}
                s.sendall(pickle.dumps(message))
                response_data = s.recv(50*1024*1024)  # large buffer, arbitrary
                if not response_data:
                    print("No data received from the peer.")
                    return
                response = pickle.loads(response_data)
                if 'file_data' in response:
                    file_data = response['file_data']
                    with open(f"downloaded_{file_name}", 'wb') as f:
                        f.write(file_data)
                    print(f"File {file_name} downloaded successfully.")
                else:
                    print(f"Error receiving file: {response.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"Failed to download from {peer_host}:{peer_port}: {e}")

    def handshake_with_peer(self, peer_host, peer_port):
        # Attempt a handshake test with the given peer
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
        # Announce to tracker that we have the file
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
                "pieces": [piece_hash],
                "piece_length": total_length
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
        # In this simplified version, no 'stopped' event logic is implemented.
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='P2P Peer')
    parser.add_argument('--host', default='127.0.0.1', help='Peer host')
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
            print("4. Download a file using a .torrent file (not needed if we just rely on tracker info)")
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
                # If needed, user can still provide a .torrent file to download from
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
