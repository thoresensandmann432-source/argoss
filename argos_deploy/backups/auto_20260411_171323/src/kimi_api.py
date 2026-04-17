"""
kimi_api.py — Web API endpoints для Kimi K2.5

Добавляет в ARGOS Web API:
  • POST /api/kimi/chat — текстовый запрос
  • POST /api/kimi/chat/stream — потоковый ответ
  • GET  /api/kimi/models — список моделей
  • GET  /api/kimi/agents — Claude агенты через Kimi
  • POST /api/kimi/agent/execute — выполнить агента
  • GET  /api/kimi/status — статус API

Использование:
    from src.kimi_api import setup_kimi_routes
    setup_kimi_routes(app, core)
"""

import json
from flask import Flask, Response, jsonify, request, stream_with_context

def setup_kimi_routes(app: Flask, core=None):
    """
    Настройка роутов Kimi для Flask приложения.
    
    Args:
        app: Flask приложение
        core: Экземпляр ArgosCore
    """
    
    # Глобальный экземпляр Kimi Bridge (создаётся при первом запросе)
    _kimi_instance = None
    
    def get_kimi():
        """Ленивая инициализация Kimi Bridge."""
        nonlocal _kimi_instance
        if _kimi_instance is None:
            from src.connectivity.kimi_bridge import KimiBridge
            _kimi_instance = KimiBridge()
        return _kimi_instance
    
    @app.route('/api/kimi/status', methods=['GET'])
    def kimi_status():
        """Статус Kimi API."""
        try:
            kimi = get_kimi()
            return jsonify({
                "available": kimi.is_available,
                "model": kimi.model,
                "api_base": kimi.API_BASE
            })
        except Exception as e:
            return jsonify({"error": str(e), "available": False}), 500
    
    @app.route('/api/kimi/models', methods=['GET'])
    def kimi_models():
        """Список доступных моделей."""
        try:
            kimi = get_kimi()
            models = kimi.list_models()
            return jsonify({"models": models})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/kimi/chat', methods=['POST'])
    def kimi_chat():
        """Обычный текстовый запрос к Kimi."""
        data = request.get_json() or {}
        message = data.get('message')
        system_prompt = data.get('system')
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 2048)
        
        if not message:
            return jsonify({"error": "message required"}), 400
        
        try:
            kimi = get_kimi()
            
            if not kimi.is_available:
                return jsonify({"error": "Kimi API not configured"}), 503
            
            # Устанавливаем системный промпт если передан
            if system_prompt:
                kimi.set_system_prompt(system_prompt)
            
            answer = kimi.chat(
                message, 
                temperature=temperature, 
                max_tokens=max_tokens
            )
            
            return jsonify({
                "response": answer,
                "model": kimi.model,
                "tokens": max_tokens
            })
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/kimi/chat/stream', methods=['POST'])
    def kimi_chat_stream():
        """Потоковый ответ от Kimi (Server-Sent Events)."""
        data = request.get_json() or {}
        message = data.get('message')
        system_prompt = data.get('system')
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 2048)
        
        if not message:
            return jsonify({"error": "message required"}), 400
        
        try:
            kimi = get_kimi()
            
            if not kimi.is_available:
                return jsonify({"error": "Kimi API not configured"}), 503
            
            # Устанавливаем системный промпт если передан
            if system_prompt:
                kimi.set_system_prompt(system_prompt)
            
            def generate():
                """Генератор для SSE."""
                for chunk in kimi.chat_stream(message, temperature=temperature, max_tokens=max_tokens):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            
            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/kimi/agent/find', methods=['POST'])
    def kimi_find_agent():
        """Поиск Claude агента через API."""
        data = request.get_json() or {}
        task = data.get('task')
        
        if not task:
            return jsonify({"error": "task required"}), 400
        
        try:
            # Используем интегратор ARGOS
            if core and hasattr(core, 'integrator'):
                agent = core.integrator.get_claude_agent(task)
                if agent:
                    return jsonify({
                        "found": True,
                        "agent": agent
                    })
            
            # Fallback через Kimi напрямую
            kimi = get_kimi()
            if kimi.is_available:
                prompt = f"""Какой Claude агент из библиотеки лучше всего подходит для задачи: {task}?
                
Доступные категории:
- programming-languages (python, javascript, c++, etc.)
- devops-infrastructure (docker, kubernetes, ci/cd)
- security (audit, pentest)
- data-ai (ml, data science)

Ответь кратко: название категории и почему."""
                
                response = kimi.chat(prompt)
                return jsonify({
                    "found": False,
                    "recommendation": response
                })
            
            return jsonify({"found": False})
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/kimi/agent/execute', methods=['POST'])
    def kimi_agent_execute():
        """Выполнить задачу через Kimi как агента."""
        data = request.get_json() or {}
        task = data.get('task')
        agent_type = data.get('agent_type', 'general')
        
        # payload для команды
        payload = data.get('payload', {})
        
        if not task:
            return jsonify({"error": "task required"}), 400
        
        try:
            kimi = get_kimi()
            
            if not kimi.is_available:
                return jsonify({"error": "Kimi API not configured"}), 503
            
            # Формируем системный промпт на основе типа агента
            system_prompts = {
                'programming': 'Ты senior software engineer. Пишешь чистый, документированный код.',
                'security': 'Ты cybersecurity эксперт. Анализируешь уязвимости и даёшь рекомендации.',
                'devops': 'Ты DevOps инженер. Знаешь Docker, K8s, CI/CD лучшие практики.',
                'data': 'Ты data scientist. Работаешь с pandas, numpy, ML моделями.',
                'general': 'Ты полезный ассистент. Помогаешь с задачами пользователя.'
            }
            
            system = system_prompts.get(agent_type, system_prompts['general'])
            
            # Добавляем payload в запрос если есть
            task_with_payload = task
            if payload:
                task_with_payload += f"\n\nДополнительные параметры: {json.dumps(payload, ensure_ascii=False)}"
            
            kimi.set_system_prompt(system)
            response = kimi.chat(task_with_payload, temperature=0.5)
            
            return jsonify({
                "response": response,
                "agent_type": agent_type,
                "model": kimi.model
            })
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/kimi/balance', methods=['GET'])
    def kimi_balance():
        """Проверка баланса аккаунта."""
        try:
            kimi = get_kimi()
            balance = kimi.get_balance()
            return jsonify(balance)
        except Exception as e:
            return jsonify({"error": str(e)}), 500


