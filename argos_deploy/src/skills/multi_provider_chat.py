"""
multi_provider_chat.py — единый вызов AI-провайдеров через OpenAI SDK.
Команды:
  ai спроси grok <текст>
  ai спроси openai <текст>
  ai спроси groq <текст>
  ai спроси cloudflare <текст>
  ai спроси ollama <текст>
  ai спроси kimi <текст>
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Единый чат через xAI/Grok, OpenAI, Groq, Cloudflare, Ollama и Kimi"

import os
from typing import Optional

try:
    from openai import OpenAI
    _OPENAI_SDK = True
except Exception:
    OpenAI = None  # type: ignore
    _OPENAI_SDK = False

SKILL_NAME = "multi_provider_chat"
SKILL_TRIGGERS = [
    "ai спроси", "ask grok", "ask openai", "ask groq",
    "ask cloudflare", "ask ollama", "ask kimi",
    "grok", "openai", "groq", "cloudflare", "ollama", "kimi",
]


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

        elif p == "groq":
            api_key = os.getenv("GROQ_API_KEY", "").strip()
            if not api_key:
                return "❌ GROQ_API_KEY не задан"
            client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
            model_name = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        elif p == "cloudflare":
            api_key = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
            account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
            if not api_key or not account_id:
                return "❌ CLOUDFLARE_API_TOKEN или CLOUDFLARE_ACCOUNT_ID не задан"
            client = OpenAI(
                api_key=api_key,
                base_url=f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
            )
            model_name = model or os.getenv("CLOUDFLARE_MODEL", "@cf/moonshotai/kimi-k2.5")

        elif p == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip().rstrip("/")
            client = OpenAI(api_key="ollama", base_url=f"{host}/v1")
            model_name = model or os.getenv("OLLAMA_MODEL", "llama3.2:1b")

        elif p == "kimi":
            api_key = os.getenv("KIMI_API_KEY", "").strip()
            if not api_key:
                return "❌ KIMI_API_KEY не задан"
            client = OpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")
            model_name = model or os.getenv("KIMI_MODEL", "kimi-k2.5")

        else:
            return f"❌ неизвестный провайдер: {p}. Доступные: grok, openai, groq, cloudflare, ollama, kimi"

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
            return f"❌ {p} API ({model_name}): {e}"

    def handle_command(self, text: str) -> Optional[str]:
        t = (text or "").strip()
        lt = t.lower()

        providers = ["grok", "openai", "groq", "cloudflare", "ollama", "kimi"]
        for p in providers:
            if f"ai спроси {p}" in lt:
                prompt = t.split(p, 1)[-1].strip()
                if not prompt:
                    return f"Формат: ai спроси {p} <вопрос>"
                return self.ask_ai(prompt, provider=p)
        return None


def handle(text: str, core=None) -> Optional[str]:
    lt = (text or "").lower()
    if not any(k in lt for k in SKILL_TRIGGERS):
        return None
    return MultiProviderChat(core=core).handle_command(text)
