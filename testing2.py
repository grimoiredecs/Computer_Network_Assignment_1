import socket
import threading
import pickle
import argparse
import time

class Tracker:
    def __init__(self, host='0.0.0.0', port=8000):
        self.host = host
        self.port = port
        self.torrents = {}  # {info_hash: {'seeders': set(), 'leechers': set()}}
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
            data = conn.recv(4096)
            message = pickle.loads(data)
            if message['type'] == 'announce':
                self._handle_announce(conn, addr, message)
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
                self.torrents[info_hash] = {'seeders': set(), 'leechers': set()}

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

            # Prepare peer list to send back (excluding the requesting peer)
            all_peers = self.torrents[info_hash]['seeders'] | self.torrents[info_hash]['leechers']
            all_peers.discard(peer)  # Remove self from the list
            peers_list = list(all_peers)
            response = {'peers': peers_list}
            conn.sendall(pickle.dumps(response))

    def clean_up(self):
        # Optional: Implement periodic cleanup to remove inactive peers
        pass

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
