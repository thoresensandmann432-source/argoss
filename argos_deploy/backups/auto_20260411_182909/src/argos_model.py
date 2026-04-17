"""
argos_model.py — Собственная модель Аргоса
  Создаёт, обучает, сохраняет и использует локальную нейросеть
  на основе накопленных диалогов из SQLite-памяти.

  Архитектура:
    - Эмбеддинг слой (TF-IDF / sentence-transformers)
    - Классификатор намерений (sklearn / torch)
    - Файн-тюнинг на диалогах из памяти
    - Экспорт в ONNX для использования без зависимостей

  Команды:
    модель статус
    модель обучить
    модель сохранить
    модель загрузить
    модель спросить [вопрос]
    модель экспорт
    модель версия
"""

from __future__ import annotations

import os
import json
import time
import pickle
import hashlib
import threading
import math
import platform
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Optional

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


log = get_logger("argos.model")

# Директории
MODEL_DIR = Path("data/argos_model")
MODEL_FILE = MODEL_DIR / "argos_intent_model.pkl"
VECTORIZER_FILE = MODEL_DIR / "argos_vectorizer.pkl"
META_FILE = MODEL_DIR / "model_meta.json"
TRAINING_LOG = MODEL_DIR / "training_history.jsonl"


# ── ПОПЫТКА ИМПОРТА ML-БИБЛИОТЕК ─────────────────────────
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report

    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False
    log.warning("sklearn не установлен: pip install scikit-learn")

try:
    import numpy as np

    NUMPY_OK = True
except ImportError:
    NUMPY_OK = False

try:
    from src.quantum.quantum_ml import QuantumDecisionEngine, QuantumIntentHead, QISKIT_OK

    QUANTUM_MODEL_OK = True
except Exception:
    QuantumDecisionEngine = None
    QuantumIntentHead = None
    QISKIT_OK = False
    QUANTUM_MODEL_OK = False


class ArgosModelMeta:
    """Метаданные модели — версия, дата, точность."""

    def __init__(self):
        self.version = "0.0.0"
        self.trained_at = None
        self.accuracy = 0.0
        self.samples = 0
        self.classes = []
        self.git_hash = ""
        self.quantum_enabled = False
        self.quantum_backend = ""
        self.quantum_policy = ""
        self.quantum_head_enabled = False
        self.quantum_head_accuracy = 0.0
        self.quantum_head_classes = []
        self.quantum_head_reason = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "trained_at": self.trained_at,
            "accuracy": self.accuracy,
            "samples": self.samples,
            "classes": self.classes,
            "git_hash": self.git_hash,
            "quantum_enabled": self.quantum_enabled,
            "quantum_backend": self.quantum_backend,
            "quantum_policy": self.quantum_policy,
            "quantum_head_enabled": self.quantum_head_enabled,
            "quantum_head_accuracy": self.quantum_head_accuracy,
            "quantum_head_classes": self.quantum_head_classes,
            "quantum_head_reason": self.quantum_head_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ArgosModelMeta":
        m = cls()
        m.version = d.get("version", "0.0.0")
        m.trained_at = d.get("trained_at")
        m.accuracy = d.get("accuracy", 0.0)
        m.samples = d.get("samples", 0)
        m.classes = d.get("classes", [])
        m.git_hash = d.get("git_hash", "")
        m.quantum_enabled = bool(d.get("quantum_enabled", False))
        m.quantum_backend = d.get("quantum_backend", "")
        m.quantum_policy = d.get("quantum_policy", "")
        m.quantum_head_enabled = bool(d.get("quantum_head_enabled", False))
        m.quantum_head_accuracy = float(d.get("quantum_head_accuracy", 0.0))
        m.quantum_head_classes = list(d.get("quantum_head_classes", []))
        m.quantum_head_reason = d.get("quantum_head_reason", "")
        return m


