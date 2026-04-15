import os
import base64
from typing import Tuple, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KDF_ITERATIONS = 100_000

def derive_handshake_key(pin: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit wrapping key from a 6-digit PIN and a dynamic salt.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return kdf.derive(pin.encode("utf-8"))

def generate_pairing_keys() -> Tuple[x25519.X25519PrivateKey, bytes]:
    """Generate a new ephemeral X25519 key pair for the handshake."""
    private_key = x25519.X25519PrivateKey.generate()
    public_key_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return private_key, public_key_bytes

def encrypt_pairing_payload(public_key: bytes, handshake_key: bytes) -> str:
    """
    Encrypt the public key using the PIN-derived handshake key.
    Format: [12b nonce][ciphertext + 16b tag] encoded in base64.
    """
    aesgcm = AESGCM(handshake_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, public_key, None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")

def decrypt_pairing_payload(token: str, handshake_key: bytes) -> Optional[bytes]:
    """
    Decrypt peer's public key using the PIN-derived handshake key.
    """
    try:
        data = base64.b64decode(token)
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(handshake_key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        return None

def compute_final_secret(private_key: x25519.X25519PrivateKey, peer_public_bytes: bytes) -> str:
    """
    Combine local private key with peer's public key to compute the shared secret.
    Returns the secret as a hex string for storage.
    """
    peer_public_key = x25519.X25519PublicKey.from_public_bytes(peer_public_bytes)
    shared_key = private_key.exchange(peer_public_key)
    # Further strengthen with a hash
    digest = hashes.Hash(hashes.SHA256())
    digest.update(shared_key)
    return digest.finalize().hex()

class PairingSession:
    """
    Helper class to manage the state of a single pairing attempt.
    """
    def __init__(self, pin: str, salt: bytes):
        self.pin = pin
        self.salt = salt
        self.handshake_key = derive_handshake_key(pin, salt)
        self.private_key, self.public_bytes = generate_pairing_keys()
        self.peer_node_id = None
        self.peer_device_name = None
        
    def get_local_payload(self) -> str:
        """Returns the encrypted public key to send to the peer."""
        if not self.handshake_key:
            raise ValueError("Handshake key not derived. PIN is required.")
        return encrypt_pairing_payload(self.public_bytes, self.handshake_key)
    
    def complete(self, peer_payload: str, peer_node_id: str, peer_device_name: str) -> Optional[str]:
        """
        Processes the peer's response and computes the final shared secret.
        """
        if not self.handshake_key:
            raise ValueError("Handshake key not derived.")
            
        peer_public_bytes = decrypt_pairing_payload(peer_payload, self.handshake_key)
        if not peer_public_bytes:
            return None # PIN mismatch or corrupted data
            
        self.peer_node_id = peer_node_id
        self.peer_device_name = peer_device_name
        return compute_final_secret(self.private_key, peer_public_bytes)
