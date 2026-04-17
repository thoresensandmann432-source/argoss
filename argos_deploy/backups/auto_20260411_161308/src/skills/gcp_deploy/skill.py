"""
gcloud skill — развертывание на Google Cloud Run.
"""
import subprocess
import os
import asyncio
import threading

SKILL_NAME = "gcp_deploy"
DESCRIPTION = "Развертывание ARGOS на Google Cloud Run"


async def execute(command: str, project: str = "argos-489214", region: str = "us-central1", **kwargs):
    """Execute gcloud command."""
    if command == "deploy":
        cmd = [
            "gcloud", "run", "deploy", "argos-core",
            "--image", f"us-central1-docker.pkg.dev/{project}/argos-repo/argos-core:latest",
            "--platform", "managed",
            "--region", region,
            "--project", project,
            "--memory", "4Gi",
            "--cpu", "2",
            "--port", "8080",
            "--allow-unauthenticated",
        ]
        env = os.environ.copy()
        env["CLOUDSDK_ACTIVE_CONFIG_NAME"] = project
        proc = await asyncio.create_subprocess_exec(
            *cmd, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return {
            "ok": proc.returncode == 0,
            "output": stdout.decode() if stdout else "",
            "error": stderr.decode() if stderr else "",
        }
    return {"ok": False, "error": f"Unknown command: {command}"}


def handle(text: str, core=None) -> str:
    """Синхронная обёртка для вызова из ArgosCore._run_skill (event-loop-safe)."""
    t = (text or "").lower()
    command = "deploy" if "deploy" in t or "деплой" in t else t.strip()

    result: dict = {}
    exc_holder: list = []

    def _run():
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            result.update(new_loop.run_until_complete(execute(command)))
        except Exception as e:
            exc_holder.append(e)
        finally:
            new_loop.close()

    t_obj = threading.Thread(target=_run, daemon=True)
    t_obj.start()
    t_obj.join(timeout=120)

    if exc_holder:
        return f"❌ gcp_deploy: {exc_holder[0]}"
    if not result:
        return "❌ gcp_deploy: таймаут"
    if result.get("ok"):
        return f"✅ gcp_deploy deploy завершён:\n{result.get('output', '')}"
    return f"❌ gcp_deploy: {result.get('error', 'неизвестная ошибка')}"