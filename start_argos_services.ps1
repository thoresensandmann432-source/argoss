# ============================================================
# ARGOS Universal OS — автозапуск сервисов
# Запускает: dashboard_server.py, ngrok, cloudflared
# Запуск: powershell -ExecutionPolicy Bypass -File start_argos_services.ps1
# ============================================================

$ARGOS_DIR = "F:\debug\argoss"
$PYTHON = "F:\debug\argoss\.venv\Scripts\python.exe"
$NGROK = "$env:LOCALAPPDATA\Microsoft\WindowsApps\ngrok.exe"
$CLOUDFLARED = "cloudflared.exe"
$LOG_DIR = "$ARGOS_DIR\logs"

# Создаём директорию логов
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

Write-Host "[ARGOS] Starting services..." -ForegroundColor Cyan

# ── 1. Dashboard Server ──────────────────────────────────────
$dashProc = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*dashboard_server*" }
if (-not $dashProc) {
    Write-Host "[ARGOS] Starting dashboard_server.py on :8081..." -ForegroundColor Green
    Start-Process -FilePath $PYTHON `
        -ArgumentList "dashboard_server.py" `
        -WorkingDirectory $ARGOS_DIR `
        -RedirectStandardOutput "$LOG_DIR\dashboard.log" `
        -RedirectStandardError  "$LOG_DIR\dashboard_err.log" `
        -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "[ARGOS] dashboard_server.py already running (PID $($dashProc.Id))" -ForegroundColor Yellow
}

# ── 2. ngrok ────────────────────────────────────────────────
$ngrokProc = Get-Process -Name "ngrok*" -ErrorAction SilentlyContinue
if (-not $ngrokProc) {
    Write-Host "[ARGOS] Starting ngrok → lastingly-unretreating-lucia.ngrok-free.dev..." -ForegroundColor Green
    Start-Process -FilePath $NGROK `
        -ArgumentList "http --url=lastingly-unretreating-lucia.ngrok-free.dev 8081" `
        -RedirectStandardOutput "$LOG_DIR\ngrok.log" `
        -RedirectStandardError  "$LOG_DIR\ngrok_err.log" `
        -WindowStyle Hidden
    Start-Sleep -Seconds 5
} else {
    Write-Host "[ARGOS] ngrok already running (PID $($ngrokProc.Id))" -ForegroundColor Yellow
}

# ── 3. Cloudflare Tunnel ─────────────────────────────────────
$cfProc = Get-Process -Name "cloudflared*" -ErrorAction SilentlyContinue
if (-not $cfProc) {
    Write-Host "[ARGOS] Starting cloudflared tunnel argos → argosssss.win..." -ForegroundColor Green
    Start-Process -FilePath $CLOUDFLARED `
        -ArgumentList "tunnel run argos" `
        -RedirectStandardOutput "$LOG_DIR\cloudflared.log" `
        -RedirectStandardError  "$LOG_DIR\cloudflared_err.log" `
        -WindowStyle Hidden
    Start-Sleep -Seconds 5
} else {
    Write-Host "[ARGOS] cloudflared already running (PID $($cfProc.Id))" -ForegroundColor Yellow
}

# ── Статус ────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== ARGOS Services Status ===" -ForegroundColor Cyan
Write-Host "Dashboard : http://localhost:8081" -ForegroundColor White
Write-Host "ngrok     : https://lastingly-unretreating-lucia.ngrok-free.dev" -ForegroundColor White
Write-Host "Cloudflare: https://argosssss.win" -ForegroundColor White
Write-Host "wg-easy   : http://172.207.209.134:51824  (https://wg.argosssss.win)" -ForegroundColor White
Write-Host ""

# Проверка доступности
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8081/" -TimeoutSec 3 -UseBasicParsing
    Write-Host "[OK] Dashboard responding (HTTP $($r.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Dashboard not responding yet" -ForegroundColor Yellow
}
