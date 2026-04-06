"""src/connectivity/xai_tts.py — xAI TTS синтез речи"""
from __future__ import annotations
import os, time
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

__all__ = ["generate_speech_bytes", "XAI_TTS_ENDPOINT"]

XAI_TTS_ENDPOINT = "https://api.x.ai/v1/audio/speech"
_RETRYABLE = {429, 500, 502, 503, 504}


def generate_speech_bytes(
    text: str,
    language: str = "en",
    voice_id: str = "default",
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> bytes:
    """
    Синтез речи через xAI TTS API.

    Raises:
        RuntimeError: XAI_API_KEY не задан.
        ValueError:   Пустой или слишком длинный текст.
        requests.HTTPError: HTTP-ошибка (не-5xx не повторяется).
    """
    api_key = os.environ.get("XAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY не задан")

    text = text.strip()
    if not text:
        raise ValueError("text не может быть пустым")
    if len(text) > 15000:
        raise ValueError(f"text слишком длинный: {len(text)} символов (макс 15000)")

    if requests is None:
        raise RuntimeError("requests не установлен")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"text": text, "language": language, "voice_id": voice_id}

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        resp = requests.post(XAI_TTS_ENDPOINT, headers=headers,
                             json=payload, timeout=30)
        if resp.ok:
            return resp.content
        # Не повторяем для не-retryable ошибок
        if resp.status_code not in _RETRYABLE:
            resp.raise_for_status()
        last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
        if attempt < max_retries - 1:
            time.sleep(retry_delay * (2 ** attempt))

    raise last_exc  # type: ignore[misc]
