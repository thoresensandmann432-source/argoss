"""src/quantum/watson_bridge.py — IBM WatsonX мост ARGOS"""
from __future__ import annotations
import os, re
from typing import Optional

__all__ = ["WatsonXBridge", "is_code_request"]

_CODE_KEYWORDS = {
    "python","код","code","функцию","функция","class","def ","import",
    "asm","assembly","ассемблер","script","скрипт","напиши","исправь",
    "реализуй","create","implement","fix","bug","ошибку","src/",".py",
    "arm","x86","avr","c++","java","rust","golang","bash",
}


def is_code_request(text: str) -> bool:
    """Определяет является ли запрос запросом на код."""
    t = text.lower()
    return any(k in t for k in _CODE_KEYWORDS)


class WatsonXBridge:
    """IBM WatsonX/Granite LLM мост (только для кода)."""

    _POLICY = "Политика: WatsonX используется только для кода"

    def __init__(self) -> None:
        self._api_key    = os.environ.get("WATSONX_API_KEY", "")
        self._project_id = os.environ.get("WATSONX_PROJECT_ID", "")
        self._url        = os.environ.get("WATSONX_URL",
                                          "https://us-south.ml.cloud.ibm.com")
        self._model      = "ibm/granite-13b-instruct-v2"

    def is_configured(self) -> bool:
        return bool(self._api_key and self._project_id)

    def ask(self, system: str, prompt: str, max_tokens: int = 512) -> Optional[str]:
        """Отправляет запрос к Watson. Только для кода."""
        if not is_code_request(prompt):
            return None  # только для кода
        if not self.is_configured():
            return None
        try:
            import requests
            token = self._get_iam_token()
            if not token:
                return None
            url = f"{self._url}/ml/v1/text/generation?version=2023-05-29"
            payload = {
                "model_id": self._model,
                "input": f"{system}\n\n{prompt}",
                "parameters": {"max_new_tokens": max_tokens, "temperature": 0.2},
                "project_id": self._project_id,
            }
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json=payload, timeout=60,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            return results[0].get("generated_text", "").strip() if results else None
        except Exception:
            return None

    def status(self) -> str:
        cfg = "✅" if self.is_configured() else "❌"
        return (
            f"🔬 WatsonX Bridge\n"
            f"  Настроен: {cfg}\n"
            f"  Модель  : {self._model}\n"
            f"  только для кода — {self._POLICY}"
        )

    def _get_iam_token(self) -> Optional[str]:
        try:
            import requests
            r = requests.post(
                "https://iam.cloud.ibm.com/identity/token",
                data={"apikey": self._api_key,
                      "grant_type": "urn:ibm:params:oauth:grant-type:apikey"},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("access_token")
        except Exception:
            return None
