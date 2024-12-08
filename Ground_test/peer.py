import pickle
import struct

def send_msg(conn, obj):
    data = pickle.dumps(obj)
    length_prefix = struct.pack('!I', len(data))
    conn.sendall(length_prefix + data)

def recv_all(conn, length):
    chunks = []
    bytes_recd = 0
    while bytes_recd < length:
        chunk = conn.recv(length - bytes_recd)
        if not chunk:
            return None
        chunks.append(chunk)
        bytes_recd += len(chunk)
    return b''.join(chunks)

def recv_msg(conn):
    # Read length prefix
    length_prefix = recv_all(conn, 4)
    if not length_prefix:
        return None
    msg_length = struct.unpack('!I', length_prefix)[0]
    data = recv_all(conn, msg_length)
    if not data:
        return None
    return pickle.loads(data)



import socket
import threading
import argparse
import time
import json
import hashlib
import os
import pickle
import struct

def send_msg(conn, obj):
    data = pickle.dumps(obj)
    length_prefix = struct.pack('!I', len(data))
    conn.sendall(length_prefix + data)

def recv_all(conn, length):
    chunks = []
    bytes_recd = 0
    while bytes_recd < length:
        chunk = conn.recv(length - bytes_recd)
        if not chunk:
            return None
        chunks.append(chunk)
        bytes_recd += len(chunk)
    return b''.join(chunks)

def recv_msg(conn):
    length_prefix = recv_all(conn, 4)
    if not length_prefix:
        return None
    msg_length = struct.unpack('!I', length_prefix)[0]
    data = recv_all(conn, msg_length)
    if not data:
        return None
    return pickle.loads(data)

class Peer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.shared_files = {}      # {info_hash: torrent}
        self.tracker_host = None
        self.tracker_port = None
        # available_torrents[torrent_id] = (info_hash, {name, length, peers, piece_length, pieces})
        self.available_torrents = {}
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
            message = recv_msg(conn)
            if not message:
                conn.close()
                return
            msg_type = message.get('type', None)
            if msg_type == 'handshake_test':
                response = {'type': 'handshake_ack'}
                send_msg(conn, response)
            elif msg_type == 'request_piece':
                info_hash = message['info_hash']
                piece_index = message['index']
                if info_hash in self.shared_files:
                    torrent_info = self.shared_files[info_hash]['info']
                    piece_length = torrent_info['piece_length']
                    pieces = torrent_info['pieces']
                    if piece_index < 0 or piece_index >= len(pieces):
                        response = {'error': 'Invalid piece index'}
                        send_msg(conn, response)
                    else:
                        file_name = torrent_info['name']
                        start = piece_index * piece_length
                        length = piece_length
                        if piece_index == len(pieces)-1:
                            total_length = torrent_info['length']
                            length = total_length - start
                        with open(file_name, 'rb') as f:
                            f.seek(start)
                            piece_data = f.read(length)
                        response = {'data': piece_data}
                        send_msg(conn, response)
                else:
                    response = {'error': 'File not found here.'}
                    send_msg(conn, response)
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
                send_msg(s, message)
                response = recv_msg(s)
                torrents = response.get('torrents', {})
                if torrents:
                    print("Available torrents:")
                    self.available_torrents = {}
                    for idx, (info_hash, t_info) in enumerate(torrents.items()):
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
                send_msg(s, message)
                response = recv_msg(s)
                if not response:
                    print("No response from peer during handshake.")
                    return False
                if response.get('type') == 'handshake_ack':
                    print("Handshake successful with the peer!")
                    return True
                else:
                    print("Peer did not acknowledge the handshake.")
                    return False
        except Exception as e:
            print(f"Failed to handshake with peer {peer_host}:{peer_port}: {e}")
            return False

    def download_pieces(self, info_hash, info, peer_host, peer_port):
        # handshake first
        if not self.handshake_with_peer(peer_host, peer_port):
            print("Handshake failed, cannot download.")
            return

        piece_length = info['piece_length']
        pieces = info['pieces']
        total_pieces = len(pieces)
        file_data_map = {}
        file_name = info['name']

        for i in range(total_pieces):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(5)
                    s.connect((peer_host, peer_port))
                    req_msg = {'type': 'request_piece', 'info_hash': info_hash, 'index': i}
                    send_msg(s, req_msg)
                    response = recv_msg(s)
                    if not response:
                        print("No data received for piece")
                        return
                    if 'error' in response:
                        print(f"Error receiving piece {i}: {response['error']}")
                        return
                    piece_data = response['data']
                    # Verify piece hash
                    expected_hash = pieces[i]
                    actual_hash = hashlib.sha1(piece_data).hexdigest()
                    if actual_hash == expected_hash:
                        file_data_map[i] = piece_data
                        self.show_piece_progress(i+1, total_pieces)
                    else:
                        print(f"Piece {i} hash mismatch. Download failed.")
                        return
            except Exception as e:
                print(f"Failed to download piece {i} from {peer_host}:{peer_port}: {e}")
                return

        # All pieces verified
        with open(f"downloaded_{file_name}", 'wb') as f:
            for i in range(total_pieces):
                f.write(file_data_map[i])
        print(f"\nFile {file_name} assembled successfully and verified.")

    def show_piece_progress(self, completed_pieces, total_pieces):
        percent = (completed_pieces / total_pieces) * 100
        bar_length = 50
        filled_length = int(bar_length * completed_pieces // total_pieces)
        bar = '=' * filled_length + '-' * (bar_length - filled_length)
        print(f"\rDownloading: |{bar}| {percent:.2f}% ({completed_pieces}/{total_pieces} pieces)", end='', flush=True)

    def start_download_by_id(self, torrent_id):
        if torrent_id not in self.available_torrents:
            print("Invalid torrent ID.")
            return
        info_hash, t_info = self.available_torrents[torrent_id]
        if not t_info['peers']:
            print("No peers have this file.")
            return
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
        self.download_pieces(info_hash, t_info, peer_host, peer_port)

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
                "host": self.host,
                "port": self.port,
            },
            "info": {
                "name": os.path.basename(file_path),
                "length": total_length,
                "piece_length": piece_length,
                "pieces": pieces
            },
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
                send_msg(s, message)
                response = recv_msg(s)
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
            print("4. Download a file by ID (multi-piece)")
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
                p_host = input("Enter the peer's IP address: ").strip()
                p_port = int(input("Enter the peer's port number: ").strip())
                peer.handshake_with_peer(p_host, p_port)
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
