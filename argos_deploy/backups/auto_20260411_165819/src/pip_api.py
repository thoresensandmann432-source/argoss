"""
pip_api.py — API endpoints для управления pip

Добавляет в ARGOS Web API:
  • POST /api/pip/install — установка пакетов
  • POST /api/pip/uninstall — удаление
  • GET  /api/pip/list — список пакетов
  • GET  /api/pip/outdated — устаревшие
  • GET  /api/pip/check — проверка зависимостей

Использование:
    from src.pip_api import setup_pip_routes
    setup_pip_routes(app, core)
"""

from flask import Flask, jsonify, request
from typing import Optional

def setup_pip_routes(app: Flask, core=None):
    """
    Настройка роутов pip для Flask приложения.
    
    Args:
        app: Flask приложение
        core: Экземпляр ArgosCore (для доступа к менеджеру)
    """
    
    @app.route('/api/pip/install', methods=['POST'])
    def pip_install():
        """Установка пакета."""
        data = request.get_json() or {}
        package = data.get('package')
        version = data.get('version')
        upgrade = data.get('upgrade', False)
        
        if not package:
            return jsonify({"error": "package required"}), 400
        
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        
        success = pm.install(package, version=version, upgrade=upgrade)
        
        return jsonify({
            "success": success,
            "package": package,
            "version": version,
            "upgrade": upgrade
        })
    
    @app.route('/api/pip/uninstall', methods=['POST'])
    def pip_uninstall():
        """Удаление пакета."""
        data = request.get_json() or {}
        package = data.get('package')
        
        if not package:
            return jsonify({"error": "package required"}), 400
        
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        
        success = pm.uninstall(package)
        
        return jsonify({
            "success": success,
            "package": package
        })
    
    @app.route('/api/pip/list', methods=['GET'])
    def pip_list():
        """Список установленных пакетов."""
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        
        packages = pm.list_installed()
        
        return jsonify({
            "count": len(packages),
            "packages": [
                {"name": p.name, "version": p.version}
                for p in packages
            ]
        })
    
    @app.route('/api/pip/outdated', methods=['GET'])
    def pip_outdated():
        """Список устаревших пакетов."""
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        
        packages = pm.list_outdated()
        
        return jsonify({
            "count": len(packages),
            "packages": [
                {
                    "name": p.name,
                    "version": p.version,
                    "latest": p.latest
                }
                for p in packages
            ]
        })
    
    @app.route('/api/pip/check', methods=['GET'])
    def pip_check():
        """Проверка зависимостей ARGOS."""
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        
        deps = pm.check_argos_dependencies()
        
        missing_critical = [p for p, ok in deps["critical"].items() if not ok]
        missing_optional = [p for p, ok in deps["optional"].items() if not ok]
        
        return jsonify({
            "status": "ok" if not missing_critical else "critical_missing",
            "critical": {
                "total": len(deps["critical"]),
                "missing": len(missing_critical),
                "packages": deps["critical"]
            },
            "optional": {
                "total": len(deps["optional"]),
                "missing": len(missing_optional),
                "packages": deps["optional"]
            }
        })
    
    @app.route('/api/pip/info/<package>', methods=['GET'])
    def pip_info(package):
        """Информация о пакете."""
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        
        info = pm.show(package)
        
        if info:
            return jsonify({"found": True, "info": info})
        else:
            return jsonify({"found": False}), 404


# FastAPI версия (для будущего)
try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    
    class PipInstallRequest(BaseModel):
        package: str
        version: Optional[str] = None
        upgrade: bool = False
    
    class PipUninstallRequest(BaseModel):
        package: str
    
    router = APIRouter(prefix="/api/pip", tags=["pip"])
    
    @router.post("/install")
    async def pip_install_fastapi(req: PipInstallRequest):
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        success = pm.install(req.package, version=req.version, upgrade=req.upgrade)
        return {"success": success}
    
    @router.post("/uninstall")
    async def pip_uninstall_fastapi(req: PipUninstallRequest):
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        success = pm.uninstall(req.package)
        return {"success": success}
    
    @router.get("/list")
    async def pip_list_fastapi():
        from src.pip_manager_ext import PipManager
        pm = PipManager()
        packages = pm.list_installed()
        return {"packages": [{"name": p.name, "version": p.version} for p in packages]}
    
except ImportError:
    # FastAPI не установлен, пропускаем
    pass