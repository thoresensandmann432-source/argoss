"""
src/ai_failover.py — Автоматическое переключение AI-провайдеров
================================================================
При ошибке провайдера переключается на следующий в очереди.
Поддерживает backoff, статистику и сброс.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

__all__ = ["AIFailover", "ProviderStatus"]

_DEFAULT_ORDER = ["gemini", "gigachat", "yandexgpt", "ollama", "openai", "grok", "watsonx"]
_BACKOFF_SEC = 300  # 5 минут блокировки после ошибки


class ProviderStatus(str, Enum):
    OK   = "ok"
    DOWN = "down"
    SLOW = "slow"


@dataclass
class ProviderStats:
    """Статистика одного провайдера."""
    name: str
    status: ProviderStatus = ProviderStatus.OK
    success_count: int = 0
    error_count: int = 0
    last_error: str = ""
    backoff_until: float = 0.0
    total_latency_ms: float = 0.0

    @property
    def in_backoff(self) -> bool:
        return time.time() < self.backoff_until

    @property
    def avg_latency_ms(self) -> float:
        if self.success_count == 0:
            return 0.0
        return self.total_latency_ms / self.success_count


class AIFailover:
    """
    Менеджер переключения между AI-провайдерами.

    Каждый провайдер регистрируется как ``ask_<name>(prompt)`` метод
    на переданном ``provider_module``.

    Пример::

        failover = AIFailover(provider_module=my_providers)
        result, provider = await failover.ask("Привет!", prefer="gemini")
    """

    def __init__(
        self,
        provider_module: Any = None,
        order: Optional[list[str]] = None,
    ) -> None:
        self._module = provider_module
        self._order = list(order or _DEFAULT_ORDER)
        self._stats: dict[str, ProviderStats] = {
            name: ProviderStats(name=name)
            for name in _DEFAULT_ORDER
        }

    def set_order(self, order: list[str]) -> None:
        """Задаёт приоритет провайдеров."""
        self._order = list(order)
        for name in order:
            if name not in self._stats:
                self._stats[name] = ProviderStats(name=name)

    def stats(self) -> dict[str, ProviderStats]:
        """Возвращает статистику всех провайдеров."""
        return dict(self._stats)

    def reset(self, provider: str) -> None:
        """Сбрасывает backoff и статус провайдера."""
        if provider in self._stats:
            self._stats[provider].backoff_until = 0.0
            self._stats[provider].status = ProviderStatus.OK

    async def ask(
        self,
        prompt: str,
        prefer: Optional[str] = None,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> tuple[str, str]:
        """
        Запрашивает ответ у провайдеров по очереди.

        Args:
            prompt:      Запрос к AI.
            prefer:      Предпочтительный провайдер (пробуется первым).
            max_retries: Максимум попыток на провайдера.
            **kwargs:    Дополнительные аргументы провайдеру.

        Returns:
            (ответ, имя_провайдера)

        Raises:
            RuntimeError: Если все провайдеры недоступны.
        """
        order = self._build_order(prefer)
        last_error: Optional[Exception] = None

        for provider_name in order:
            st = self._stats.setdefault(provider_name, ProviderStats(name=provider_name))

            if st.in_backoff:
                continue

            try:
                result = await self._call_provider(provider_name, prompt, **kwargs)
                st.success_count += 1
                st.status = ProviderStatus.OK
                return result, provider_name

            except Exception as e:
                last_error = e
                st.error_count += 1
                st.last_error = str(e)[:120]
                st.status = ProviderStatus.DOWN
                st.backoff_until = time.time() + _BACKOFF_SEC

        raise RuntimeError(
            f"Все провайдеры недоступны. Последняя ошибка: {last_error}"
        )

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _build_order(self, prefer: Optional[str]) -> list[str]:
        """Строит порядок опроса провайдеров."""
        if prefer:
            rest = [p for p in self._order if p != prefer]
            return [prefer] + rest
        return list(self._order)

    async def _call_provider(self, name: str, prompt: str, **kwargs: Any) -> str:
        """Вызывает ask_<name> на provider_module."""
        if self._module is None:
            raise RuntimeError(f"provider_module не задан")

        method_name = f"ask_{name}"
        method = getattr(self._module, method_name, None)

        if method is None:
            raise RuntimeError(f"Метод {method_name} не найден в provider_module")

        t0 = time.time()
        if asyncio.iscoroutinefunction(method):
            result = await method(prompt, **kwargs)
        else:
            result = method(prompt, **kwargs)

        elapsed_ms = (time.time() - t0) * 1000
        st = self._stats.get(name)
        if st:
            st.total_latency_ms += elapsed_ms

        return str(result)
