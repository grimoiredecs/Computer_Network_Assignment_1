import socket
import threading
import pickle
import argparse
import time

class Tracker:
    def __init__(self, host='0.0.0.0', port=8000):
        self.host = host
        self.port = port
        # Structure: {info_hash: {'peers': set((host, port)), 'info': torrent_info}}
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
            data = conn.recv(8192)
            if not data:
                return
            message = pickle.loads(data)
            msg_type = message.get('type', None)
            if msg_type == 'announce':
                self._handle_announce(conn, addr, message)
            elif msg_type == 'get_torrents':
                self._handle_get_torrents(conn)
            else:
                response = {'error': 'Unknown message type'}
                conn.sendall(pickle.dumps(response))
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            conn.close()

    def _handle_announce(self, conn, addr, message):
        info_hash = message['info_hash']
        peer_host = message['host']
        peer_port = message['port']

        with self.lock:
            if info_hash not in self.torrents:
                self.torrents[info_hash] = {'peers': set(), 'info': None}
            # Add this peer to the set of peers that have the file
            self.torrents[info_hash]['peers'].add((peer_host, peer_port))
            torrent_info = message.get('torrent_info')
            if torrent_info:
                self.torrents[info_hash]['info'] = torrent_info

        # Respond with a list of other peers (excluding this one)
        with self.lock:
            all_peers = self.torrents[info_hash]['peers'].copy()
            all_peers.discard((peer_host, peer_port))
            response = {'peers': list(all_peers)}
        conn.sendall(pickle.dumps(response))
        print(f"Peer {(peer_host,peer_port)} announced having {info_hash}")

    def _handle_get_torrents(self, conn):
        with self.lock:
            torrents_info = {}
            for info_hash, data in self.torrents.items():
                torrent_info = data['info']
                if torrent_info:
                    # Include the list of peers who have this file
                    peers_list = list(data['peers'])
                    torrents_info[info_hash] = {
                        'name': torrent_info.get('name', 'Unknown'),
                        'length': torrent_info.get('length', 0),
                        'peers': peers_list  # Return the actual peers (host, port)
                    }
            response = {'torrents': torrents_info}
        conn.sendall(pickle.dumps(response))

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
