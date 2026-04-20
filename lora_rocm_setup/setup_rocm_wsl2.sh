#!/usr/bin/env bash
# setup_rocm_wsl2.sh — ROCm 6.x + PyTorch + LoRA stack для WSL2
# Оборудование: AMD RX 580 (gfx803) + RX 560 (gfx803) + Vega11 (gfx902)
# Запуск: bash setup_rocm_wsl2.sh
set -euo pipefail

# ─── Цвета ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }
section() { echo -e "\n${BOLD}══════════════════════════════════════${NC}"; echo -e "${BOLD} $*${NC}"; echo -e "${BOLD}══════════════════════════════════════${NC}"; }

# ─── Определение ОС ──────────────────────────────────────────────────────────
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        OS_VER="${VERSION_CODENAME:-${VERSION_ID:-unknown}}"
    else
        fail "Не удалось определить ОС"
    fi
    info "ОС: ${OS_ID} ${OS_VER}"

    case "$OS_ID" in
        ubuntu) ;;
        debian) ;;
        *) warn "Протестировано только на Ubuntu/Debian. Продолжаем..." ;;
    esac
}

# ─── Проверка WSL2 ────────────────────────────────────────────────────────────
check_wsl() {
    if grep -qi "microsoft" /proc/version 2>/dev/null; then
        ok "WSL2 обнаружен"
    else
        warn "Не WSL2 — скрипт оптимизирован для WSL2, но продолжаем"
    fi
}

# ─── ROCm 6.x ────────────────────────────────────────────────────────────────
install_rocm() {
    section "1/5 Установка ROCm 6.x"

    sudo apt-get update -qq
    sudo apt-get install -y wget gnupg2 software-properties-common lsb-release

    # ROCm 6.1 репозиторий (Ubuntu 22.04 / jammy)
    ROCM_VER="6.1"
    ROCM_DEB_VER="6.1.60100"
    CODENAME=$(lsb_release -cs 2>/dev/null || echo "jammy")

    info "Добавляем ROCm ${ROCM_VER} репозиторий..."
    wget -qO /tmp/amdgpu-install.deb \
        "https://repo.radeon.com/amdgpu-install/${ROCM_VER}/ubuntu/${CODENAME}/amdgpu-install_${ROCM_DEB_VER}-1_all.deb" \
        || fail "Не удалось скачать amdgpu-install. Проверь подключение."

    sudo apt-get install -y /tmp/amdgpu-install.deb
    rm -f /tmp/amdgpu-install.deb

    sudo amdgpu-install --usecase=wsl,rocm --no-dkms -y
    ok "ROCm ${ROCM_VER} установлен"

    # Группы
    sudo usermod -aG video,render "$USER" 2>/dev/null || true
    ok "Пользователь добавлен в группы video, render"
}

# ─── PyTorch + ROCm 6.0 wheel ────────────────────────────────────────────────
install_pytorch() {
    section "2/5 Установка PyTorch с ROCm 6.0"

    # venv в домашней директории
    VENV_DIR="$HOME/argos-lora-env"
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
        ok "Создан venv: $VENV_DIR"
    else
        info "venv уже существует: $VENV_DIR"
    fi

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    pip install --upgrade pip setuptools wheel -q

    info "Устанавливаем PyTorch 2.3 + ROCm 6.0 wheel..."
    pip install torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/rocm6.0 \
        --extra-index-url https://download.pytorch.org/whl/rocm6.0 \
        -q
    ok "PyTorch установлен"
}

# ─── LoRA стек ───────────────────────────────────────────────────────────────
install_lora_stack() {
    section "3/5 Установка LoRA стека"

    source "$HOME/argos-lora-env/bin/activate"

    info "transformers, peft, trl, datasets, accelerate..."
    pip install \
        "transformers>=4.41" \
        "peft>=0.11" \
        "trl>=0.9" \
        "datasets>=2.19" \
        "accelerate>=0.30" \
        "bitsandbytes>=0.43" \
        "sentencepiece" \
        "scipy" \
        "einops" \
        "psutil" \
        -q
    ok "LoRA стек установлен"
}

