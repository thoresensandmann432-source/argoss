import os
import shlex
content = open("src/connectivity/telegram_bot.py", "r", encoding="utf-8").read()
m = "        except Exception:\\n            pass\\n\\n    async def cmd_tg_health"

new = 1
new = """\n    # APK BUILD\n    def _build_apk_sync(self) -> tuple[bool, str]:\n        import shlex\n        cmd = os.getenv("ARGOS_APK_BUILD_CMD", "").strip()\n        if not cmd:\n            return False, "ARGOS_APK_BUILD_CMD is not set"\n        if not cmd.strip():\n            return False, "ARGOS_APK_BUILD_CMD is empty"\n        try:\n            args = shlex.split(cmd)\n        except ValueError:\n            return False, "ARGOS_APK_BUILD_CMD parse error"\n        try:\n            result = subprocess.run(args, capture_output=True, text=True, timeout=600)\n            if result.returncode != 0:\n                return False, f"Build failed: {result.stderr[:200]}"\n        except subprocess.CalledProcessError as e:\n            return False, f"CalledProcessError: {e}"\n        except Exception as e:\n            return False, f"Build error: {e}"\n        apk_path = self._find_apk_artifact()\n        if not apk_path:\n            return False, "APK file not found after build"\n        return True, apk_path\n\n    def _find_apk_artifact(self) -> str | None:\n        import glob\n        patterns = ["build/bin/*.apk", "bin/*.apk", "*.apk", "build/*.apk", "app/build/outputs/apk/**/*.apk"]\n        for pattern in patterns:\n            matches = glob.glob(pattern, recursive=True)\n            if matches:\n                return sorted(matches, key=os.path.getmtime, reverse=True)[0]\n        return None\n"""
r = "        except Exception:\n            pass\n" + new + "\n    async def cmd_tg_health"
content = content.replace(m, r)
open("src/connectivity/telegram_bot.py", "w", encoding="utf-8").write(content)
print("OK")
