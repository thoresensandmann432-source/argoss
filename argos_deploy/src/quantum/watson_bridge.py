"""
watson_bridge.py — IBM WatsonX AI Bridge (ibm-watsonx-ai)
Команды: режим ии watsonx | watsonx статус

⚠️  ПОЛИТИКА: WatsonX используется ИСКЛЮЧИТЕЛЬНО для работы
    с собственным кодом Аргоса — анализ, генерация, рефакторинг,
    code review, self-healing. Для общих запросов используй Gemini/Ollama.
"""

import os
import re
import threading
from src.argos_logger import get_logger

log = get_logger("argos.watsonx")

try:
    from ibm_watsonx_ai import Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

    WATSONX_OK = True
except ImportError:
    WATSONX_OK = False

AVAILABLE_MODELS = [
    "meta-llama/llama-3-1-70b-instruct",
    "meta-llama/llama-3-1-8b-instruct",
    "ibm/granite-13b-chat-v2",
    "ibm/granite-20b-chat-v2",
]

# Ключевые слова, по которым запрос считается code-задачей Аргоса
_CODE_KEYWORDS = re.compile(
    r"(код|code|python|класс|class|функц|func|def\b|import|баг|bug|ошибк|error|"
    r"исправ|fix|рефакт|refactor|review|анализ|анализ.*код|напиш.*класс|"
    r"напиш.*функ|улучш|optimize|тест|test|src/|argos|колибри|colibri|"
    r"модул|module|скрипт|script|прошив|firmware|asm|assembl)",
    re.IGNORECASE,
)


def is_code_request(text: str) -> bool:
    """Возвращает True если запрос связан с кодом Аргоса."""
    return bool(_CODE_KEYWORDS.search(text))


class WatsonXBridge:
    def __init__(self):
        self.api_key = os.getenv("WATSONX_API_KEY", "")
        self.project_id = os.getenv("WATSONX_PROJECT_ID", "")
        self.url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        self.model_id = os.getenv("WATSONX_MODEL", "meta-llama/llama-3-1-70b-instruct")
        self._model = None
        self._init_model()

    @staticmethod
    def _patch_proxy() -> None:
        """Сбрасываем loopback-прокси для requests (ibm-watsonx-ai использует requests)."""
        bad = ("127.0.0.1:9", "localhost:9", "127.0.0.1:7890", "127.0.0.1:2080")
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                    "http_proxy", "https_proxy", "all_proxy"):
            val = (os.getenv(key) or "").lower()
            if val and any(m in val for m in bad):
                os.environ.pop(key, None)
        # requests уважает NO_PROXY; * = обойти прокси для всех хостов
        if not os.getenv("NO_PROXY"):
            os.environ["NO_PROXY"] = "iam.cloud.ibm.com,us-south.ml.cloud.ibm.com"
            os.environ["no_proxy"] = os.environ["NO_PROXY"]

    def _init_model_inner(self):
        """Внутренняя инициализация — вызывается из потока с таймаутом."""
        creds = Credentials(api_key=self.api_key, url=self.url)
        params = {
            GenParams.DECODING_METHOD: "greedy",
            GenParams.MAX_NEW_TOKENS: 1024,
            GenParams.REPETITION_PENALTY: 1.05,
        }
        self._model = ModelInference(
            model_id=self.model_id,
            params=params,
            credentials=creds,
            project_id=self.project_id,
        )
        log.info("WatsonX: OK (%s)", self.model_id)

    def _init_model(self):
        if not (WATSONX_OK and self.api_key and self.project_id):
            return
        self._patch_proxy()

        error_holder: list = [None]
        done = threading.Event()

        def _worker():
            try:
                self._init_model_inner()
            except Exception as exc:
                error_holder[0] = exc
            finally:
                done.set()

        t = threading.Thread(target=_worker, daemon=True, name="watsonx-init")
        t.start()

        if not done.wait(timeout=12):
            # daemon-поток продолжит работу в фоне, не блокируя старт
            log.warning("WatsonX init: таймаут 12с — IBM Cloud не ответил, пропускаем")
            return

        e = error_holder[0]
        if e is None:
            return  # успех — log уже в _init_model_inner
        err_str = str(e)
        # WSCPA0000E: 403 — Service ID не добавлен в проект
        if "WSCPA0000E" in err_str or "403" in err_str or "not a member" in err_str:
            import re as _re
            sid_match = _re.search(r"ServiceId-[a-f0-9\-]+", err_str)
            sid = sid_match.group(0) if sid_match else "ServiceId из WATSONX_API_KEY"
            log.warning(
                "WatsonX: 403 Forbidden — Service ID не добавлен в проект IBM Cloud.\n"
                "  Исправление:\n"
                "  1. Открой https://dataplatform.cloud.ibm.com/projects/%s/manage\n"
                "  2. Раздел 'Access Control' → 'Add collaborators'\n"
                "  3. Добавь %s с ролью Editor\n"
                "  Или замени WATSONX_API_KEY на IAM-ключ владельца проекта.",
                self.project_id, sid,
            )
        else:
            log.warning("WatsonX init: %s", e)

    @property
    def available(self) -> bool:
        return self._model is not None

    def ask(self, system: str, user: str) -> str | None:
        """
        Запрос к WatsonX.

        ⚠️ ТОЛЬКО для задач с кодом Аргоса.
        Если запрос не связан с кодом — возвращает None
        (управление передаётся Gemini/Ollama).
        """
        if not self.available:
            return None
        if not is_code_request(user):
            log.debug("WatsonX: запрос не code-задача, передаю Gemini/Ollama")
            return None  # не наша задача
        try:
            prompt = (
                f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
                f"{system}\n<|eot_id|>"
                f"<|start_header_id|>user<|end_header_id|>\n"
                f"{user}\n<|eot_id|>"
                f"<|start_header_id|>assistant<|end_header_id|>\n"
            )
            res = self._model.generate_text(prompt=prompt)
            return res.strip() if res else None
        except Exception as e:
            log.error("WatsonX ask: %s", e)
            return None

    def status(self) -> str:
        lines = ["🔷 IBM WatsonX Bridge:"]
        if not WATSONX_OK:
            lines.append("  ❌ Не установлен: pip install ibm-watsonx-ai")
        elif not self.api_key:
            lines.append("  ❌ WATSONX_API_KEY не задан в .env")
        elif not self.project_id:
            lines.append("  ❌ WATSONX_PROJECT_ID не задан в .env")
        elif self.available:
            lines.append(f"  ✅ Подключён: {self.model_id}")
            lines.append(f"  URL: {self.url}")
        else:
            lines.append("  ⚠️ Ошибка инициализации — проверь ключи")
        lines.append(f"  Доступные модели: {', '.join(AVAILABLE_MODELS)}")
        lines.append("  ⚠️ Политика: только для кода Аргоса (анализ/генерация/fix)")
        return "\n".join(lines)
