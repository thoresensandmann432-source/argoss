"""
win_host_tool.py — Клиент для win_bridge_host.py (Windows HTTP bridge)
Отправляет команды на хост-машину через REST API.
"""
import os
import requests

URL = os.getenv("ARGOS_WIN_BRIDGE_URL", "http://localhost:5757/cmd")


def run_on_host(cmd: str) -> str:
    """Выполняет команду на Windows-хосте через bridge."""
    token = os.getenv("ARGOS_BRIDGE_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.post(URL, json={"cmd": cmd}, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("output", "")
    except requests.exceptions.ConnectionError:
        return "Ошибка: win_bridge_host не запущен на хосте"
    except Exception as e:
        return f"Ошибка: {e}"


if __name__ == "__main__":
    import sys
    cmd = " ".join(sys.argv[1:]) or "echo hello"
    print(run_on_host(cmd))
