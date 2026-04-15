import base64
import secrets
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from core import storage
from core.pairing import PairingSession

class InitWorker(QThread):
    finished = pyqtSignal(bool, str, str, bytes) # success, message, peer_node_id, salt
    
    def __init__(self, peer_ip: str, peer_port: int, local_node_id: str, local_name: str):
        super().__init__()
        self.peer_url = f"http://{peer_ip}:{peer_port}"
        self.local_node_id = local_node_id
        self.local_name = local_name
        
    def run(self):
        try:
            resp = requests.post(f"{self.peer_url}/api/pair/init", json={
                "node_id": self.local_node_id,
                "device_name": self.local_name
            }, timeout=5)
            
            if resp.status_code != 200:
                self.finished.emit(False, f"Peer rejected request ({resp.status_code})", "", b"")
                return
                
            data = resp.json()
            peer_node_id = data.get("node_id")
            salt_b64 = data.get("salt")
            if not salt_b64:
                self.finished.emit(False, "Peer did not provide a salt.", "", b"")
                return
            salt = base64.b64decode(salt_b64)
            self.finished.emit(True, "", peer_node_id, salt)
        except Exception as e:
            self.finished.emit(False, str(e), "", b"")

class PairingWorker(QThread):
    finished = pyqtSignal(bool, str) # success, message
    
    def __init__(self, peer_ip: str, peer_port: int, pin: str, local_node_id: str, local_name: str, peer_node_id: str, salt: bytes, local_port: int):
        super().__init__()
        self.peer_url = f"http://{peer_ip}:{peer_port}"
        self.pin = pin
        self.local_node_id = local_node_id
        self.local_name = local_name
        self.peer_node_id = peer_node_id
        self.salt = salt
        self.local_port = local_port
        
    def run(self):
        try:
            # 2. Handshake
            session = PairingSession(pin=self.pin, salt=self.salt)
            payload = session.get_local_payload()
            
            resp = requests.post(f"{self.peer_url}/api/pair/handshake", json={
                "node_id": self.local_node_id,
                "device_name": self.local_name,
                "api_port": self.local_port,
                "payload": payload
            }, timeout=10)
            
            if resp.status_code != 200:
                try:
                    err_data = resp.json()
                    msg = err_data.get("message", f"HTTP {resp.status_code}")
                except:
                    msg = resp.text or f"HTTP {resp.status_code}"
                self.finished.emit(False, f"Handshake failed: {msg}")
                return
                
            data = resp.json()
            if data.get("status") == "success":
                peer_payload = data.get("payload")
                shared_secret = session.complete(peer_payload, self.peer_node_id, data.get("device_name", self.peer_node_id))
                if shared_secret:
                    storage.add_trusted_peer(self.peer_node_id, data.get("device_name", self.peer_node_id), shared_secret, self.peer_url)
                    self.finished.emit(True, "Successfully paired!")
                else:
                    self.finished.emit(False, "Failed to compute shared secret (PIN mismatch?)")
            else:
                self.finished.emit(False, data.get("message", "Unknown error"))
                
        except Exception as e:
            self.finished.emit(False, str(e))

