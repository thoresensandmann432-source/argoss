# Patch v1.20.5 commands for Argos
# Adds: build apk, tasmota, pr2350, ghost, remember, recall

def handle_v1205_command(self, text):
    t = text.lower().strip()
    if t.startswith("build apk"):
        return self.cmd_build_apk() if hasattr(self, "cmd_build_apk") else "APK not loaded"
    elif t.startswith("tasmota "):
        return self.cmd_tasmota(t.split()[-1]) if hasattr(self, "cmd_tasmota") else "IoT not loaded"
    elif t.startswith("pr2350"):
        return self.cmd_pr2350() if hasattr(self, "cmd_pr2350") else "IoT not loaded"
    elif t.startswith("ghost "):
        return self.cmd_ghost(text[6:]) if hasattr(self, "cmd_ghost") else "C2 not loaded"
    elif t.startswith("remember:"):
        parts = text[9:].split("|")
        if len(parts) == 2:
            return self.remember(parts[0].strip(), parts[1].strip()) if hasattr(self, "remember") else "Memory not loaded"
        return "Format: remember: key | value"
    elif t.startswith("recall "):
        return self.recall(text[7:]) if hasattr(self, "recall") else "Memory not loaded"
    return None
