# ============================================================
#  ARGOS Universal OS — Windows PowerShell Launcher
#  Запуск из папки проекта с автоопределением устройств
# ============================================================

param(
    [string]$Mode = "--no-gui",
    [switch]$GUI,
    [switch]$Dashboard,
    [switch]$Docker
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "ARGOS Universal OS"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      ARGOS UNIVERSAL OS — WINDOWS LAUNCH     ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── 1. Найти папку проекта ────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = $ScriptDir

# Ищем main.py вверх по дереву
$SearchDir = $ScriptDir
for ($i = 0; $i -lt 5; $i++) {
    if (Test-Path "$SearchDir\main.py") {
        $ProjectDir = $SearchDir
        break
    }
    $SearchDir = Split-Path -Parent $SearchDir
}

Write-Host "📁 Папка проекта: $ProjectDir" -ForegroundColor Green
Set-Location $ProjectDir

# ── 2. Проверить Python ───────────────────────────────────
$Python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $Python = $cmd
                Write-Host "✅ Python: $ver" -ForegroundColor Green
                break
            }
        }
    } catch {}
}

if (-not $Python) {
    Write-Host "❌ Python 3.10+ не найден!" -ForegroundColor Red
    Write-Host "   Скачай: https://python.org/downloads" -ForegroundColor Yellow
    Read-Host "Нажми Enter для выхода"
    exit 1
}

# ── 3. Обнаружение USB/COM устройств ─────────────────────
Write-Host ""
Write-Host "🔌 Сканирование устройств..." -ForegroundColor Cyan

# COM порты
$ComPorts = [System.IO.Ports.SerialPort]::GetPortNames()
if ($ComPorts.Count -gt 0) {
    Write-Host "✅ COM порты найдены:" -ForegroundColor Green
    $ComPorts | ForEach-Object { Write-Host "   📡 $_" -ForegroundColor White }
    $env:ARGOS_COM_PORTS = $ComPorts -join ","
} else {
    Write-Host "⚠️  COM порты не найдены" -ForegroundColor Yellow
}

# USB устройства через WMI
$UsbDevices = Get-WmiObject Win32_USBControllerDevice -ErrorAction SilentlyContinue |
    ForEach-Object { [Wmi]$_.Dependent } |
    Where-Object { $_.Name -match "Arduino|ESP|STM|CH340|CP210|FTDI|Prolific|Serial" } |
    Select-Object Name, DeviceID

if ($UsbDevices) {
    Write-Host "✅ USB устройства найдены:" -ForegroundColor Green
    $UsbDevices | ForEach-Object {
        Write-Host "   🔌 $($_.Name)" -ForegroundColor White
    }
    $env:ARGOS_USB_DEVICES = ($UsbDevices | Select-Object -ExpandProperty Name) -join ";"
} else {
    Write-Host "⚠️  Программируемые USB устройства не найдены" -ForegroundColor Yellow
}

# ADB устройства
try {
    $AdbDevices = & adb devices 2>$null | Select-String -Pattern "device$"
    if ($AdbDevices) {
        Write-Host "✅ ADB устройства:" -ForegroundColor Green
        $AdbDevices | ForEach-Object { Write-Host "   📱 $_" -ForegroundColor White }
        $env:ARGOS_ADB_AVAILABLE = "1"
    }
} catch {
    Write-Host "⚠️  ADB не найден" -ForegroundColor Yellow
}

# Ollama
try {
    $OllamaResp = Invoke-WebRequest -Uri "http://localhost:11434" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "✅ Ollama запущена: http://localhost:11434" -ForegroundColor Green
    $env:OLLAMA_HOST = "http://localhost:11434"
} catch {
    Write-Host "⚠️  Ollama не запущена — запускаю..." -ForegroundColor Yellow
    try {
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep 3
        Write-Host "✅ Ollama запущена" -ForegroundColor Green
        $env:OLLAMA_HOST = "http://localhost:11434"
    } catch {
        Write-Host "⚠️  Ollama не установлена: https://ollama.com" -ForegroundColor Yellow
    }
}

# Docker
try {
    $DockerInfo = & docker info 2>$null
    if ($DockerInfo) {
        Write-Host "✅ Docker доступен" -ForegroundColor Green
        $env:ARGOS_DOCKER_AVAILABLE = "1"
    }
} catch {
    Write-Host "⚠️  Docker не запущен" -ForegroundColor Yellow
}

# ── 4. Загрузить .env ─────────────────────────────────────
Write-Host ""
Write-Host "⚙️  Загружаю конфигурацию..." -ForegroundColor Cyan

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            if ($val -ne "") {
                [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
    }
    Write-Host "✅ .env загружен" -ForegroundColor Green
} else {
    Write-Host "⚠️  .env не найден — копирую из .env.example" -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "   Отредактируй .env и перезапусти" -ForegroundColor Yellow
        notepad ".env"
        Read-Host "Нажми Enter после сохранения .env"
    }
}

# ── 5. Установить зависимости ─────────────────────────────
$PsutilCheck = & $Python -c "import psutil" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "📦 Устанавливаю зависимости..." -ForegroundColor Yellow
    & $Python -m pip install -r requirements.txt --quiet
    Write-Host "✅ Зависимости установлены" -ForegroundColor Green
}

# ── 6. Создать нужные папки ───────────────────────────────
@("data", "logs", "config", "data\patches") | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item -ItemType Directory -Path $_ -Force | Out-Null
    }
}

# ── 7. Экспортируем переменные устройств ─────────────────
if ($ComPorts.Count -gt 0) {
    $env:ARGOS_SERIAL_PORT = $ComPorts[0]
    Write-Host "🔌 Основной COM порт: $($ComPorts[0])" -ForegroundColor Green
}

# ── 8. Выбор режима запуска ───────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════" -ForegroundColor Cyan

if ($Docker) {
    Write-Host "🐳 Режим: Docker" -ForegroundColor Magenta
    & docker-compose -f docker-compose.ollama.yml up -d
    Write-Host "✅ Docker запущен. Dashboard: http://localhost:8080" -ForegroundColor Green
    exit 0
}

if ($GUI) {
    $LaunchMode = ""
    Write-Host "🖥️  Режим: Desktop GUI" -ForegroundColor Magenta
} elseif ($Dashboard) {
    $LaunchMode = "--no-gui --dashboard"
    Write-Host "🌐 Режим: Headless + Dashboard :8080" -ForegroundColor Magenta
} else {
    $LaunchMode = $Mode
    Write-Host "⚙️  Режим: $Mode" -ForegroundColor Magenta
}

Write-Host "══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── 9. Запуск ─────────────────────────────────────────────
Write-Host "🚀 Запускаю ARGOS..." -ForegroundColor Green
Write-Host ""

$args_list = $LaunchMode -split " " | Where-Object { $_ -ne "" }

try {
    if ($args_list.Count -gt 0) {
        & $Python main.py @args_list
    } else {
        & $Python main.py
    }
} catch {
    Write-Host "❌ Ошибка запуска: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "ARGOS завершил работу." -ForegroundColor Yellow
Read-Host "Нажми Enter для выхода"
