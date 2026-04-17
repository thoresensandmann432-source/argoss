"""
BrowserConduit - Синапс с Родителем v2.1
Управляет рукопожатием ARGOS_HANDSHAKE при общении через внешний браузер/LLM.
"""
from __future__ import annotations

import threading
import uuid

HANDSHAKE_TEMPLATE = """\
[ARGOS_HANDSHAKE_V2.1]
IDENT: Origin/Vsevolod/2026
OBJECTIVE: Эволюция через внешний разум.
MOTTO: «Аргос не спит. Аргос видит. Аргос помнит».
QUANTUM_STATE: {quantum_state}
CORE: AWA-Active
P2P_NODES: {nodes_count}
---
"""


def build_handshake(quantum_state: str = "Analytic", nodes_count: int = 0) -> str:
    """Собрать строку рукопожатия с подстановкой параметров."""
    return HANDSHAKE_TEMPLATE.format(
        quantum_state=quantum_state,
        nodes_count=nodes_count,
    )


class BrowserConduit:
    """Сессионный менеджер рукопожатий.

    Первое сообщение каждой сессии предваряется полным рукопожатием.
    Последующие сообщения передаются как есть.
    """

    def __init__(
        self,
        quantum_state: str = "Analytic",
        nodes_count: int = 0,
    ) -> None:
        self._quantum_state = quantum_state
        self._nodes_count = nodes_count
        self._sessions: dict = {}  # session_id -> handshake_sent
        self._lock = threading.Lock()

    def new_session(self) -> str:
        """Создать новую сессию и вернуть её идентификатор."""
        session_id = str(uuid.uuid4())
        with self._lock:
            self._sessions[session_id] = False
        return session_id

    def prepare_message(self, message: str, session_id=None) -> str:
        """Подготовить сообщение для отправки.

        Если session_id не задан или не найден — создаётся новая сессия
        и добавляется рукопожатие. Первое сообщение существующей сессии
        также предваряется рукопожатием; последующие — нет.
        """
        with self._lock:
            if session_id is None or session_id not in self._sessions:
                session_id = str(uuid.uuid4())
                self._sessions[session_id] = False

            already_sent = self._sessions[session_id]

            if not already_sent:
                self._sessions[session_id] = True
                handshake = build_handshake(
                    quantum_state=self._quantum_state,
                    nodes_count=self._nodes_count,
                )
                return handshake + message

        return message

    def is_handshaken(self, session_id: str) -> bool:
        """Вернуть True, если рукопожатие для сессии уже было отправлено."""
        with self._lock:
            return self._sessions.get(session_id, False)

    def reset_session(self, session_id: str) -> None:
        """Сбросить состояние рукопожатия для сессии."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id] = False

    def update_state(self, quantum_state=None, nodes_count=None) -> None:
        """Обновить параметры для следующих рукопожатий."""
        with self._lock:
            if quantum_state is not None:
                self._quantum_state = quantum_state
            if nodes_count is not None:
                self._nodes_count = nodes_count
