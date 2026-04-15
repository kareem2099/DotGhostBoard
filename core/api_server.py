import os
import base64
import json
import hmac
import urllib.parse
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from PyQt6.QtCore import QThread, pyqtSignal

from core import storage
from core.pairing import PairingSession
from core.sync_engine import decrypt_from_peer

class GhostAPIHandler(BaseHTTPRequestHandler):
    """
    Handles REST API requests.
    Expects Bearer token authentication.
    """
    def _check_rate_limit(self) -> bool:
        """Rate limit pairing attempts to 3 per minute per IP."""
        client_ip = self.client_address[0]
        now = time.time()
        
        # Get rate limit data from server
        if not hasattr(self.server, 'rate_limits'):
            self.server.rate_limits = {}
            
        timestamps = self.server.rate_limits.get(client_ip, [])
        # Filter timestamps from the last 60 seconds
        timestamps = [t for t in timestamps if now - t < 60]
        
        if len(timestamps) >= 3:
            self._send_response(429, {"status": "error", "message": "Too many pairing attempts. Please wait 60s."})
            return False
            
        timestamps.append(now)
        self.server.rate_limits[client_ip] = timestamps
        return True
    def do_GET(self):
        if not self._check_auth():
            return
            
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/api/items':
            query = urllib.parse.parse_qs(parsed_path.query)
            limit = int(query.get('limit', ['50'])[0])
            offset = int(query.get('offset', ['0'])[0])
            
            # Fetch items (for security, if it's secret, we strip the content)
            items = storage.get_all_items(limit=limit, offset=offset)
            safe_items = []
            for item in items:
                safe_item = dict(item)
                if item.get("is_secret"):
                    safe_item["content"] = "[ENCRYPTED]"
                safe_items.append(safe_item)
                
            self._send_response(200, safe_items)
            
        elif parsed_path.path == '/api/stats':
            stats = storage.get_stats()
            self._send_response(200, stats)
            
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if not self._check_auth():
            return
            
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/api/items':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error(400, "Empty body")
                return
                
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
                
            text = data.get("text")
            if not text:
                self._send_response(400, {"status": "error", "message": "Missing 'text' field"})
                return
                
            # Insert into database
            item_id = storage.add_item("text", text)
            
            # Emit signal to update UI
            if hasattr(self.server, 'qthread_parent') and self.server.qthread_parent:
                self.server.qthread_parent.new_text_received.emit(item_id, text)
                
            self._send_response(201, {"id": item_id, "status": "created"})
            
        elif parsed_path.path == '/api/pair/init':
            if not self._check_rate_limit():
                return
            # Pairing Initiation (A -> B)
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return

            node_id = data.get("node_id")
            device_name = data.get("device_name")
            
            if not node_id or not device_name:
                self._send_response(400, {"status": "error", "message": "Missing node_id or device_name"})
                return

            # Trigger UI on this device (B) to show PIN and accept
            if hasattr(self.server, 'qthread_parent') and self.server.qthread_parent:
                self.server.qthread_parent.pairing_requested.emit(node_id, device_name)

            # Generate a dynamic salt for this session
            salt = os.urandom(16)
            # Store salt in a temporary session object on Device B
            # Note: We don't have a full PairingSession yet because the PIN is generated in the UI
            # We'll store the salt so the UI can use it.
            self.server.pending_salts[node_id] = salt
            
            self._send_response(200, {
                "status": "pending", 
                "node_id": self.server.node_id,
                "device_name": self.server.device_name,
                "salt": base64.b64encode(salt).decode("utf-8")
            })

        elif parsed_path.path == '/api/pair/handshake':
            if not self._check_rate_limit():
                return
            # Handshake (A -> B) - A sends encrypted payload
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
                
            node_id = data.get("node_id")
            payload = data.get("payload")
            
            if not node_id or not payload:
                self._send_response(400, {"status": "error", "message": "Missing node_id or payload"})
                return
                
            # Device B must have an active session for this node_id
            session = self.server.active_pairing_sessions.get(node_id)
            if not session:
                self._send_response(403, {"status": "error", "message": "No active session for this node"})
                return
                
            # Complete the handshake
            try:
                # payload is encrypted A_pub bytes
                # B uses its PIN-derived key to decrypt A_pub
                # Then B computes shared secret
                # Then B returns its own encrypted pubkey
                shared_secret = session.complete(payload, node_id, data.get("device_name", "Unknown"))
                if not shared_secret:
                    if hasattr(self.server, 'qthread_parent') and self.server.qthread_parent:
                        self.server.qthread_parent.pairing_failed.emit(node_id, "Invalid PIN or corrupted payload")
                    self._send_response(401, {"status": "error", "message": "Invalid PIN or corrupted payload"})
                    return
                
                # Extract api_port to store correct IP+Port for two-way sync
                api_port = data.get("api_port", 9090)
                peer_url = f"http://{self.client_address[0]}:{api_port}"
                storage.add_trusted_peer(node_id, session.peer_device_name, shared_secret, peer_url)
                
                # Success signal to UI
                if hasattr(self.server, 'qthread_parent') and self.server.qthread_parent:
                    self.server.qthread_parent.pairing_completed.emit(node_id, session.peer_device_name)
                
                # Send encrypted B_pub back to A
                self._send_response(200, {
                    "status": "success",
                    "payload": session.get_local_payload()
                })
                
                # Clean up session
                del self.server.active_pairing_sessions[node_id]
                
            except Exception as e:
                if hasattr(self.server, 'qthread_parent') and self.server.qthread_parent:
                    self.server.qthread_parent.pairing_failed.emit(node_id, str(e))
                self._send_response(500, {"status": "error", "message": str(e)})

        elif parsed_path.path == '/api/pair/unpair':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body)
                    node_id = data.get("node_id")
                    payload = data.get("payload")
                    peer = storage.get_trusted_peer(node_id)
                    if peer and payload:
                        plaintext = decrypt_from_peer(payload, peer["shared_secret"])
                        if plaintext == "unpair":
                            storage.remove_trusted_peer(node_id)
                            if hasattr(self.server, 'qthread_parent') and self.server.qthread_parent:
                                self.server.qthread_parent.peer_unpaired.emit(node_id)
                            self._send_response(200, {"status": "success"})
                            return
                except Exception as e:
                    pass
            self._send_response(400, {"status": "error", "message": "Invalid request"})
            return

        elif parsed_path.path == '/api/sync':
            # Incoming E2EE encrypted clipboard item from a trusted peer
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error(400, "Empty body")
                return
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            sender_node_id = data.get("node_id")
            item_type      = data.get("item_type", "text")
            payload        = data.get("payload")
            if not sender_node_id or not payload:
                self.send_error(400, "Missing node_id or payload")
                return
            # Verify sender is a trusted peer
            peer = storage.get_trusted_peer(sender_node_id)
            if not peer:
                self._send_response(403, {"status": "error", "message": "Untrusted peer"})
                return
            # Decrypt with the shared secret established during pairing
            plaintext = decrypt_from_peer(payload, peer["shared_secret"])
            if plaintext is None:
                self._send_response(401, {"status": "error", "message": "Decryption failed"})
                return
            # Store (add_item handles deduplication automatically)
            item_id = storage.add_item(item_type, plaintext)
            # Notify UI thread-safely
            if hasattr(self.server, 'qthread_parent') and self.server.qthread_parent:
                self.server.qthread_parent.sync_received.emit(item_id, plaintext)
            self._send_response(201, {"status": "synced", "id": item_id})

        else:
            self.send_error(404, "Not Found")


    def _check_auth(self) -> bool:
        """Verify the Authorization Bearer header against the settings token."""
        # Check if the endpoint is public (pairing)
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path.startswith('/api/pair/') or parsed_path.path == '/api/sync':
            return True  # Protected by PIN/peer-trust logic, not Bearer token
            
        # Grab token from server instance (passed via thread)
        expected_token = getattr(self.server, 'api_token', None)
        if not expected_token:
            # If no token configured, fail closed
            self.send_error(500, "API Token not configured")
            return False
            
        auth_header = self.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            self.send_error(401, "Unauthorized")
            return False
            
        provided_token = auth_header.split(" ")[1].strip()
        
        # Constant-time compare
        if not hmac.compare_digest(provided_token, expected_token):
            self.send_error(403, "Forbidden")
            return False
            
        return True

    def _send_response(self, code: int, data: dict | list):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
        
    def log_message(self, format, *args):
        # Suppress default HTTP logging to stdout to keep console clean
        pass


