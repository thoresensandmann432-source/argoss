#!/usr/bin/env bash
# apply_apk_patch.sh
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Патч для репозитория iliyaqdrwalqu/SiGtRiP:
#   1. Удаляет флаг из всех pip install
#   2. Форматирует Python-файлы через black
#   3. Заменяет workflow-файлы на исправленные версии
#   4. Проверяет наличие критических файлов
#
# Использование:
#   bash apply_apk_patch.sh [путь/к/репо]
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:-.}"
REPO="$(cd "$REPO" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ARGOS APK Patch — pip fix + black format         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "  Репозиторий: $REPO"
echo ""

# ── 1. Удаление из pip install ────────────────────────────

echo "━━━ [1/4] Удаление из pip install ━━━"

remove_pip_user() {
    local file="$1"
    if grep -q -- "--user" "$file" 2>/dev/null; then
        # Удаляем (с пробелом до и после)
        sed -i \
          -e 's/pip install\b/pip install/g' \
          -e 's/pip3 install\b/pip3 install/g' \
          -e 's/python -m pip install\b/python -m pip install/g' \
          -e 's/python3 -m pip install\b/python3 -m pip install/g' \
          -e 's/ / /g' \
          -e 's/ --user$//g' \
          "$file"
        echo "  ✅ удалён: $file"
    fi
}

# Обходим все файлы, содержащие pip install
while IFS= read -r -d '' f; do
    remove_pip_user "$f"
done < <(
    find "$REPO" \
        -not -path "*/.git/*" \
        -not -path "*/.buildozer/*" \
        -not -path "*/node_modules/*" \
        -not -path "*/venv/*" \
        -not -path "*/__pycache__/*" \
        \( -name "*.py" -o -name "*.sh" -o -name "*.yml" -o -name "*.yaml" -o -name "*.bat" \) \
        -print0
)

echo "  ✅ Готово"

# ── 2. Установка и запуск black ───────────────────────────────────

echo ""
echo "━━━ [2/4] Форматирование Python-файлов (black) ━━━"

BLACK_CMD=""
for cmd in black python3-black python-black; do
    if command -v "$cmd" &>/dev/null; then
        BLACK_CMD="$cmd"
        break
    fi
done

if [ -z "$BLACK_CMD" ]; then
    echo "  📦 Устанавливаю black..."
    pip install black --quiet 2>/dev/null || \
    pip3 install black --quiet 2>/dev/null || \
    pip install black --break-system-packages --quiet 2>/dev/null || true
    BLACK_CMD="python3 -m black"
fi

PY_TARGETS=()
for candidate in \
    "src" \
    "main.py" \
    "main_kivy.py" \
    "main_argos_local.py" \
    "telegram_bot.py" \
    "git_push.py" \
    "setup_builder.py" \
    "build.py" \
    "genesis.py" \
    "status_report.py" \
    "cleanup_repo.py" \
    "organize_files.py" \
    "pack_archive.py" \
    "bump_version.py" \
    "awareness.py"
do
    if [ -e "$REPO/$candidate" ]; then
        PY_TARGETS+=("$REPO/$candidate")
    fi
done

if [ ${#PY_TARGETS[@]} -gt 0 ]; then
    $BLACK_CMD \
        --line-length 100 \
        --target-version py310 \
        --quiet \
        "${PY_TARGETS[@]}" 2>/dev/null \
    && echo "  ✅ black: ${#PY_TARGETS[@]} целей отформатировано" \
    || echo "  ⚠️  black завершился с предупреждениями (см. выше)"
else
    echo "  ⚠️  Python-файлы не найдены"
fi

# ── 3. Замена workflow-файлов ─────────────────────────────────────

echo ""
echo "━━━ [3/4] Обновление GitHub Actions workflows ━━━"

WF_DIR="$REPO/.github/workflows"
mkdir -p "$WF_DIR"

for wf in build_apk.yml auto_push.yml status_report.yml; do
    src="$PATCH_DIR/.github/workflows/$wf"
    dst="$WF_DIR/$wf"
    if [ -f "$src" ]; then
        cp "$src" "$dst"
        echo "  ✅ $wf"
    else
        echo "  ⚠️  $wf не найден в патче"
    fi
done

# Также чистим в уже существующих workflows
while IFS= read -r -d '' f; do
    remove_pip_user "$f"
done < <(find "$WF_DIR" -name "*.yml" -print0 2>/dev/null)

echo "  ✅ Workflows обновлены"

# ── 4. Проверка наличия критических файлов ────────────────────────

echo ""
echo "━━━ [4/4] Проверка критических файлов ━━━"

python3 - "$REPO" <<'PYEOF'
import sys
from pathlib import Path

repo = Path(sys.argv[1])
REQUIRED = {
    "main.py":                           "Основной модуль",
    "requirements.txt":                  "Зависимости Python",
    "buildozer.spec":                    "Конфигурация APK",
    "telegram_bot.py":                   "Telegram-бот",
    "src/argos_model.py":                "Локальная нейросеть",
    "git_push.py":                       "Скрипт автопуша",
    "README.md":                         "Документация",
    ".github/workflows/build_apk.yml":   "CI сборка APK",
    ".github/workflows/auto_push.yml":   "CI автопуш",
    ".github/workflows/status_report.yml": "CI отчёт",
}

ok = err = 0
for rel, desc in REQUIRED.items():
    p = repo / rel
    if p.exists():
        print(f"  ✅  {rel:<45} {desc}")
        ok += 1
    else:
        print(f"  ❌  {rel:<45} {desc}  ← ОТСУТСТВУЕТ")
        err += 1

print(f"\n  Итог: {ok} OK / {err} отсутствует")
if err:
    print("\n  💡 Отсутствующие файлы нужно создать вручную.")
    print("     Используйте шаблоны из репозитория или документацию ARGOS.")
PYEOF

# ── Итог ──────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ Патч применён!                                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Следующие шаги:"
echo "    cd $REPO"
echo "    git add -A"
echo "    git commit -m 'fix: remove from pip, black format, fix workflows'"
echo "    git push"
echo ""
