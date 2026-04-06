#!/usr/bin/env bash
# apply_patch.sh — применить патч к репозиторию ARGOS
# Использование: bash apply_patch.sh [путь/к/репо]
set -e

PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:-.}"

echo "══════════════════════════════════════════════"
echo "  🔱 ARGOS Patch Applicator"
echo "  Репо: $REPO"
echo "══════════════════════════════════════════════"

copy() {
    local src="$PATCH_DIR/$1"
    local dst="$REPO/$1"
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "  ✅ $1"
}

echo ""
echo "📁 Применяю файлы..."

# Connectivity bridges
copy src/connectivity/email_bridge.py
copy src/connectivity/sms_bridge.py
copy src/connectivity/websocket_bridge.py
copy src/connectivity/web_scraper.py
copy src/connectivity/aiogram_bridge.py
copy src/connectivity/socket_transport.py
copy src/connectivity/messenger_router.py
copy src/connectivity/ipc_hub.py

# Interface
copy src/interface/fastapi_dashboard.py

# Src-level
copy src/awareness.py

# Root-level
copy bump_version.py
copy pytest.ini

echo ""
echo "📦 Проверка зависимостей..."
python3 -c "import pytest_asyncio" 2>/dev/null && echo "  ✅ pytest-asyncio" || {
    echo "  ⚠️  Устанавливаю pytest-asyncio..."
    pip install pytest-asyncio --quiet
}

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ Патч применён успешно!"
echo ""
echo "  Следующие шаги:"
echo "  1. cd $REPO"
echo "  2. python -m pytest tests/ -v --tb=short"
echo "  3. python scripts/health_check.py"
echo "══════════════════════════════════════════════"