# ─── Переменные окружения ─────────────────────────────────────────────────────
configure_env() {
    section "4/5 Настройка переменных окружения"

    BASHRC="$HOME/.bashrc"
    ARGOS_ENV_MARKER="# === ARGOS ROCm env ==="

    if grep -q "$ARGOS_ENV_MARKER" "$BASHRC" 2>/dev/null; then
        warn "Переменные уже прописаны в .bashrc — пропускаем"
        return
    fi

    cat >> "$BASHRC" << 'EOF'

# === ARGOS ROCm env ===
# RX 580 / RX 560 — Polaris (gfx803)
export HSA_OVERRIDE_GFX_VERSION=8.0.3
export ROCR_VISIBLE_DEVICES=0,1
export HIP_VISIBLE_DEVICES=0,1
export ROC_ENABLE_PRE_VEGA=1
export PYTORCH_ROCM_DEVICE=0
export PATH="/opt/rocm/bin:$PATH"
export LD_LIBRARY_PATH="/opt/rocm/lib:$LD_LIBRARY_PATH"
# venv ARGOS LoRA
source "$HOME/argos-lora-env/bin/activate" 2>/dev/null || true
# === END ARGOS ROCm env ===
EOF
    ok "Переменные добавлены в ~/.bashrc"
    info "  HSA_OVERRIDE_GFX_VERSION=8.0.3  (gfx803 / Polaris)"
    info "  ROCR_VISIBLE_DEVICES=0,1         (RX 580 + RX 560)"
}

# ─── Проверка GPU ─────────────────────────────────────────────────────────────
verify_gpu() {
    section "5/5 Проверка GPU"

    export HSA_OVERRIDE_GFX_VERSION=8.0.3
    export ROCR_VISIBLE_DEVICES=0,1
    export ROC_ENABLE_PRE_VEGA=1
    export PATH="/opt/rocm/bin:$PATH"

    if command -v rocm-smi &>/dev/null; then
        rocm-smi --showid --showproductname 2>/dev/null || warn "rocm-smi не видит GPU (в WSL2 — норма до ребута)"
    else
        warn "rocm-smi не найден — ROCm возможно не установлен"
    fi

    source "$HOME/argos-lora-env/bin/activate"
    python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'ROCm/CUDA доступен: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(f'  GPU {i}: {p.name} — {p.total_memory // 1024**2} MB')
else:
    print('  GPU не виден. Нужен: source ~/.bashrc && python ...')
    print('  Или задай: export HSA_OVERRIDE_GFX_VERSION=8.0.3')
" 2>&1 || warn "Ошибка при проверке PyTorch — может потребоваться reboot"
}

# ─── Итог ────────────────────────────────────────────────────────────────────
print_summary() {
    echo -e "\n${GREEN}${BOLD}╔══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   ARGOS ROCm Setup — ГОТОВО          ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Следующие шаги:${NC}"
    echo "  1. source ~/.bashrc"
    echo "  2. cd F:/debug/argoss/lora_rocm_setup   (или /mnt/f/debug/argoss/...)"
    echo "  3. python train_lora_rocm.py --quick"
    echo ""
    echo -e "${YELLOW}Если GPU не виден:${NC}"
    echo "  export HSA_OVERRIDE_GFX_VERSION=8.0.3"
    echo "  export ROCR_VISIBLE_DEVICES=0,1"
    echo "  python train_lora_rocm.py --quick"
    echo ""
    echo -e "${YELLOW}Документация:${NC} README_rocm.md"
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}ARGOS Universal OS v2.1.3 — ROCm Setup для RX 580 / RX 560${NC}"
    echo "Дата: $(date '+%Y-%m-%d %H:%M')"
    echo ""

    detect_os
    check_wsl
    install_rocm
    install_pytorch
    install_lora_stack
    configure_env
    verify_gpu
    print_summary
}

main "$@"