class ArgosOwnModel:
    """
    Собственная ML-модель Аргоса.
    Обучается на диалогах из памяти SQLite.
    Может отвечать на вопросы автономно, без внешнего API.
    """

    def __init__(self, core=None):
        self.core = core
        self._pipeline: Optional[object] = None
        self._meta = ArgosModelMeta()
        self._lock = threading.Lock()
        self._quantum_engine = self._create_quantum_engine()
        self._quantum_head = None
        self._quantum_reducer = None
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self._load_if_exists()

    def _create_quantum_engine(self):
        if not QUANTUM_MODEL_OK:
            return None
        try:
            return QuantumDecisionEngine()
        except Exception as e:
            log.warning("Квантовый движок недоступен: %s", e)
            return None

    # ── ЗАГРУЗКА / СОХРАНЕНИЕ ─────────────────────────────

    def _load_if_exists(self):
        """Загружает модель при старте если она уже существует."""
        if MODEL_FILE.exists() and META_FILE.exists():
            try:
                with open(MODEL_FILE, "rb") as f:
                    self._pipeline = pickle.load(f)
                with open(META_FILE, "r", encoding="utf-8") as f:
                    self._meta = ArgosModelMeta.from_dict(json.load(f))
                log.info(
                    "Собственная модель загружена: v%s, точность=%.2f%%, образцов=%d",
                    self._meta.version,
                    self._meta.accuracy * 100,
                    self._meta.samples,
                )
            except Exception as e:
                log.warning("Не удалось загрузить модель: %s", e)
                self._pipeline = None

    def save(self) -> str:
        """Сохраняет модель и метаданные на диск."""
        if self._pipeline is None:
            return "❌ Нет обученной модели для сохранения."
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            with open(MODEL_FILE, "wb") as f:
                pickle.dump(self._pipeline, f)
            with open(META_FILE, "w", encoding="utf-8") as f:
                json.dump(self._meta.to_dict(), f, ensure_ascii=False, indent=2)
            size_kb = MODEL_FILE.stat().st_size // 1024
            log.info("Модель сохранена: %s (%d KB)", MODEL_FILE, size_kb)
            return (
                f"💾 Модель сохранена:\n"
                f"  Файл: {MODEL_FILE}\n"
                f"  Размер: {size_kb} KB\n"
                f"  Версия: {self._meta.version}\n"
                f"  Точность: {self._meta.accuracy * 100:.1f}%"
            )
        except Exception as e:
            return f"❌ Ошибка сохранения модели: {e}"

    # ── СБОР ДАННЫХ ───────────────────────────────────────

    def _collect_training_data(self) -> tuple[list[str], list[str]]:
        """
        Собирает обучающие данные из SQLite-памяти Аргоса.
        Использует историю диалогов: вопрос → категория намерения.
        """
        texts, labels = [], []

        # 1. Встроенный базовый датасет (работает без памяти)
        builtin = {
            "system": [
                "статус системы",
                "чек-ап",
                "список процессов",
                "сколько памяти",
                "загрузка cpu",
                "температура",
                "статус дисков",
                "здоровье системы",
                "мониторинг",
                "отчёт системы",
                "использование ram",
            ],
            "file": [
                "покажи файлы",
                "список файлов",
                "прочитай файл",
                "создай файл",
                "удали файл",
                "найди файл",
                "открой директорию",
                "скопируй файл",
                "переименуй",
                "размер файла",
                "содержимое папки",
            ],
            "network": [
                "сканируй сеть",
                "статус сети",
                "мой ip",
                "ping",
                "открытые порты",
                "сетевые подключения",
                "интернет работает",
                "скорость интернета",
                "arp таблица",
                "маршруты",
                "dns запрос",
            ],
            "ai": [
                "привет",
                "как дела",
                "что ты умеешь",
                "помоги мне",
                "объясни",
                "расскажи про",
                "что такое",
                "кто такой",
                "как работает",
                "переведи",
                "напиши текст",
                "сгенерируй",
                "придумай",
            ],
            "memory": [
                "запомни",
                "что ты знаешь",
                "найди в памяти",
                "граф знаний",
                "забудь",
                "мои заметки",
                "история диалогов",
                "запиши факт",
                "что я говорил",
                "предыдущий разговор",
            ],
            "iot": [
                "iot статус",
                "умный дом",
                "включи свет",
                "выключи",
                "температура датчик",
                "zigbee",
                "mqtt",
                "умная система",
                "добавь устройство",
                "статус устройств",
            ],
            "build": [
                "собрать апк",
                "build apk",
                "собери exe",
                "компиляция",
                "сборка проекта",
                "deploy",
                "выпусти версию",
                "сборка docker",
            ],
            "git": [
                "git статус",
                "git коммит",
                "git пуш",
                "создай ветку",
                "merge",
                "pull request",
                "история коммитов",
                "отмени коммит",
            ],
        }

        for label, examples in builtin.items():
            for ex in examples:
                texts.append(ex)
                labels.append(label)

        # 2. Данные из SQLite-памяти Аргоса
        if self.core and hasattr(self.core, "db") and self.core.db:
            try:
                history = self.core.db.get_chat_history(limit=500)
                for row in history:
                    role = row.get("role", "")
                    text = row.get("text", "") or ""
                    category = row.get("category", "") or "ai"
                    if role == "user" and len(text) > 3:
                        texts.append(text)
                        labels.append(category if category in builtin else "ai")
                log.info("Загружено %d образцов из SQLite", len(history))
            except Exception as e:
                log.warning("Не удалось загрузить историю из SQLite: %s", e)

        # 3. Данные из файлов навыков (названия → категории)
        skills_dir = Path("src/skills")
        if skills_dir.exists():
            for skill_file in skills_dir.glob("*.py"):
                name = skill_file.stem.replace("_", " ")
                texts.append(f"запусти навык {name}")
                labels.append("skill")

        log.info("Итого обучающих образцов: %d", len(texts))
        return texts, labels

    def _probability_entropy(self, probabilities: list[float]) -> float:
        if not probabilities:
            return 0.0
        total = 0.0
        for value in probabilities:
            p = max(1e-9, float(value))
            total -= p * np.log2(p) if NUMPY_OK else p * math.log(p, 2)
        max_entropy = np.log2(len(probabilities)) if NUMPY_OK else math.log(len(probabilities), 2)
        if max_entropy <= 0:
            return 0.0
        return float(total / max_entropy)

    def _quantum_features_from_text(self, text: str, probabilities: list[float]) -> list[float]:
        sorted_probs = sorted((float(x) for x in probabilities), reverse=True)
        top1 = sorted_probs[0] if sorted_probs else 0.0
        top2 = sorted_probs[1] if len(sorted_probs) > 1 else 0.0
        margin = max(0.0, min(1.0, top1 - top2))
        entropy = self._probability_entropy(sorted_probs)
        length_norm = min(len((text or "").split()) / 16.0, 1.0)
        confidence_signal = (top1 * 2.0) - 1.0
        margin_signal = (margin * 2.0) - 1.0
        uncertainty_signal = (entropy * 2.0) - 1.0
        length_signal = (length_norm * 2.0) - 1.0
        return [confidence_signal, margin_signal, uncertainty_signal, length_signal]

    def _quantum_route(self, text: str, probabilities: list[float]) -> dict:
        if self._quantum_engine is None:
            return {
                "enabled": False,
                "label": "execute_local",
                "backend": "disabled",
                "ok": False,
                "reason": "quantum_engine_unavailable",
                "features": [],
                "probabilities": {"00": 1.0},
            }

        features = self._quantum_features_from_text(text, probabilities)
        result = self._quantum_engine.decide(features)
        return {
            "enabled": True,
            "label": result.label,
            "backend": result.backend,
            "ok": result.ok,
            "reason": result.reason,
            "features": result.features,
            "probabilities": result.probabilities,
            "bitstring": result.bitstring,
        }

    def _apply_quantum_policy(self, confidence: float, quantum_label: str) -> float:
        policy_weights = {
            "execute_local": 1.0,
            "delegate_p2p": 0.92,
            "ask_cloud": 0.82,
            "defer": 0.68,
        }
        adjusted = confidence * policy_weights.get(quantum_label, 0.85)
        return max(0.0, min(1.0, float(adjusted)))

    def _pad_quantum_vector(self, vector) -> list[float]:
        values = [float(x) for x in list(vector)]
        values = values[:4]
        while len(values) < 4:
            values.append(0.0)
        scale = max((abs(v) for v in values), default=1.0) or 1.0
        return [max(-1.0, min(1.0, v / scale)) for v in values]

    def _train_quantum_head(self, pipeline, x_train, y_train, x_test, y_test) -> tuple[Optional[float], str]:
        self._quantum_head = None
        self._quantum_reducer = None

        classes = sorted(set(y_train))
        if self._quantum_engine is None or not QUANTUM_MODEL_OK:
            return None, "quantum_engine_unavailable"
        if len(classes) > 4:
            return None, f"слишком много классов: {len(classes)}"

        try:
            tfidf = pipeline.named_steps["tfidf"]
            x_train_tfidf = tfidf.transform(x_train)
            x_test_tfidf = tfidf.transform(x_test)
            n_features = int(x_train_tfidf.shape[1])
            n_components = max(1, min(4, n_features - 1)) if n_features > 1 else 1
            reducer = TruncatedSVD(n_components=n_components, random_state=42)
            reduced_train = reducer.fit_transform(x_train_tfidf)
            reduced_test = reducer.transform(x_test_tfidf)

            head = QuantumIntentHead(decision_engine=self._quantum_engine)
            head.fit([self._pad_quantum_vector(row) for row in reduced_train], y_train)

            predicted = [
                head.predict(self._pad_quantum_vector(row)).intent
                for row in reduced_test
            ]
            accuracy = (
                sum(1 for pred, true in zip(predicted, y_test) if pred == true) / len(y_test)
                if y_test else 0.0
            )
            self._quantum_head = head
            self._quantum_reducer = reducer
            return float(accuracy), ""
        except Exception as e:
            log.warning("Quantum head training skipped: %s", e)
            self._quantum_head = None
            self._quantum_reducer = None
            return None, str(e)

    def _predict_with_quantum_head(self, text: str) -> Optional[dict]:
        if self._pipeline is None or self._quantum_head is None or self._quantum_reducer is None:
            return None
        try:
            tfidf = self._pipeline.named_steps["tfidf"]
            features = tfidf.transform([text])
            reduced = self._quantum_reducer.transform(features)[0]
            prediction = self._quantum_head.predict(self._pad_quantum_vector(reduced))
            return {
                "intent": prediction.intent,
                "confidence": float(prediction.confidence),
                "label_probabilities": prediction.label_probabilities,
                "bitstring": prediction.bitstring,
                "backend": prediction.backend,
                "ok": prediction.ok,
                "reason": prediction.reason,
            }
        except Exception as e:
            log.warning("Quantum head predict failed: %s", e)
            return None

    def _winbridge_status(self) -> dict:
        if platform.system() != "Windows":
            return {
                "enabled": False,
                "configured": False,
                "reachable": False,
                "details": "не Windows",
            }

        configured = os.getenv("ARGOS_WIN_BRIDGE", "on").strip().lower() in (
            "1", "true", "on", "yes", "да"
        )
        if not configured:
            return {
                "enabled": False,
                "configured": False,
                "reachable": False,
                "details": "отключён через ARGOS_WIN_BRIDGE",
            }

        bridge_url = os.getenv("ARGOS_WIN_BRIDGE_URL", "http://localhost:5000/exec")
        token = os.getenv("ARGOS_BRIDGE_TOKEN", "Generation_2026")
        payload = json.dumps({"cmd": "echo ARGOS_BRIDGE_OK"}).encode("utf-8")
        request = urllib.request.Request(
            bridge_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=2.5) as response:
                body = response.read().decode("utf-8", errors="replace")
                ok = response.status == 200 and "ARGOS_BRIDGE_OK" in body
                return {
                    "enabled": True,
                    "configured": True,
                    "reachable": ok,
                    "details": bridge_url if ok else f"{bridge_url} ответил без маркера",
                }
        except urllib.error.URLError as e:
            return {
                "enabled": True,
                "configured": True,
                "reachable": False,
                "details": str(e.reason),
            }
        except Exception as e:
            return {
                "enabled": True,
                "configured": True,
                "reachable": False,
                "details": str(e),
            }

    # ── ОБУЧЕНИЕ ──────────────────────────────────────────

    def train(self) -> str:
        """
        Обучает модель на собранных данных.
        Возвращает отчёт с точностью.
        """
        if not SKLEARN_OK:
            return "❌ Для обучения модели нужен scikit-learn:\n" "  pip install scikit-learn numpy"

        log.info("Начинаю обучение собственной модели...")
        start = time.time()

        texts, labels = self._collect_training_data()
        if len(texts) < 10:
            return f"❌ Недостаточно данных для обучения: {len(texts)} образцов (нужно минимум 10)."

        # Разбивка на train/test
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=0.2, random_state=42, stratify=labels
            )
        except ValueError:
            # Если классов слишком мало для stratify
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=0.2, random_state=42
            )

        # Построение pipeline: TF-IDF + LogisticRegression
        pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        max_features=5000,
                        analyzer="word",
                        sublinear_tf=True,
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000,
                        C=5.0,
                        solver="lbfgs",
                    ),
                ),
            ]
        )

        with self._lock:
            pipeline.fit(X_train, y_train)
            accuracy = pipeline.score(X_test, y_test)
            self._pipeline = pipeline

        elapsed = time.time() - start

        # Автоверсия на основе точности и хэша данных
        data_hash = hashlib.md5("|".join(sorted(set(texts))).encode()).hexdigest()[:8]
        version_major = int(accuracy * 10)
        self._meta.version = f"1.{version_major}.0+{data_hash}"
        self._meta.trained_at = datetime.now().isoformat()
        self._meta.accuracy = accuracy
        self._meta.samples = len(texts)
        self._meta.classes = sorted(set(labels))
        self._meta.quantum_enabled = self._quantum_engine is not None
        self._meta.quantum_backend = (
            getattr(self._quantum_engine, "backend_name", "")
            if self._quantum_engine is not None
            else ""
        )
        self._meta.quantum_policy = "hybrid_quantum_router_v1"
        quantum_head_accuracy, quantum_head_reason = self._train_quantum_head(
            pipeline,
            X_train,
            y_train,
            X_test,
            y_test,
        )
        self._meta.quantum_head_enabled = self._quantum_head is not None
        self._meta.quantum_head_accuracy = float(quantum_head_accuracy or 0.0)
        self._meta.quantum_head_classes = sorted(set(y_train)) if self._quantum_head is not None else []
        self._meta.quantum_head_reason = quantum_head_reason or ""

        # Логируем в history
        try:
            with open(TRAINING_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._meta.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

        report = ""
        try:
            y_pred = pipeline.predict(X_test)
            report = classification_report(y_test, y_pred, zero_division=0)
        except Exception:
            pass

        result = (
            f"🧠 МОДЕЛЬ ОБУЧЕНА:\n"
            f"  Версия:   {self._meta.version}\n"
            f"  Образцов: {len(texts)} (train={len(X_train)}, test={len(X_test)})\n"
            f"  Классов:  {len(self._meta.classes)} → {', '.join(self._meta.classes)}\n"
            f"  Точность: {accuracy * 100:.1f}%\n"
            f"  Квантовый слой: {'включён' if self._meta.quantum_enabled else 'fallback'}"
            f"{f' ({self._meta.quantum_backend})' if self._meta.quantum_backend else ''}\n"
            f"  Quantum head: {'активен' if self._meta.quantum_head_enabled else 'не активен'}"
            f"{f' ({self._meta.quantum_head_accuracy * 100:.1f}%)' if self._meta.quantum_head_enabled else ''}\n"
            f"  Время:    {elapsed:.1f}с\n"
        )
        if self._meta.quantum_head_reason and not self._meta.quantum_head_enabled:
            result += f"  Причина quantum head: {self._meta.quantum_head_reason}\n"
        if report:
            result += f"\n📊 Отчёт:\n{report}"

        # Автосохранение
        self.save()
        return result

    # ── ИНФЕРЕНС ──────────────────────────────────────────

    def predict(self, text: str) -> dict:
        """
        Предсказывает намерение по тексту.
        Возвращает: {'intent': str, 'confidence': float, 'source': str}
        """
        if self._pipeline is None:
            return {"intent": "unknown", "confidence": 0.0, "source": "no_model"}
        try:
            with self._lock:
                proba = [float(x) for x in self._pipeline.predict_proba([text])[0]]
                classical_intent = self._pipeline.predict([text])[0]
                classical_confidence = float(max(proba))
            head_prediction = self._predict_with_quantum_head(text)
            if head_prediction:
                intent = head_prediction["intent"]
                base_confidence = head_prediction["confidence"]
                source = f"argos_quantum_head_v{self._meta.version}"
            else:
                intent = classical_intent
                base_confidence = classical_confidence
                source = f"argos_hybrid_model_v{self._meta.version}"
            quantum = self._quantum_route(text, proba)
            adjusted_confidence = self._apply_quantum_policy(base_confidence, quantum["label"])
            return {
                "intent": intent,
                "confidence": adjusted_confidence,
                "raw_confidence": base_confidence,
                "classical_intent": classical_intent,
                "classical_confidence": classical_confidence,
                "source": source,
                "quantum": quantum,
                "quantum_head": head_prediction or {
                    "enabled": False,
                    "reason": self._meta.quantum_head_reason or "inactive",
                },
            }
        except Exception as e:
            log.error("predict error: %s", e)
            return {"intent": "unknown", "confidence": 0.0, "source": "error"}

    def ask(self, text: str) -> str:
        """Отвечает на вопрос используя собственную модель."""
        if self._pipeline is None:
            return "❌ Модель не обучена. Выполни: модель обучить"

        result = self.predict(text)
        intent = result["intent"]
        conf = result["confidence"]
        quantum = result.get("quantum", {})
        quantum_label = quantum.get("label", "execute_local")

        # Маршрутизация на ядро Аргоса
        if self.core and conf > 0.5 and quantum_label != "defer":
            try:
                route_prefix = f"[model_routed:{intent}|quantum:{quantum_label}] "
                routed = self.core.process(f"{route_prefix}{text}")
                if routed and routed.get("answer"):
                    return (
                        f"🤖 [Гибридная модель v{self._meta.version}] "
                        f"Намерение: {intent} ({conf*100:.0f}%) | "
                        f"Квантовый маршрут: {quantum_label}\n"
                        f"{routed['answer']}"
                    )
            except Exception:
                pass

        return (
            f"🤖 [Гибридная модель v{self._meta.version}]\n"
            f"Намерение: {intent}\n"
            f"Уверенность: {conf*100:.0f}% "
            f"(сырой сигнал {result.get('raw_confidence', conf)*100:.0f}%)\n"
            f"Квантовый маршрут: {quantum_label}\n"
            f"(Для полного ответа нужен Gemini API или Ollama)"
        )

    # ── СТАТУС / ВЕРСИЯ ───────────────────────────────────

    def status(self) -> str:
        if self._pipeline is None:
            return "🤖 Собственная модель: НЕ ОБУЧЕНА\n" "  Запусти: модель обучить"
        return (
            f"🤖 СОБСТВЕННАЯ ГИБРИДНАЯ МОДЕЛЬ АРГОСА:\n"
            f"  Версия:    {self._meta.version}\n"
            f"  Обучена:   {self._meta.trained_at}\n"
            f"  Точность:  {self._meta.accuracy * 100:.1f}%\n"
            f"  Образцов:  {self._meta.samples}\n"
            f"  Классов:   {len(self._meta.classes)}\n"
            f"  Классы:    {', '.join(self._meta.classes)}\n"
            f"  Квантовый слой: {'да' if self._meta.quantum_enabled else 'нет'}\n"
            f"  Quantum backend: {self._meta.quantum_backend or 'fallback'}\n"
            f"  Quantum policy:  {self._meta.quantum_policy or 'disabled'}\n"
            f"  Quantum head: {('активен' if self._meta.quantum_head_enabled else 'не активен')}\n"
            f"  Quantum head acc: {self._meta.quantum_head_accuracy * 100:.1f}%\n"
            f"  Quantum head classes: {', '.join(self._meta.quantum_head_classes) if self._meta.quantum_head_classes else '-'}\n"
            f"  Quantum head reason: {self._meta.quantum_head_reason or '-'}\n"
            f"  Файл:      {MODEL_FILE}\n"
            f"  Размер:    {MODEL_FILE.stat().st_size // 1024 if MODEL_FILE.exists() else 0} KB"
        )

    def quantum_status(self) -> str:
        if self._pipeline is None:
            return "⚛️ Квантовый статус модели: модель ещё не обучена."
        winbridge = self._winbridge_status()
        engine_state = "готов" if self._quantum_engine is not None else "fallback"
        head_state = "активен" if self._meta.quantum_head_enabled else "не активен"
        return (
            f"⚛️ КВАНТОВЫЙ СТАТУС МОДЕЛИ:\n"
            f"  Quantum engine: {engine_state}\n"
            f"  Backend:        {self._meta.quantum_backend or 'fallback'}\n"
            f"  Router policy:  {self._meta.quantum_policy or 'disabled'}\n"
            f"  Quantum head:   {head_state}\n"
            f"  Head accuracy:  {self._meta.quantum_head_accuracy * 100:.1f}%\n"
            f"  Head classes:   {', '.join(self._meta.quantum_head_classes) if self._meta.quantum_head_classes else '-'}\n"
            f"  Reason:         {self._meta.quantum_head_reason or '-'}\n"
            f"  WinBridge:      {'используется' if winbridge['configured'] else 'не используется'}\n"
            f"  WinBridge API:  {'доступен' if winbridge['reachable'] else 'не отвечает'}\n"
            f"  WinBridge note: {winbridge['details']}"
        )

    def version(self) -> str:
        quantum_suffix = f", quantum={self._meta.quantum_backend or 'fallback'}"
        return f"🤖 Модель Аргоса v{self._meta.version} (точность {self._meta.accuracy*100:.1f}%{quantum_suffix})"

    def history(self) -> str:
        """История всех обучений."""
        if not TRAINING_LOG.exists():
            return "📜 История обучений пуста."
        lines = ["📜 ИСТОРИЯ ОБУЧЕНИЙ:"]
        try:
            with open(TRAINING_LOG, "r", encoding="utf-8") as f:
                for i, line in enumerate(f.readlines()[-10:], 1):
                    m = json.loads(line)
                    lines.append(
                        f"  {i}. v{m['version']} | "
                        f"{m['trained_at'][:16]} | "
                        f"точность={m['accuracy']*100:.1f}% | "
                        f"образцов={m['samples']}"
                    )
        except Exception as e:
            return f"❌ Ошибка чтения истории: {e}"
        return "\n".join(lines)

    def export_onnx(self) -> str:
        """Экспортирует модель в ONNX-формат для портативного использования."""
        return (
            "⚠️ ONNX-экспорт для sklearn-pipeline требует skl2onnx:\n"
            "  pip install skl2onnx\n"
            "  Функция будет доступна в следующей версии."
        )