class APIServerThread(QThread):
    new_text_received = pyqtSignal(int, str)  # Emitted on successful local POST
    sync_received     = pyqtSignal(int, str)  # Emitted when a peer pushes an item
    pairing_requested = pyqtSignal(str, str)  # node_id, device_name
    pairing_completed = pyqtSignal(str, str)  # node_id, device_name
    pairing_failed    = pyqtSignal(str, str)  # node_id, error_message
    peer_unpaired     = pyqtSignal(str)       # node_id
    
    def __init__(self, port: int, token: str, node_id: str, device_name: str, parent=None):
        super().__init__(parent)
        self.port = port
        self.token = token
        self.node_id = node_id
        self.device_name = device_name
        self.server = None
        # Track pairing sessions keyed by peer node_id
        self.active_pairing_sessions = {} 
        self.pending_salts = {} # salt per peer_node_id
        self.rate_limits = {} # IP -> [timestamps]

    def run(self):
        try:
            # Bind to 0.0.0.0 for actual network sync
            self.server = HTTPServer(('0.0.0.0', self.port), GhostAPIHandler)
            # Inject properties into the server so the handler can access them
            self.server.api_token = self.token
            self.server.node_id = self.node_id
            self.server.device_name = self.device_name
            self.server.active_pairing_sessions = self.active_pairing_sessions
            self.server.pending_salts = self.pending_salts
            self.server.rate_limits = self.rate_limits
            self.server.qthread_parent = self
            print(f"[API] Server listening on 0.0.0.0:{self.port}")
            self.server.serve_forever()
        except Exception as e:
            print(f"[API] Failed to start server on port {self.port}: {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("[API] Server stopped")
