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
    """
    Serialize and send a Python object with a length prefix.
    
    Args:
        conn (socket.socket): The socket connection.
        obj (Any): The Python object to send.
    """
    try:
        data = pickle.dumps(obj)
        length_prefix = struct.pack('!I', len(data))
        conn.sendall(length_prefix + data)
    except Exception as e:
        print(f"Failed to send message: {e}")

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
    try:
        length_prefix = recv_all(conn, 4)
        if not length_prefix:
            return None
        msg_length = struct.unpack('!I', length_prefix)[0]
        data = recv_all(conn, msg_length)
        if not data:
            return None
        return pickle.loads(data)
    except Exception as e:
        print(f"Failed to receive message: {e}")
        return None

class Tracker:
    def __init__(self, host, port=8000):
        """
        Initialize the Tracker with host and port.

        Args:
            host (str): The host IP address.
            port (int): The port number.
        """
        self.host = host
        self.port = port
        self.torrents = {}  # {info_hash: {'peers': set(), 'info': torrent_info}}
        self.lock = threading.Lock()  # To handle concurrent access to torrents

    def start(self):
        """
        Start the tracker server to listen for incoming connections.
        """
        threading.Thread(target=self._server, daemon=True).start()
        print(f"Tracker listening on {self.host}:{self.port}")

    def _server(self):
        """
        The server method that listens for incoming connections and handles each client in a new thread.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"Tracker started on {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn, addr):
        """
        Handle incoming client messages, including the handshake.

        Args:
            conn (socket.socket): The client connection socket.
            addr (tuple): The client address.
        """
        peer_host, peer_port = addr
        try:
            # Step 1: Receive Handshake from Peer
            handshake_message = recv_msg(conn)
            if not handshake_message:
                print(f"No handshake received. Closing connection with {addr}")
                return

            if handshake_message.get('type') != 'handshake':
                # Invalid handshake
                error_response = {'type': 'error', 'message': 'Invalid handshake'}
                send_msg(conn, error_response)
                print(f"Invalid handshake from {addr}. Connection closed.")
                return

            # Step 2: Send Handshake Acknowledgment
            handshake_ack = {'type': 'handshake_ack', 'message': 'Handshake successful'}
            send_msg(conn, handshake_ack)
            print(f"Handshake successful with peer {peer_host}:{peer_port}")

            # Step 3: Enter Loop to Handle Further Messages
            while True:
                message = recv_msg(conn)
                if not message:
                    print(f"Peer {peer_host}:{peer_port} disconnected.")
                    self._remove_peer_from_all_torrents(peer_host, peer_port)
                    break

                msg_type = message.get('type', None)

                if msg_type == 'announce':
                    response = self._handle_announce(message)
                    send_msg(conn, response)
                elif msg_type == 'get_torrents':
                    response = self._handle_get_torrents()
                    send_msg(conn, response)
                else:
                    response = {'error': 'Unknown message type'}
                    send_msg(conn, response)
                    print(f"Received unknown message type from {addr}: {msg_type}")

        except Exception as e:
            print(f"Error handling client {addr}: {e}")
            self._remove_peer_from_all_torrents(peer_host, peer_port)
        finally:
            conn.close()

    def _handle_announce(self, message):
        """
        Handle announce messages from peers.

        Args:
            message (dict): The announce message.

        Returns:
            dict: The response message containing the list of peers.
        """
        info_hash = message.get('info_hash')
        peer_host = message.get('host')
        peer_port = message.get('port')
        event = message.get('event', None)
        torrent_info = message.get('torrent_info', None)

        if not info_hash or not peer_host or not peer_port:
            print("Received announce with missing fields.")
            return {'error': 'Missing fields in announce message.'}

        with self.lock:
            if info_hash not in self.torrents:
                if event == 'started' and torrent_info:
                    # Add new torrent
                    self.torrents[info_hash] = {
                        'peers': set(),
                        'info': torrent_info
                    }
                    self._write_torrent_file(info_hash, torrent_info, peer_host, peer_port)
                    print(f"Torrent added: {torrent_info.get('name')} (Info Hash: {info_hash})")
                else:
                    print(f"Announce received for unknown torrent {info_hash} from {peer_host}:{peer_port}")
                    return {'error': 'Unknown torrent.'}

            # Add or remove peers based on the event
            if event == 'started':
                self.torrents[info_hash]['peers'].add((peer_host, peer_port))
                print(f"Peer {peer_host}:{peer_port} added to torrent {self.torrents[info_hash]['info'].get('name')}")
            elif event == 'stopped':
                self.torrents[info_hash]['peers'].discard((peer_host, peer_port))
                print(f"Peer {peer_host}:{peer_port} removed from torrent {self.torrents[info_hash]['info'].get('name')}")
            elif event == 'completed':
                print(f"Peer {peer_host}:{peer_port} completed downloading torrent {self.torrents[info_hash]['info'].get('name')}")
            # Additional events can be handled here

            # Prepare the list of peers excluding the requesting peer
            all_peers = self.torrents[info_hash]['peers'].copy()
            all_peers.discard((peer_host, peer_port))
            return {'peers': list(all_peers)}

    def _handle_get_torrents(self):
        """
        Handle get_torrents requests from peers.

        Returns:
            dict: The response message containing the list of torrents.
        """
        with self.lock:
            torrents_info = {}
            for info_hash, data in self.torrents.items():
                t_info = data['info']
                if t_info:
                    peers_list = list(data['peers'])
                    torrents_info[info_hash] = {
                        'name': t_info.get('name', 'Unknown'),
                        'length': t_info.get('length', 0),
                        'peers': peers_list,
                        'piece_length': t_info.get('piece_length'),
                        'pieces': t_info.get('pieces', [])
                    }
        return {'torrents': torrents_info}

    def _write_torrent_file(self, info_hash, torrent_info, peer_host, peer_port):
        """
        Save the torrent information as a .torrent file.

        Args:
            info_hash (str): The info_hash of the torrent.
            torrent_info (dict): The torrent's info dictionary.
            peer_host (str): The host address of the peer.
            peer_port (int): The port number of the peer.
        """
        # Construct the torrent dictionary
        torrent = {
            "announce": {
                "host": peer_host,
                "port": peer_port
            },
            "info": torrent_info,
            "comment": "Torrent file stored by tracker",
            "created_by": "Tracker"
        }

        # Save the file as <info_hash>.torrent
        torrent_file_name = f"{info_hash}.torrent"
        try:
            with open(torrent_file_name, 'w') as tf:
                json.dump(torrent, tf, indent=4)
            print(f"Tracker saved torrent file as {torrent_file_name}")
        except Exception as e:
            print(f"Failed to write torrent file {torrent_file_name}: {e}")

    def _remove_peer_from_all_torrents(self, peer_host, peer_port):
        """
        Remove a peer from all torrents it is part of.

        Args:
            peer_host (str): The host address of the peer.
            peer_port (int): The port number of the peer.
        """
        with self.lock:
            for info_hash, data in self.torrents.items():
                if (peer_host, peer_port) in data['peers']:
                    data['peers'].discard((peer_host, peer_port))
                    print(f"Peer {peer_host}:{peer_port} removed from torrent {data['info'].get('name')} due to disconnection.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='P2P Tracker')
    parser.add_argument('--host', default='0.0.0.0', help='Tracker host')
    parser.add_argument('--port', type=int, default=8000, help='Tracker port')
    args = parser.parse_args()

    tracker = Tracker(host=args.host, port=args.port)
    tracker.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nTracker shutting down.")
