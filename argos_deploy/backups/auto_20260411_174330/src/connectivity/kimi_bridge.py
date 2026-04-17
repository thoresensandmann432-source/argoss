"""
kimi_bridge.py — Мост для Kimi K2.5 (Moonshot AI) API

Интеграция с Kimi API для ARGOS.
API Docs: https://platform.moonshot.ai/docs

Использование:
    from src.connectivity.kimi_bridge import KimiBridge
    
    kimi = KimiBridge(api_key="sk-...")
    response = kimi.chat("Привет, как дела?")
    
    # Или через генератор (streaming)
    for chunk in kimi.chat_stream("Расскажи о себе"):
        print(chunk, end="")
"""

import os
import requests
import json
from typing import Optional, List, Dict, Generator, Union
from dataclasses import dataclass

from src.argos_logger import get_logger

log = get_logger("argos.kimi")


@dataclass
class KimiMessage:
    """Сообщение для Kimi API."""
    role: str  # "system", "user", "assistant"
    content: str


class KimiBridge:
    """
    Мост для работы с Kimi K2.5 API (Moonshot AI).
    
    Поддерживаемые модели:
      • kimi-k2.5 — последняя версия K2.5
      • kimi-k2 — модель K2
      • kimi-latest — автовыбор
      • moonshot-v1-8k/32k/128k — legacy модели
    """
    
    API_BASE = "https://api.moonshot.cn/v1"
    DEFAULT_MODEL = "kimi-k2.5"
    AVAILABLE_MODELS = [
        "kimi-k2.5",
        "kimi-k2",
        "kimi-latest",
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
    ]
    
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        """
        Инициализация Kimi Bridge.
        
        Args:
            api_key: API ключ от Moonshot. Если None, берётся из KIMI_API_KEY
            model: Название модели (по умолчанию kimi-k2.5)
        """
        self.api_key = api_key or os.getenv("KIMI_API_KEY", "")
        if not self.api_key:
            log.warning("KIMI_API_KEY не задан — Kimi Bridge не активен")
        
        self.model = model if model in self.AVAILABLE_MODELS else self.DEFAULT_MODEL
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        
        # Контекст для диалога
        self._messages: List[Dict] = []
        
        log.info(f"KimiBridge инициализирован: model={self.model}")
    
    @property
    def is_available(self) -> bool:
        """Проверка доступности API."""
        return bool(self.api_key)
    
    def set_system_prompt(self, prompt: str):
        """Устанавливает системный промпт."""
        if not self._messages or self._messages[0]["role"] != "system":
            self._messages.insert(0, {"role": "system", "content": prompt})
        else:
            self._messages[0]["content"] = prompt
    
    def chat(self, 
             message: str, 
             temperature: float = 0.7,
             max_tokens: int = 2048) -> str:
        """
        Отправляет сообщение и получает ответ (blocking).
        
        Args:
            message: Текст сообщения
            temperature: Креативность (0-1)
            max_tokens: Макс. токенов в ответе
            
        Returns:
            Текст ответа от Kimi
        """
        if not self.is_available:
            return "[Kimi] API ключ не настроен (KIMI_API_KEY)"
        
        # Добавляем сообщение пользователя
        self._messages.append({"role": "user", "content": message})
        
        try:
            payload = {
                "model": self.model,
                "messages": self._messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            response = self._session.post(
                f"{self.API_BASE}/chat/completions",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            
            # Сохраняем контекст
            self._messages.append({"role": "assistant", "content": reply})
            
            return reply
            
        except requests.exceptions.RequestException as e:
            log.error(f"Kimi API error: {e}")
            return f"[Kimi Error] {e}"
        except KeyError as e:
            log.error(f"Kimi invalid response: {e}")
            return "[Kimi Error] Неверный формат ответа"
    
    def chat_stream(self, 
                    message: str,
                    temperature: float = 0.7,
                    max_tokens: int = 2048) -> Generator[str, None, None]:
        """
        Отправляет сообщение и получает ответ потоком (streaming).
        
        Args:
            message: Текст сообщения
            temperature: Креативность (0-1)
            max_tokens: Макс. токенов
            
        Yields:
            Части ответа по мере генерации
        """
        if not self.is_available:
            yield "[Kimi] API ключ не настроен"
            return
        
        self._messages.append({"role": "user", "content": message})
        
        try:
            payload = {
                "model": self.model,
                "messages": self._messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            
            full_response = ""
            
            with self._session.post(
                f"{self.API_BASE}/chat/completions",
                json=payload,
                stream=True,
                timeout=120
            ) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if not line:
                        continue
                    
                    line = line.decode('utf-8').strip()
                    if not line.startswith("data: "):
                        continue
                    
                    data = line[6:]  # Убираем "data: "
                    if data == "[DONE]":
                        break
                    
                    try:
                        chunk = json.loads(data)
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            full_response += content
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        continue
            
            # Сохраняем полный ответ
            if full_response:
                self._messages.append({"role": "assistant", "content": full_response})
                
        except requests.exceptions.RequestException as e:
            log.error(f"Kimi streaming error: {e}")
            yield f"[Kimi Error] {e}"
    
    def clear_context(self):
        """Очищает историю диалога (кроме system prompt)."""
        system = [m for m in self._messages if m["role"] == "system"]
        self._messages = system[:1]  # Оставляем только системный промпт
    
    def get_balance(self) -> Dict:
        """Получает баланс аккаунта."""
        if not self.is_available:
            return {"error": "API key not set"}
        
        try:
            response = self._session.get(f"{self.API_BASE}/users/me")
            response.raise_for_status()
            data = response.json()
            return {
                "available": data.get("available", 0),
                "currency": data.get("currency", "CNY"),
            }
        except Exception as e:
            log.error(f"Kimi balance check failed: {e}")
            return {"error": str(e)}
    
    def list_models(self) -> List[str]:
        """Возвращает список доступных моделей."""
        if not self.is_available:
            return self.AVAILABLE_MODELS
        
        try:
            response = self._session.get(f"{self.API_BASE}/models")
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            log.error(f"Kimi models list failed: {e}")
            return self.AVAILABLE_MODELS


class KimiSkillAdapter:
    """Адаптер для интеграции Kimi как навык ARGOS."""
    
    def __init__(self, core=None):
        self.core = core
        self._kimi = None
        self._init_kimi()
    
    def _init_kimi(self):
        """Инициализация Kimi Bridge."""
        try:
            self._kimi = KimiBridge()
            if self._kimi.is_available:
                log.info("KimiSkillAdapter: Kimi доступен")
            else:
                log.warning("KimiSkillAdapter: Kimi не настроен")
        except Exception as e:
            log.error(f"KimiSkillAdapter init error: {e}")
    
    def handle(self, text: str, core=None) -> Optional[str]:
        """Обработчик навыка."""
        if not self._kimi or not self._kimi.is_available:
            return None
        
        # Триггеры для Kimi
        triggers = ["kimi", "кими", "moonshot", "мууншот", "k2.5"]
        if not any(t in text.lower() for t in triggers):
            return None
        
        # Убираем триггер из запроса
        query = text
        for t in triggers:
            query = query.replace(t, "").strip()
        
        if not query:
            return "[Kimi] Привет! Я Kimi K2.5. Задайте ваш вопрос."
        
        # Отправляем в Kimi
        return self._kimi.chat(query)
    
    @property
    def name(self) -> str:
        return "kimi_bridge"
    
    @property
    def version(self) -> str:
        return "1.0.0"


# ══════════════════════════════════════════════════════════════════════════════
# Демо и тестирование
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🌙 Kimi Bridge for ARGOS")
    print("=" * 50)
    
    if not os.getenv("KIMI_API_KEY"):
        print("\n⚠️ Установите KIMI_API_KEY:")
        print("   export KIMI_API_KEY='sk-...'")
        print("\nПолучить ключ: https://platform.moonshot.ai")
        exit(1)
    
    kimi = KimiBridge()
    
    print(f"\n📡 Тестирование Kimi API")
    print(f"   Модель: {kimi.model}")
    print(f"   API: {kimi.API_BASE}")
    
    # Тестовый запрос
    test_msg = "Привет! Какая у тебя модель и версия?"
    print(f"\n📝 Query: {test_msg}")
    print("\n🤖 Response:")
    
    response = kimi.chat(test_msg)
    print(response)
    
    # Тест streaming
    print("\n📝 Streaming test:")
    print("🤖 ", end="", flush=True)
    for chunk in kimi.chat_stream("Скажи 'Тест пройден' три раза"):
        print(chunk, end="", flush=True)
    print()
    
    print("\n✅ Тест завершён")