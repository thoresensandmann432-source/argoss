#!/usr/bin/env bash
# setup_zigbee_rpi.sh — Настройка Zigbee координатора на RPi
# Поддерживает CC2531, CC2652, ConBee II
# Запуск: bash setup_zigbee_rpi.sh

set -e
echo "╔══════════════════════════════════════════════════╗"
echo "║   ARGOS Zigbee — Настройка RPi                    ║"
echo "╚══════════════════════════════════════════════════╝"

# 1. Определяем устройство координатора
COORD=""
for dev in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1; do
    if [ -e "$dev" ]; then
        COORD="$dev"
        echo "[+] Координатор найден: $COORD"
        break
    fi
done

if [ -z "$COORD" ]; then
    echo "[!] Координатор не найден. Подключите CC2531/CC2652/ConBee II и повторите."
    exit 1
fi

# 2. Добавляем пользователя в dialout
USER=${SUDO_USER:-pi}
usermod -a -G dialout "$USER"
echo "[+] Пользователь $USER добавлен в dialout"

# 3. Docker / docker-compose
if ! command -v docker &>/dev/null; then
    echo "[~] Устанавливаю Docker..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "$USER"
fi

# 4. Запускаем zigbee2mqtt
mkdir -p zigbee2mqtt_data
cat > zigbee2mqtt_data/configuration.yaml << EOF
homeassistant: false
permit_join: true
mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://localhost
serial:
  port: $COORD
frontend:
  port: 8080
EOF

docker run -d \
  --name zigbee2mqtt \
  --restart unless-stopped \
  -e TZ=Europe/Moscow \
  --device=$COORD:$COORD \
  -v $(pwd)/zigbee2mqtt_data:/app/data \
  -p 8080:8080 \
  koenkk/zigbee2mqtt

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ zigbee2mqtt запущен!"
echo "  Веб-интерфейс: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "  Настройте .env:"
echo "    ZIGBEE_MQTT_HOST=localhost"
echo "    ZIGBEE_MQTT_PORT=1883"
echo ""
echo "  Затем: python main.py → 'zigbee сопряжение'"
echo "═══════════════════════════════════════════════════"

# 5. Устанавливаем Mosquitto если нет
if ! command -v mosquitto &>/dev/null; then
    apt-get install -y mosquitto mosquitto-clients
    systemctl enable mosquitto
    systemctl start mosquitto
    echo "[+] Mosquitto MQTT брокер установлен"
fi

# 6. Python зависимости
pip3 install paho-mqtt --quiet
echo "[+] paho-mqtt установлен"
