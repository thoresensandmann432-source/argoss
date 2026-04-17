"""
IoT Flasher + APK Builder Module
v1.20.5 Features → v2.1.3 Integration
"""
import os
import subprocess
import requests
import threading
from typing import Optional

class IoTFlasher:
    """Tasmota OTA + ESP/PR2350 flashing via esptool"""
    
    def __init__(self, report_callback=None):
        self.report = report_callback or print
        
    def tasmota_ota(self, ip: str, version: str = "latest") -> dict:
        """OTA update Tasmota device"""
        try:
            url = f"http://{ip}/cm?cmnd=Upgrade%201"
            if version != "latest":
                url = f"http://{ip}/cm?cmnd=Upgrade%20{version}"
            
            r = requests.get(url, timeout=10)
            result = {
                "device": ip,
                "status": r.status_code,
                "response": r.text[:200]
            }
            self.report(f"TASMOTA_OTA: {ip} → {r.status_code}")
            return result
        except Exception as e:
            self.report(f"TASMOTA_ERR: {str(e)}")
            return {"error": str(e)}
    
    def pr2350_flash_id(self) -> dict:
        """Check PR2350/ESP chip ID via esptool"""
        try:
            # Ensure esptool installed
            subprocess.run(["pip", "install", "esptool", "-q"], check=True)
            
            res = subprocess.check_output(
                "esptool.py flash_id",
                shell=True,
                stderr=subprocess.STDOUT,
                timeout=30
            ).decode('utf-8')
            
            self.report(f"PR2350_ID: {res[:100]}")
            return {"success": True, "output": res}
        except Exception as e:
            self.report(f"PR2350_ERR: {str(e)}")
            return {"error": str(e)}
    
    def flash_firmware(self, port: str, firmware_path: str, chip: str = "auto") -> dict:
        """Flash firmware to ESP device"""
        try:
            cmd = f"esptool.py --chip {chip} --port {port} write_flash 0x0 {firmware_path}"
            res = subprocess.check_output(
                cmd,
                shell=True,
                stderr=subprocess.STDOUT,
                timeout=120
            ).decode('utf-8')
            
            self.report(f"FLASH_OK: {port}")
            return {"success": True, "output": res}
        except Exception as e:
            self.report(f"FLASH_FAIL: {str(e)}")
            return {"error": str(e)}


class APKBuilder:
    """Android APK builder via Buildozer"""
    
    def __init__(self, notify_callback=None):
        self.is_building = False
        self.notify = notify_callback or print
        self.build_log = "/tmp/buildozer.log"
        
    def setup_sdk(self):
        """Auto-link Android SDK tools"""
        sdk_tools = "/root/.buildozer/android/platform/android-sdk/build-tools"
        if os.path.exists(sdk_tools):
            versions = sorted(os.listdir(sdk_tools))
            if versions:
                latest = os.path.join(sdk_tools, versions[-1])
                subprocess.run(f"ln -sf {latest}/aidl /usr/local/bin/aidl", shell=True)
                
        # Link buildozer
        if os.path.exists("/root/.local/bin/buildozer"):
            subprocess.run("ln -sf /root/.local/bin/buildozer /usr/local/bin/buildozer", shell=True)
    
    def build(self, project_path: str = ".", send_file_callback=None) -> threading.Thread:
        """Start APK build in background thread"""
        if self.is_building:
            raise RuntimeError("Build already in progress")
        
        def _build_task():
            self.is_building = True
            self.notify("⚙️ [FACTORY]: Starting Buildozer...")
            self.setup_sdk()
            
            try:
                with open(self.build_log, "w") as log:
                    process = subprocess.Popen(
                        "yes | buildozer android debug",
                        shell=True,
                        cwd=project_path,
                        stdout=log,
                        stderr=subprocess.STDOUT
                    )
                    process.wait()
                
                if process.returncode == 0:
                    # Find built APK
                    apk_dir = os.path.join(project_path, "bin")
                    if os.path.exists(apk_dir):
                        apks = [f for f in os.listdir(apk_dir) if f.endswith(".apk")]
                        if apks:
                            apk_path = os.path.join(apk_dir, apks[0])
                            self.notify(f"✅ Build complete: {apks[0]}")
                            if send_file_callback:
                                send_file_callback(apk_path)
                            return
                    
                    self.notify("✅ Build complete (APK location unknown)")
                else:
                    self.notify(f"❌ Build failed (exit {process.returncode})")
                    
            except Exception as e:
                self.notify(f"❌ Build error: {str(e)}")
            finally:
                self.is_building = False
        
        thread = threading.Thread(target=_build_task, daemon=True)
        thread.start()
        return thread
    
    def get_logs(self, lines: int = 50) -> str:
        """Get last N lines of build log"""
        try:
            with open(self.build_log, "r") as f:
                return "\n".join(f.readlines()[-lines:])
        except:
            return "No logs available"
