import socket
import threading
import pickle
import argparse
import time
import json
import hashlib
import struct
import os

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

class Tracker:
    def __init__(self, host, port=8000):
        self.host = host
        self.port = port
        # {info_hash: {'peers': set(), 'info': torrent_info}}
        self.torrents = {}
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._server, daemon=True).start()
        print(f"Tracker listening on {self.host}:{self.port}")

    def _server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn, addr):
        try:
            message = recv_msg(conn)
            if not message:
                return
            msg_type = message.get('type', None)
            if msg_type == 'announce':
                response = self._handle_announce(message)
            elif msg_type == 'get_torrents':
                response = self._handle_get_torrents()
            else:
                response = {'error': 'Unknown message type'}

            send_msg(conn, response)
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            conn.close()

    def _handle_announce(self, message):
        info_hash = message['info_hash']
        peer_host = message['host']
        peer_port = message['port']

        with self.lock:
            if info_hash not in self.torrents:
                self.torrents[info_hash] = {'peers': set(), 'info': None}
            self.torrents[info_hash]['peers'].add((peer_host, peer_port))
            torrent_info = message.get('torrent_info')
            if torrent_info:
                self.torrents[info_hash]['info'] = torrent_info
                # Pass peer_host and peer_port to the _write_torrent_file method
                self._write_torrent_file(info_hash, torrent_info, peer_host, peer_port)

            all_peers = self.torrents[info_hash]['peers'].copy()
            all_peers.discard((peer_host, peer_port))
            return {'peers': list(all_peers)}


    def _handle_get_torrents(self):
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
        with open(torrent_file_name, 'w') as tf:
            json.dump(torrent, tf, indent=4)
        print(f"Tracker saved torrent file as {torrent_file_name}")

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
