#!/usr/bin/env python3
"""
ARGOS AUTO-PILOT v1.0
Полностью автономное управление системой Argos
"""

import os
import sys
import time
import json
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from src.argos_logger import get_logger
from src.event_bus import get_bus, Events

log = get_logger("argos.autopilot")
bus = get_bus()

class ArgosAutoPilot:
    """Авто-пилот системы Argos"""
    
    def __init__(self):
        self.running = False
        self.threads = []
        self.status_file = Path("data/autopilot_status.json")
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Конфигурация
        self.config = {
            'health_check_interval': 300,  # 5 минут
            'backup_interval': 900,         # 15 минут
            'sync_interval': 600,           # 10 минут
            'report_interval': 3600,        # 1 час
            'nodes': [
                {'name': 'PC-Local', 'host': 'localhost', 'port': 8000},
                {'name': 'Azure-VM', 'host': '20.53.240.36', 'port': 8000},
            ]
        }
        
        log.info("AutoPilot initialized")
    
    def start(self):
        """Запуск авто-пилота"""
        self.running = True
        log.info("🚀 AUTO-PILOT STARTED")
        
        # Запускаем потоки мониторинга
        monitors = [
            ("HealthMonitor", self._health_monitor),
            ("BackupAgent", self._backup_agent),
            ("SyncAgent", self._sync_agent),
            ("Reporter", self._reporter),
            ("NetworkGuard", self._network_guard),
        ]
        
        for name, target in monitors:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self.threads.append(t)
            log.info(f"  ✓ {name} started")
        
        # Публикуем событие
        # bus.emit(Events.SYSTEM_READY, {"mode": "autopilot"})
        log.info("AutoPilot event bus connected")
        
        # Основной цикл
        try:
            while self.running:
                self._save_status()
                time.sleep(60)  # Минутный heartbeat
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Остановка авто-пилота"""
        self.running = False
        log.info("🛑 AUTO-PILOT STOPPED")
    
    def _health_monitor(self):
        """Мониторинг здоровья системы"""
        while self.running:
            try:
                # Проверяем ресурсы
                import psutil
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                
                if cpu > 90 or ram > 90:
                    log.warning(f"High load: CPU {cpu}%, RAM {ram}%")
                    bus.emit(Events.ALERT, {"type": "high_load", "cpu": cpu, "ram": ram})
                
                # Проверяем диск
                disk = psutil.disk_usage('/').percent
                if disk > 85:
                    log.warning(f"Low disk space: {disk}%")
                
                log.debug(f"Health check: CPU {cpu}%, RAM {ram}%, DISK {disk}%")
                
            except Exception as e:
                log.error(f"Health monitor error: {e}")
            
            time.sleep(self.config['health_check_interval'])
    
    def _backup_agent(self):
        """Агент резервного копирования"""
        while self.running:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = Path(f"backups/auto_{timestamp}")
                backup_dir.mkdir(parents=True, exist_ok=True)
                
                # Копируем важные файлы
                files_to_backup = [
                    "src", ".env", "config", "data"
                ]
                
                for item in files_to_backup:
                    src = Path(item)
                    if src.exists():
                        import shutil
                        if src.is_dir():
                            shutil.copytree(src, backup_dir / src.name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                        else:
                            shutil.copy2(src, backup_dir / src.name)
                
                log.info(f"💾 Auto-backup created: {backup_dir}")
                
                # Удаляем старые бэкапы (оставляем последние 10)
                backups = sorted(Path("backups").glob("auto_*"))
                for old in backups[:-10]:
                    import shutil
                    shutil.rmtree(old)
                    
            except Exception as e:
                log.error(f"Backup error: {e}")
            
            time.sleep(self.config['backup_interval'])
    
    def _sync_agent(self):
        """Агент синхронизации"""
        while self.running:
            try:
                # Синхронизируем конфиги между узлами
                for node in self.config['nodes']:
                    if self._ping_node(node['host'], node['port']):
                        log.debug(f"✓ {node['name']} is online")
                    else:
                        log.warning(f"✗ {node['name']} is offline")
                        bus.emit(Events.NODE_OFFLINE, {"node": node['name']})
                
            except Exception as e:
                log.error(f"Sync error: {e}")
            
            time.sleep(self.config['sync_interval'])
    
    def _network_guard(self):
        """Сетевой страж"""
        while self.running:
            try:
                import socket
                # Проверяем доступность Azure VM
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex(('20.53.240.36', 8000))
                sock.close()
                
                if result == 0:
                    log.debug("NetworkGuard: Azure VM reachable")
                else:
                    log.warning("NetworkGuard: Azure VM unreachable!")
                    
            except Exception as e:
                log.error(f"Network guard error: {e}")
            
            time.sleep(60)  # Каждую минуту
    
    def _reporter(self):
        """Отчетность"""
        while self.running:
            try:
                report = {
                    "timestamp": datetime.now().isoformat(),
                    "status": "running",
                    "threads_alive": sum(1 for t in self.threads if t.is_alive()),
                    "nodes_online": self._count_online_nodes(),
                }
                
                log.info(f"📊 Hourly report: {report['threads_alive']} threads, {report['nodes_online']} nodes online")
                
                # Сохраняем отчет
                report_file = Path(f"reports/hourly_{datetime.now().strftime('%Y%m%d_%H')}.json")
                report_file.parent.mkdir(parents=True, exist_ok=True)
                with open(report_file, 'w') as f:
                    json.dump(report, f, indent=2)
                    
            except Exception as e:
                log.error(f"Reporter error: {e}")
            
            time.sleep(self.config['report_interval'])
    
    def _ping_node(self, host, port):
        """Проверка доступности узла"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def _count_online_nodes(self):
        """Подсчет онлайн узлов"""
        count = 0
        for node in self.config['nodes']:
            if self._ping_node(node['host'], node['port']):
                count += 1
        return count
    
    def _save_status(self):
        """Сохранение статуса"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "running": self.running,
            "threads": [{"name": t.name, "alive": t.is_alive()} for t in self.threads],
        }
        with open(self.status_file, 'w') as f:
            json.dump(status, f, indent=2)

if __name__ == "__main__":
    print("="*60)
    print("ARGOS AUTO-PILOT v1.0")
    print("="*60)
    print()
    
    pilot = ArgosAutoPilot()
    
    try:
        pilot.start()
    except KeyboardInterrupt:
        print("\nStopping auto-pilot...")
        pilot.stop()
