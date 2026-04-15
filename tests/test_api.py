"""
tests/test_api.py
──────────────────
Unit tests for the REST API in core/api_server.py
"""

import os
import pytest
import tempfile
import json
import urllib.request
import urllib.error
import time

# ── Isolate DB ──
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["GHOST_DB_PATH"] = _tmp.name

import core.storage as storage
storage.DB_PATH = _tmp.name

from core.api_server import APIServerThread

@pytest.fixture(scope="module", autouse=True)
def fresh_db():
    storage.init_db()
    yield
    os.remove(_tmp.name)

@pytest.fixture(scope="module")
def api_server():
    port = 59091
    token = "test_super_secret_token"
    node_id = "test-node-id"
    device_name = "test-device-name"
    server = APIServerThread(port, token, node_id, device_name)
    server.start()
    time.sleep(0.5)  # Let server bind
    
    yield port, token
    
    server.stop()
    server.quit()
    server.wait()

def do_request(port, path, token, method="GET", payload=None):
    url = f"http://127.0.0.1:{port}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = None
    if payload:
        data = json.dumps(payload).encode("utf-8")
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as res:
        return res.getcode(), json.loads(res.read().decode())

def test_api_unauthorized_no_token(api_server):
    port, _ = api_server
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/stats")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 401

def test_api_unauthorized_wrong_token(api_server):
    port, _ = api_server
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        do_request(port, "/api/stats", "wrong_token")
    assert exc_info.value.code == 403

def test_api_stats(api_server):
    port, token = api_server
    code, res = do_request(port, "/api/stats", token)
    assert code == 200
    assert "total" in res
    assert "pinned" in res

def test_api_push_and_pop(api_server):
    port, token = api_server
    
    # Push item
    code, res = do_request(port, "/api/items", token, method="POST", payload={"text": "Hello CLI"})
    assert code == 201
    assert "id" in res
    
    # Pop item
    code, items = do_request(port, "/api/items?limit=1", token)
    assert code == 200
    assert len(items) >= 1
    recent_item_content = items[0]["content"]
    assert recent_item_content == "Hello CLI"

def test_api_encrypted_items_hidden(api_server):
    port, token = api_server
    
    # Insert secret directly to DB
    item_id = storage.add_item("text", "Secret Pwd")
    storage.update_item_field(item_id, "is_secret", 1)
    
    code, items = do_request(port, "/api/items?limit=5", token)
    assert code == 200
    
    secret_item = next((i for i in items if i.get("id") == item_id), None)
    assert secret_item is not None
    assert secret_item["content"] == "[ENCRYPTED]"

