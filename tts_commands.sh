#!/bin/bash
# tts_commands.sh - Команды для работы с TTS модулем ARGOS

# === Инициализация ===
# Запуск TTS сервера
./arg os tts start

# Проверка статуса
./arg os tts status

# Остановка
./arg os tts stop

# === Управление голосом ===
# Установить голос (示例: ru-RU, en-US)
./arg os tts voice set ru-RU

# Регулировка скорости (0.5 - 2.0)
./arg os tts speed 1.0

# Регулировка высоты тона
./arg os tts pitch 0.0

# === Синтез речи ===
# Озвучить текст
./arg os tts speak "Привет, я ARGOS"

# Сохранить в файл
./arg os tts save "Текст для записи" output.wav

# Озвучить файл
./arg os tts play input.wav

# === Мониторинг ===
# Логи TTS
./arg os tts logs

# Статистика использования
./arg os tts stats
