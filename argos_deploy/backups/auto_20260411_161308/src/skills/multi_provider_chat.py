"""
multi_provider_chat.py — единый вызов xAI/OpenAI через OpenAI SDK.
Команды:
  ai спроси grok <текст>
  ai спроси openai <текст>
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Единый чат через xAI/Grok и OpenAI"

import os
from typing import Optional

try:
    from openai import OpenAI
    _OPENAI_SDK = True
except Exception:
    OpenAI = None  # type: ignore
    _OPENAI_SDK = False

SKILL_NAME = "multi_provider_chat"
SKILL_TRIGGERS = ["ai спроси", "ask grok", "ask openai", "grok", "openai"]


class MultiProviderChat:
    def __init__(self, core=None):
        self.core = core

    def ask_ai(self, prompt: str, provider: str = "grok", model: Optional[str] = None, temperature: float = 0.7) -> str:
        if not _OPENAI_SDK:
            return "❌ openai SDK не установлен"
        p = (provider or "").strip().lower()
        if p == "grok":
            api_key = (os.getenv("XAI_API_KEY", "") or os.getenv("GROK_API_KEY", "")).strip()
            if not api_key:
                return "❌ XAI_API_KEY/GROK_API_KEY не задан"
            client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
            model_name = model or os.getenv("GROK_MODEL", "").strip() or os.getenv("XAI_MODEL", "grok-4-1-fast-reasoning")
        elif p == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                return "❌ OPENAI_API_KEY не задан"
            client = OpenAI(api_key=api_key)
            model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        else:
            return "❌ provider должен быть grok или openai"

        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Ты полезный и правдивый помощник."},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=1000,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"❌ {p} API: {e}"

    def handle_command(self, text: str) -> Optional[str]:
        t = (text or "").strip()
        lt = t.lower()
        if "ai спроси grok" in lt:
            prompt = t.split("grok", 1)[-1].strip()
            if not prompt:
                return "Формат: ai спроси grok <вопрос>"
            return self.ask_ai(prompt, provider="grok")
        if "ai спроси openai" in lt:
            prompt = t.split("openai", 1)[-1].strip()
            if not prompt:
                return "Формат: ai спроси openai <вопрос>"
            return self.ask_ai(prompt, provider="openai")
        return None


def handle(text: str, core=None) -> Optional[str]:
    lt = (text or "").lower()
    if not any(k in lt for k in SKILL_TRIGGERS):
        return None
    return MultiProviderChat(core=core).handle_command(text)
