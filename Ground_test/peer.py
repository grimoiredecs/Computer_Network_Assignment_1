import socket
import threading
import argparse
import time
import json
import hashlib
import os
import pickle
import struct
import mmap
from tqdm import tqdm  # Import tqdm for progress bar

def send_msg(conn, obj):
    """
    Serialize and send a Python object with a length prefix.
    
    Args:
        conn (socket.socket): The socket connection.
        obj (Any): The Python object to send.
    """
    data = pickle.dumps(obj)
    length_prefix = struct.pack('!I', len(data))
    conn.sendall(length_prefix + data)

def recv_all(conn, length):
    """
    Receive exactly 'length' bytes from the socket.
    
    Args:
        conn (socket.socket): The socket connection.
        length (int): Number of bytes to receive.
        
    Returns:
        bytes or None: The received bytes or None if connection is closed.
    """
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
    """
    Receive a length-prefixed serialized Python object from the socket.
    
    Args:
        conn (socket.socket): The socket connection.
        
    Returns:
        Any or None: The deserialized Python object or None if failed.
    """
    # Read length prefix
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
        """
        Initialize the Peer with host and port.
        
        Args:
            host (str): The IP address to bind.
            port (int): The port number to bind.
        """
        self.host = host
        self.port = port
        self.shared_files = {}      # {info_hash: torrent}
        self.tracker_host = None
        self.tracker_port = None
        # available_torrents[torrent_id] = (info_hash, {name, length, peers, piece_length, pieces})
        self.available_torrents = {}
        self.connected_trackers = set()

    def start_server(self):
        """
        Start the server thread to listen for incoming connections.
        """
        threading.Thread(target=self._server, daemon=True).start()
        print(f"Peer listening on {self.host}:{self.port}")

    def _server(self):
        """
        The server method that listens for incoming connections and handles each client in a new thread.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn, addr):
        """
        Handle incoming client requests.
        
        Args:
            conn (socket.socket): The client connection socket.
            addr (tuple): The client address.
        """
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
        """
        Connect to the tracker and perform a handshake.
        
        Args:
            tracker_host (str): The tracker's IP address.
            tracker_port (int): The tracker's port number.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # Set a timeout for connecting to the tracker
                s.connect((tracker_host, tracker_port))

                # Send a handshake request
                handshake_msg = {'type': 'handshake'}
                send_msg(s, handshake_msg)

                # Wait for the handshake response
                response = recv_msg(s)
                if response and response.get('type') == 'handshake_ack':
                    print(f"Handshake successful: {response.get('message', 'No message')}")
                    self.tracker_host = tracker_host
                    self.tracker_port = tracker_port
                    print(f"Connected to tracker at {self.tracker_host}:{self.tracker_port}")
                else:
                    print("Handshake failed: Invalid tracker response.")
        except Exception as e:
            print(f"Failed to connect to tracker at {tracker_host}:{tracker_port}: {e}")

    def get_torrent_list(self):
        """
        Retrieve the list of available torrents from the tracker.
        """
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
        """
        Perform a handshake with another peer to verify connectivity.
        
        Args:
            peer_host (str): The peer's IP address.
            peer_port (int): The peer's port number.
        
        Returns:
            bool: True if handshake is successful, False otherwise.
        """
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
        """
        Download all pieces of a torrent from a single peer and assemble the file using mmap.
        
        Args:
            info_hash (str): The hash identifying the torrent.
            info (dict): The torrent's info dictionary.
            peer_host (str): The peer's IP address.
            peer_port (int): The peer's port number.
        """
        # Perform handshake with the peer
        if not self.handshake_with_peer(peer_host, peer_port):
            print("Handshake failed, cannot download.")
            return

        piece_length = info['piece_length']
        pieces = info['pieces']
        total_pieces = len(pieces)
        file_data_map = {}
        file_name = info['name']
        total_length = info['length']

        print(f"Starting download of '{file_name}' from {peer_host}:{peer_port}...")

        # Initialize tqdm progress bar
        with tqdm(total=total_pieces, desc=f"Downloading {file_name}", unit="piece") as pbar:
            for i in range(total_pieces):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(10)  # Increased timeout to accommodate slower transfers
                        s.connect((peer_host, peer_port))
                        req_msg = {'type': 'request_piece', 'info_hash': info_hash, 'index': i}
                        send_msg(s, req_msg)
                        response = recv_msg(s)
                        if not response:
                            print("\nNo data received for piece")
                            return
                        if 'error' in response:
                            print(f"\nError receiving piece {i}: {response['error']}")
                            return
                        piece_data = response['data']
                        # Verify piece hash
                        expected_hash = pieces[i]
                        actual_hash = hashlib.sha1(piece_data).hexdigest()
                        if actual_hash == expected_hash:
                            file_data_map[i] = piece_data
                            pbar.update(1)  # Update tqdm progress bar
                        else:
                            print(f"\nPiece {i} hash mismatch. Download failed.")
                            return
                except Exception as e:
                    print(f"\nFailed to download piece {i} from {peer_host}:{peer_port}: {e}")
                    return

        # All pieces downloaded and verified
        downloaded_file_path = f"downloaded_{file_name}"

        try:
            # Pre-allocate the file with the total length
            with open(downloaded_file_path, 'wb') as f:
                f.truncate(total_length)

            # Open the file in read/write binary mode
            with open(downloaded_file_path, 'r+b') as f:
                # Memory-map the entire file for writing
                with mmap.mmap(f.fileno(), length=total_length, access=mmap.ACCESS_WRITE) as m:
                    offset = 0
                    for i in range(total_pieces):
                        piece_data = file_data_map[i]
                        m[offset:offset+len(piece_data)] = piece_data
                        offset += len(piece_data)

            print(f"\nFile '{file_name}' assembled successfully and verified as '{downloaded_file_path}'.")
        except Exception as e:
            print(f"\nFailed to assemble the file using mmap: {e}")

    def start_download_by_id(self, torrent_id):
        """
        Initiate the download of a torrent by its ID from the available list.
        
        Args:
            torrent_id (int): The ID of the torrent to download.
        """
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
        # Start downloading directly without threading
        self.download_pieces(info_hash, t_info, peer_host, peer_port)

    def share_file(self, file_path):
        """
        Share a file by creating a torrent and announcing it to the tracker.
        
        Args:
            file_path (str): The path to the file to share.
        """
        torrent = self.create_torrent_file(file_path)
        info_str = json.dumps(torrent['info'], sort_keys=True)
        info_hash = hashlib.sha1(info_str.encode()).hexdigest()
        self.shared_files[info_hash] = torrent
        print(f"Sharing file '{file_path}' with info_hash {info_hash}")
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
        """
        Create a torrent file for the given file.
        
        Args:
            file_path (str): The path to the file to create a torrent for.
            piece_length (int, optional): The length of each piece in bytes. Defaults to 512*1024 (512KB).
        
        Returns:
            dict: The torrent metadata dictionary.
        """
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

        tracker_host = self.tracker_host
        tracker_port = self.tracker_port

        if not tracker_host or not tracker_port:
            tracker_host = input("Enter the tracker's IP address: ").strip()
            tracker_port = int(input("Enter the tracker's port number: ").strip())
            self.connect_to_tracker(tracker_host, tracker_port)

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
        """
        Announce the torrent to the tracker.
        
        Args:
            info_hash (str): The hash identifying the torrent.
            event (str, optional): The event type (e.g., 'completed'). Defaults to None.
        
        Returns:
            list: List of peers returned by the tracker.
        """
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
        """
        Placeholder method to stop all ongoing transfers.
        Currently not implemented.
        """
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
