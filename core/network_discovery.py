import socket
import logging
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QThread

# Zeroconf imports
try:
    from zeroconf import ServiceBrowser, Zeroconf, ServiceInfo, IPVersion
except ImportError:
    logging.warning("[Network] zeroconf not installed. Discovery will not work.")
    Zeroconf = None
    ServiceBrowser = None
    ServiceInfo = None
    IPVersion = None

_SERVICE_TYPE = "_dotghost._tcp.local."


def get_local_ip() -> str:
    """Attempt to get the local LAN IP address by connecting to a public DNS."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # We don't actually send data, just need a routable endpoint to determine the local interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class NetworkDiscoverySignals(QObject):
    device_discovered = pyqtSignal(str, dict)  # node_id, data
    device_removed = pyqtSignal(str)           # node_id


class DotGhostDiscovery(QThread):
    """
    Background QThread that:
      1. Advertises this device's presence via mDNS (zeroconf).
      2. Browses the local network for other devices broadcasting the DotGhost service.
    """
    
    def __init__(self, port: int, device_name: str, node_id: str, parent=None):
        super().__init__(parent)
        self.port = port
        self.device_name = device_name
        self.node_id = node_id
        
        self.signals = NetworkDiscoverySignals()
        
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.info: Optional[ServiceInfo] = None
        self._running = False
        
        # Track discovered devices by their mdns name
        self.discovered_devices: Dict[str, dict] = {} 

    def run(self):
        if not Zeroconf:
            print("[Discovery] Zeroconf library missing. Aborting mDNS thread.")
            return

        self._running = True
        try:
            self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        except Exception as e:
            print(f"[Discovery] Failed to start Zeroconf: {e}")
            return
            
        local_ip = get_local_ip()
        
        properties = {
            b'node_id': self.node_id.encode('utf-8'),
            b'device_name': self.device_name.encode('utf-8'),
            b'version': b'1',
        }
        
        instance_name = f"{self.node_id}.{_SERVICE_TYPE}"
        
        try:
            self.info = ServiceInfo(
                type_=_SERVICE_TYPE,
                name=instance_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties=properties,
                server=f"{self.node_id}.local."
            )
            
            self.zeroconf.register_service(self.info)
            print(f"[Discovery] Advertising service on {local_ip}:{self.port}")
            
            # Start browsing
            self.browser = ServiceBrowser(self.zeroconf, _SERVICE_TYPE, self)
            
            # Keep thread alive
            while self._running:
                QThread.msleep(500)
                
        except Exception as e:
            print(f"[Discovery] Error in mDNS thread: {e}")

    def stop(self):
        self._running = False
        if self.zeroconf:
            if self.info:
                try:
                    self.zeroconf.unregister_service(self.info)
                except Exception:
                    pass
            if self.browser:
                self.browser.cancel()
            try:
                self.zeroconf.close()
            except Exception:
                pass
            print("[Discovery] Unregistered and stopped.")

    # ── Zeroconf Listener Interface ─────────────────────────────────────────

    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        if name in self.discovered_devices:
            node_id = self.discovered_devices[name].get('node_id', name)
            del self.discovered_devices[name]
            self.signals.device_removed.emit(node_id)
            print(f"[Discovery] Device disconnected: {node_id}")

    def add_service(self, zc: Zeroconf, type_: str, name: str):
        try:
            info = zc.get_service_info(type_, name)
            if not info:
                return
                
            props = {k.decode('utf-8'): v.decode('utf-8') for k, v in info.properties.items()}
            
            # Ignore ourselves
            if props.get('node_id') == self.node_id:
                return
                
            srv_ip = socket.inet_ntoa(info.addresses[0]) if info.addresses else None
            if not srv_ip:
                return
                
            data = {
                'node_id': props.get('node_id', 'unknown'),
                'device_name': props.get('device_name', 'Unknown Device'),
                'port': info.port,
                'ip': srv_ip
            }
            
            self.discovered_devices[name] = data
            self.signals.device_discovered.emit(data['node_id'], data)
            print(f"[Discovery] Discovered peer: {data['device_name']} at {data['ip']}:{data['port']}")
            
        except Exception as e:
            print(f"[Discovery] Error parsing new service {name}: {e}")

    def update_service(self, zc: Zeroconf, type_: str, name: str):
        # Could handle metadata updates (e.g. name change) here
        pass