# FastAPI версия
try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    from typing import Optional
    
    class KimiChatRequest(BaseModel):
        message: str
        system: Optional[str] = None
        temperature: float = 0.7
        max_tokens: int = 2048
        payload: Optional[dict] = None
    
    class KimiAgentRequest(BaseModel):
        task: str
        agent_type: str = "general"
        payload: Optional[dict] = None
    
    fastapi_router = APIRouter(prefix="/api/kimi", tags=["kimi"])
    
    @fastapi_router.get("/status")
    async def kimi_status_fastapi():
        from src.connectivity.kimi_bridge import KimiBridge
        kimi = KimiBridge()
        return {"available": kimi.is_available, "model": kimi.model}
    
    @fastapi_router.post("/chat")
    async def kimi_chat_fastapi(req: KimiChatRequest):
        from src.connectivity.kimi_bridge import KimiBridge
        kimi = KimiBridge()
        
        if not kimi.is_available:
            raise HTTPException(503, "Kimi API not configured")
        
        if req.system:
            kimi.set_system_prompt(req.system)
        
        # Добавляем payload если есть
        message = req.message
        if req.payload:
            message += f"\n\nPayload: {json.dumps(req.payload, ensure_ascii=False)}"
        
        answer = kimi.chat(message, temperature=req.temperature, max_tokens=req.max_tokens)
        return {"response": answer}
    
    @fastapi_router.post("/agent/execute")
    async def kimi_agent_fastapi(req: KimiAgentRequest):
        from src.connectivity.kimi_bridge import KimiBridge
        kimi = KimiBridge()
        
        if not kimi.is_available:
            raise HTTPException(503, "Kimi API not configured")
        
        # Формируем промпт
        system_prompts = {
            'programming': 'Ты senior software engineer.',
            'security': 'Ты cybersecurity эксперт.',
            'devops': 'Ты DevOps инженер.',
            'data': 'Ты data scientist.',
            'general': 'Ты полезный ассистент.'
        }
        
        kimi.set_system_prompt(system_prompts.get(req.agent_type, system_prompts['general']))
        
        # payload в запросе
        message = req.task
        if req.payload:
            message += f"\n\nДополнительные параметры: {json.dumps(req.payload, ensure_ascii=False)}"
        
        response = kimi.chat(message)
        return {"response": response, "agent_type": req.agent_type}

except ImportError:
    pass