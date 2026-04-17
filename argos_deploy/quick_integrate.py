"""
Quick Integrator - Быстрая интеграция v2.5
Добавляет только .env переменные
"""
import os

env_addition = """
# === ARGOS v2.5 Integration ===
ARGOS_GDRIVE_SAFE=1Mq_igWN3iDSBvRapGjcKqO-zm3gd-hcv
ARGOS_BRIDGE_TOKEN=Generation_2026
ARGOS_WIN_BRIDGE_URL=http://host.docker.internal:5000/exec
ARGOS_MARKET_ENABLED=false
# ================================
"""

with open(".env", "a", encoding="utf-8") as f:
    f.write(env_addition)

print("✅ .env обновлен с переменными v2.5")
print("\nДоступные модули:")
print("  - NeuralSwarm (GPU)")
print("  - LazarusProtocol (Backup)")
print("  - WinBridge (Windows)")
print("  - BrowserConduit (Gemini)")
print("  - MarketEngine (Mining)")
print("\n🔥 Argos v2.5 активирован!")