class PairingDialog(QDialog):
    def __init__(self, role="initiator", peer_ip=None, peer_port=None, 
                 peer_node_id=None, peer_name=None, salt=None, parent=None):
        super().__init__(parent)
        self.role = role # "initiator" or "receiver"
        self.peer_ip = peer_ip
        self.peer_port = peer_port
        self.peer_node_id = peer_node_id
        self.peer_name = peer_name
        self.salt = salt # Required for receiver mode
        
        self.setWindowTitle("🔗 Device Pairing")
        self.setFixedSize(380, 310)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        
        # Load local identity
        from ui.settings import load_settings
        settings = load_settings()
        self.local_node_id = settings.get("node_id", "unknown")
        self.local_name = settings.get("device_name", "Unknown Ghost")
        self.local_port = settings.get("api_port", 9090)
        
        self.session = None
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("🔗 Pairing Request")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00ff41;")
        layout.addWidget(title)
        
        if self.role == "receiver":
            # ROLE: Receiver - Show generated PIN
            pin = "".join([str(secrets.randbelow(10)) for _ in range(6)])
            if not self.salt:
                # Should have been passed from Dashboard
                self.salt = secrets.token_bytes(16)
            self.session = PairingSession(pin=pin, salt=self.salt)
            
            self.info_lbl = QLabel(f"<b>{self.peer_name}</b> wants to pair with you.")
            self.info_lbl.setStyleSheet("color: #ccc;")
            self.info_lbl.setWordWrap(True)
            layout.addWidget(self.info_lbl)
            
            self.pin_box = QFrame()
            self.pin_box.setStyleSheet("background: #111; border: 2px solid #00ff41; border-radius: 8px;")
            pin_layout = QHBoxLayout(self.pin_box)
            
            self.pin_label = QLabel(pin)
            self.pin_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #00ff41; letter-spacing: 12px;")
            self.pin_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pin_layout.addWidget(self.pin_label)
            layout.addWidget(self.pin_box)
            
            self.hint_lbl = QLabel("Enter this code on the other device.")
            self.hint_lbl.setStyleSheet("color: #666; font-size: 11px;")
            self.hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.hint_lbl)
            
            self.btns_layout = QHBoxLayout()
            self.accept_btn = QPushButton("Accept Pairing")
            self.accept_btn.setObjectName("SaveBtn")
            self.accept_btn.clicked.connect(self._on_receiver_accept) 
            
            self.reject_btn = QPushButton("Reject")
            self.reject_btn.clicked.connect(self.reject)
            
            self.btns_layout.addWidget(self.reject_btn)
            self.btns_layout.addWidget(self.accept_btn)
            layout.addLayout(self.btns_layout)
            
            self.waiting_lbl = QLabel("Pairing in progress... Please wait.")
            self.waiting_lbl.setStyleSheet("color: #00ff41; font-style: italic;")
            self.waiting_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.waiting_lbl.hide()
            layout.addWidget(self.waiting_lbl)
            
        else:
            # ROLE: Initiator - Input PIN
            info = QLabel(f"Initiating pairing with <b>{self.peer_name}</b>.")
            info.setStyleSheet("color: #ccc;")
            layout.addWidget(info)
            
            self.pin_input = QLineEdit()
            self.pin_input.setPlaceholderText("Enter 6-digit PIN")
            self.pin_input.setMaxLength(6)
            self.pin_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pin_input.setStyleSheet("font-size: 24px; color: #00ff41; background: #111; border: 1px solid #333; height: 45px;")
            self.pin_input.setEnabled(False)
            layout.addWidget(self.pin_input)
            
            self.progress = QProgressBar()
            self.progress.setRange(0, 0) # Indeterminate
            layout.addWidget(self.progress)
            
            self.status_lbl = QLabel("Sending pairing request...")
            self.status_lbl.setStyleSheet("color: #ff9900; font-size: 11px;")
            layout.addWidget(self.status_lbl)
            
            btns = QHBoxLayout()
            self.pair_btn = QPushButton("Confirm PIN")
            self.pair_btn.setObjectName("SaveBtn")
            self.pair_btn.clicked.connect(self._start_pairing_worker)
            self.pair_btn.setEnabled(False)
            
            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(self.reject)
            
            btns.addWidget(cancel_btn)
            btns.addWidget(self.pair_btn)
            layout.addLayout(btns)
            
            # Start init worker
            self.init_worker = InitWorker(self.peer_ip, self.peer_port, self.local_node_id, self.local_name)
            self.init_worker.finished.connect(self._on_init_finished)
            self.init_worker.start()

    def _on_init_finished(self, success, message, peer_node_id, salt):
        self.progress.hide()
        if success:
            self.peer_node_id = peer_node_id
            self.salt = salt
            self.pin_input.setEnabled(True)
            self.pair_btn.setEnabled(True)
            self.status_lbl.setText("Enter the PIN shown on the other device.")
            self.status_lbl.setStyleSheet("color: #00ff41; font-size: 11px;")
            self.pin_input.setFocus()
        else:
            self.status_lbl.setText(message)
            self.status_lbl.setStyleSheet("color: #ff4444;")

    def _on_receiver_accept(self):
        """Transition Receiver UI to waiting state."""
        self.accept_btn.setEnabled(False)
        self.reject_btn.setEnabled(False)
        self.waiting_lbl.show()
        self.hint_lbl.setText("Synchronizing keys with initiator...")

    def mark_completed(self):
        """Called when Dashboard receives pairing_completed signal."""
        self.accept()

    def mark_failed(self, error_message):
        """Called when Dashboard receives pairing_failed signal."""
        if self.role == "receiver":
            self.accept_btn.setEnabled(True)
            self.reject_btn.setEnabled(True)
            self.waiting_lbl.hide()
            self.hint_lbl.setText(f"❌ Handshake failed: {error_message}")
            self.hint_lbl.setStyleSheet("color: #ff4444; font-size: 11px;")

    def _start_pairing_worker(self):
        pin = self.pin_input.text().strip()
        if len(pin) != 6:
            self.status_lbl.setText("PIN must be 6 digits.")
            return
            
        self.pair_btn.setEnabled(False)
        self.pin_input.setEnabled(False)
        self.progress.show()
        self.status_lbl.setText("Connecting...")
        
        self.worker = PairingWorker(self.peer_ip, self.peer_port, pin, 
                                    self.local_node_id, self.local_name,
                                    self.peer_node_id, self.salt, self.local_port)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self, success, message):
        self.progress.hide()
        if success:
            self.accept()
        else:
            self.pair_btn.setEnabled(True)
            self.pin_input.setEnabled(True)
            self.status_lbl.setText(f"Error: {message}")
            self.status_lbl.setStyleSheet("color: #ff4444;")
