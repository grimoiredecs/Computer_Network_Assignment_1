import socket
import threading
import pickle
import argparse
import time

class Tracker:
    def __init__(self, host='0.0.0.0', port=2000):
        self.host = host
        self.port = port
        self.torrents = {}  # {info_hash: {'seeders': set(), 'leechers': set(), 'info': torrent_info}}
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
            message = pickle.loads(data)
            if message['type'] == 'announce':
                self._handle_announce(conn, addr, message)
            elif message['type'] == 'get_torrents':
                self._handle_get_torrents(conn, addr)
            elif message['type'] == 'get_torrent_info':
                self._handle_get_torrent_info(conn, addr, message)
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
        event = message.get('event', 'started')

        with self.lock:
            if info_hash not in self.torrents:
                self.torrents[info_hash] = {'seeders': set(), 'leechers': set(), 'info': None}

            peer = (peer_host, peer_port)

            if event == 'started':
                self.torrents[info_hash]['leechers'].add(peer)
                print(f"Peer {peer} started downloading torrent {info_hash}")
            elif event == 'completed':
                # Move peer from leechers to seeders
                self.torrents[info_hash]['leechers'].discard(peer)
                self.torrents[info_hash]['seeders'].add(peer)
                print(f"Peer {peer} completed download of torrent {info_hash} and is now seeding")
            elif event == 'stopped':
                # Remove peer from both lists
                self.torrents[info_hash]['leechers'].discard(peer)
                self.torrents[info_hash]['seeders'].discard(peer)
                print(f"Peer {peer} stopped sharing torrent {info_hash}")
            else:
                # Default to leecher if event is unknown
                self.torrents[info_hash]['leechers'].add(peer)
                print(f"Peer {peer} announced for torrent {info_hash} with unknown event '{event}'")

            # Store full torrent info if provided
            torrent_info = message.get('torrent_info')
            if torrent_info:
                self.torrents[info_hash]['info'] = torrent_info  # Store the full info dictionary

            # Prepare peer list to send back (excluding the requesting peer)
            all_peers = self.torrents[info_hash]['seeders'] | self.torrents[info_hash]['leechers']
            all_peers.discard(peer)  # Remove self from the list
            peers_list = list(all_peers)
            response = {'peers': peers_list}
            conn.sendall(pickle.dumps(response))

    def _handle_get_torrents(self, conn, addr):
        with self.lock:
            torrents_info = {}
            for info_hash, data in self.torrents.items():
                torrent_info = data['info']
                if torrent_info:
                    torrents_info[info_hash] = {
                        'name': torrent_info.get('name', 'Unknown'),
                        'length': torrent_info.get('length', 0),
                        'seeders': len(data['seeders']),
                        'leechers': len(data['leechers'])
                    }
            response = {'torrents': torrents_info}
            conn.sendall(pickle.dumps(response))

    def _handle_get_torrent_info(self, conn, addr, message):
        torrent_id = message.get('torrent_id')
        with self.lock:
            info_hashes = list(self.torrents.keys())
            if 0 <= torrent_id < len(info_hashes):
                info_hash = info_hashes[torrent_id]
                torrent_data = self.torrents[info_hash]
                torrent_info = torrent_data.get('info')
                if torrent_info:
                    response = {'info_hash': info_hash, 'info': torrent_info}
                else:
                    response = {'error': 'Torrent info not available'}
            else:
                response = {'error': 'Invalid torrent ID'}
        conn.sendall(pickle.dumps(response))

if __name__ == "__main__":
    # Command-line arguments
    parser = argparse.ArgumentParser(description='P2P Tracker')
    parser.add_argument('--host', default='0.0.0.0', help='Tracker host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8000, help='Tracker port (default: 8000)')
    args = parser.parse_args()

    tracker = Tracker(host=args.host, port=args.port)
    tracker.start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nTracker shutting down.")
