import socket
import json
from threading import Thread


class Tracker:
    def __init__(self, ip, port=330):
        self.ip = ip
        self.port = port
        self.torrent_db = {}  # Torrent database: torrent_hash -> torrent_metadata
        self.peer_listing = {}  # Peer list: torrent_hash -> list of peer info
        print(f"Tracker is up and running at {self.ip}:{self.port}")

    def handle_conn(self, addr, conn):
        """
        Handle an incoming connection from a peer.
        :param addr: Address of the peer.
        :param conn: Socket connection object.
        """
        print(f"Connection received from: {addr}")
        try:
            while True:
                data = conn.recv(1024).decode("utf-8")
                if not data:
                    break
                print(f"Received: {data}")

                # Process the string request
                response = self.request_process(data)

                # Send the response back to the peer
                conn.send(response.encode("utf-8"))
        except Exception as e:
            print(f"Error handling connection from {addr}: {e}")
        finally:
            conn.close()

    def request_process(self, request):
        """
        Process a peer's string-based request.
        :param request: String request from the peer.
        :return: Response as a string.
        """
        # Split the request string into components
        parts = request.split("|")
        if len(parts) < 2:
            return "error|Invalid request format"

        action = parts[0].lower()
        torrent_hash = parts[1]
        peer_info = None

        if action in {"start", "stop"} and len(parts) == 5:
            peer_info = {
                "peer_id": parts[2],
                "ip": parts[3],
                "port": int(parts[4]),
            }

        # Handle actions
        if action == "start":
            if torrent_hash not in self.torrent_db:
                return "error|Torrent not found"

            self.peer_listing.setdefault(torrent_hash, [])
            if peer_info not in self.peer_listing[torrent_hash]:
                self.peer_listing[torrent_hash].append(peer_info)
                return f"success|Peer added for {torrent_hash}"
            else:
                return f"error|Peer already exists for {torrent_hash}"

        elif action == "stop":
            if torrent_hash not in self.peer_listing:
                return "error|No peers found for torrent"

            if peer_info in self.peer_listing[torrent_hash]:
                self.peer_listing[torrent_hash].remove(peer_info)
                if not self.peer_listing[torrent_hash]:  # Clean up empty peer lists
                    del self.peer_listing[torrent_hash]
                return f"success|Peer removed for {torrent_hash}"
            else:
                return f"error|Peer not found for {torrent_hash}"

        elif action == "list":
            if torrent_hash not in self.peer_listing:
                return f"error|No peers found for {torrent_hash}"

            peer_list = self.peer_listing[torrent_hash]
            peer_list_str = ";".join(
                [f"{peer['peer_id']}@{peer['ip']}:{peer['port']}" for peer in peer_list]
            )
            return f"success|Peers for {torrent_hash}: {peer_list_str}"

        else:
            return "error|Unknown action"

    def start(self):
        """
        Start the tracker server.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((self.ip, self.port))
            server_socket.listen(10)
            print(f"Tracker listening on {self.ip}:{self.port}")

            while True:
                conn, addr = server_socket.accept()
                client_thread = Thread(target=self.handle_conn, args=(addr, conn))
                client_thread.start()


if __name__ == "__main__":
    tracker_ip = Tracker.est_conn()
    tracker = Tracker(ip=tracker_ip, port=330)
    tracker.start()
