#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.parse
import urllib.error

def get_settings():
    settings_path = os.path.expanduser("~/.config/dotghostboard/settings.json")
    if not os.path.exists(settings_path):
        print("Error: DotGhostBoard settings not found. Start the app first.", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading settings: {e}", file=sys.stderr)
        sys.exit(1)

def request_api(method: str, path: str, token: str, port: int, payload: dict = None):
    url = f"http://127.0.0.1:{port}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    data = None
    if payload:
        data = json.dumps(payload).encode("utf-8")
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            return json.loads(res_body)
    except urllib.error.URLError as e:
        print(f"Error connecting to DotGhostBoard API: {e}", file=sys.stderr)
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'), file=sys.stderr)
        print("Is the API server enabled in settings?", file=sys.stderr)
        sys.exit(1)

def cmd_push(text: str, token: str, port: int):
    res = request_api("POST", "/api/items", token, port, payload={"text": text})
    print(f"Pushed item. ID: {res.get('id')}")

def cmd_pop(token: str, port: int):
    res = request_api("GET", "/api/items?limit=1", token, port)
    if not res:
        print("Clipboard is empty.")
    else:
        # Check if encrypted
        item = res[0]
        if item.get("content") == "[ENCRYPTED]":
            print("Error: The top item is encrypted and cannot be popped via CLI.")
            sys.exit(1)
        print(item.get("content", ""))

def main():
    if len(sys.argv) < 2:
        print("Usage: dotghost <push|pop> [text...]")
        print("  dotghost push \"my string\"")
        print("  dotghost pop")
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    
    settings = get_settings()
    if not settings.get("api_enabled"):
        print("Error: API Server is not enabled. Go to Settings -> API to enable it.", file=sys.stderr)
        sys.exit(1)
        
    port = settings.get("api_port", 9090)
    token = settings.get("api_token", "")
    
    if not token:
        print("Error: No API token found in settings.", file=sys.stderr)
        sys.exit(1)

    if cmd == "push":
        if len(sys.argv) < 3:
            print("Usage: dotghost push \"text to copy\"")
            sys.exit(1)
        text = " ".join(sys.argv[2:])
        cmd_push(text, token, port)
    elif cmd == "pop":
        cmd_pop(token, port)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
