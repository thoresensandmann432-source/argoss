from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import permutations
from typing import Dict, Iterable, List, Optional

try:
    from qiskit import QuantumCircuit
    from qiskit.primitives import StatevectorSampler

    QISKIT_OK = True
except Exception:
    QuantumCircuit = None
    StatevectorSampler = None
    QISKIT_OK = False

DecisionLabel = str


@dataclass
class QuantumDecisionResult:
    label: DecisionLabel
    bitstring: str
    probabilities: Dict[str, float]
    features: List[float]
    shots: int
    backend: str
    ok: bool
    reason: str = ""


@dataclass
class QuantumIntentPrediction:
    intent: str
    confidence: float
    label_probabilities: Dict[str, float]
    bitstring: str
    backend: str
    ok: bool
    reason: str = ""


class QuantumDecisionEngine:
    LABELS = {
        "00": "execute_local",
        "01": "ask_cloud",
        "10": "delegate_p2p",
        "11": "defer",
    }

    def __init__(
        self,
        shots: int = 512,
        backend_name: str = "local_statevector",
        weights: Optional[Iterable[float]] = None,
    ) -> None:
        self.shots = int(shots)
        self.backend_name = backend_name
        self.num_qubits = 2
        self.num_features = 4
        self.weights = list(weights) if weights is not None else [
            0.8,
            -0.4,
            0.6,
            0.3,
            -0.2,
            0.7,
            0.5,
            -0.6,
            0.25,
            -0.35,
        ]

    def prepare_features(self, features: Iterable[float]) -> List[float]:
        vals = list(features)[: self.num_features]
        while len(vals) < self.num_features:
            vals.append(0.0)
        return [max(-1.0, min(1.0, float(v))) * math.pi for v in vals]

    def build_circuit(self, features: Iterable[float]):
        if not QISKIT_OK:
            raise RuntimeError("Qiskit unavailable")
        feats = self.prepare_features(features)
        qc = QuantumCircuit(self.num_qubits, self.num_qubits)
        qc.ry(feats[0] * self.weights[0], 0)
        qc.rz(feats[1] * self.weights[1], 0)
        qc.ry(feats[2] * self.weights[2], 1)
        qc.rz(feats[3] * self.weights[3], 1)
        qc.cx(0, 1)
        qc.ry(self.weights[8], 0)
        qc.rz(self.weights[9], 1)
        qc.measure([0, 1], [0, 1])
        return qc

    def run_local(self, circuit) -> Dict[str, float]:
        if not QISKIT_OK:
            return {"00": 1.0}
        sampler = StatevectorSampler()
        job = sampler.run([circuit], shots=self.shots)
        result = job.result()
        data = result[0].data
        counts = data.c.get_counts()
        total = sum(counts.values()) or 1
        return {bit: cnt / total for bit, cnt in counts.items()}

    def decide(self, features: Iterable[float]) -> QuantumDecisionResult:
        feats = self.prepare_features(features)
        if not QISKIT_OK:
            return QuantumDecisionResult(
                label="execute_local",
                bitstring="00",
                probabilities={"00": 1.0},
                features=feats,
                shots=0,
                backend="simulation",
                ok=True,
                reason="Qiskit не установлен — режим симуляции",
            )
        try:
            qc = self.build_circuit(feats)
            probs = self.run_local(qc)
            best = max(probs, key=probs.get)
            return QuantumDecisionResult(
                label=self.LABELS.get(best, "execute_local"),
                bitstring=best,
                probabilities=probs,
                features=feats,
                shots=self.shots,
                backend=self.backend_name,
                ok=True,
            )
        except Exception as e:
            return QuantumDecisionResult(
                label="execute_local",
                bitstring="00",
                probabilities={"00": 1.0},
                features=feats,
                shots=0,
                backend="error",
                ok=False,
                reason=str(e),
            )


class QuantumIntentHead:
    BITSTRINGS = ("00", "01", "10", "11")

    def __init__(self, decision_engine: Optional[QuantumDecisionEngine] = None) -> None:
        self.decision_engine = decision_engine or QuantumDecisionEngine()
        self.label_to_bitstring: Dict[str, str] = {}
        self.bitstring_to_label: Dict[str, str] = {}
        self.backend = getattr(self.decision_engine, "backend_name", "unavailable")
        self.samples_seen = 0
        self.training_accuracy = 0.0
        self.ready = False
        self.reason = ""

    def fit(self, features_matrix: Iterable[Iterable[float]], labels: Iterable[str]) -> None:
        features = [list(row) for row in features_matrix]
        labels = [str(label) for label in labels]
        unique_labels = sorted(set(labels))
        if not unique_labels:
            raise ValueError("No labels for quantum head")
        if len(unique_labels) > len(self.BITSTRINGS):
            raise ValueError("Quantum head supports up to 4 classes")

        counts_by_label: Dict[str, Counter] = defaultdict(Counter)
        for row, label in zip(features, labels):
            result = self.decision_engine.decide(row)
            counts_by_label[label][result.bitstring] += 1

        best_score = -1
        best_mapping: Dict[str, str] = {}
        for assigned in permutations(self.BITSTRINGS, len(unique_labels)):
            candidate = dict(zip(unique_labels, assigned))
            score = sum(counts_by_label[label][bit] for label, bit in candidate.items())
            if score > best_score:
                best_score = score
                best_mapping = candidate

        self.label_to_bitstring = best_mapping
        self.bitstring_to_label = {bit: label for label, bit in best_mapping.items()}
        self.samples_seen = len(labels)
        self.training_accuracy = (best_score / len(labels)) if labels else 0.0
        self.ready = True
        self.reason = ""

    def predict(self, features: Iterable[float]) -> QuantumIntentPrediction:
        if not self.ready:
            return QuantumIntentPrediction(
                intent="unknown",
                confidence=0.0,
                label_probabilities={},
                bitstring="00",
                backend="unavailable",
                ok=False,
                reason="Quantum head not trained",
            )

        result = self.decision_engine.decide(features)
        label_scores: Dict[str, float] = {}
        for label, bit in self.label_to_bitstring.items():
            label_scores[label] = float(result.probabilities.get(bit, 0.0))

        total = sum(label_scores.values()) or 1.0
        normalized = {label: score / total for label, score in label_scores.items()}

        predicted_label = self.bitstring_to_label.get(result.bitstring)
        if predicted_label is None and normalized:
            predicted_label = max(normalized, key=normalized.get)
        predicted_label = predicted_label or "unknown"
        confidence = float(normalized.get(predicted_label, 0.0))

        return QuantumIntentPrediction(
            intent=predicted_label,
            confidence=confidence,
            label_probabilities=normalized,
            bitstring=result.bitstring,
            backend=result.backend,
            ok=result.ok,
            reason=result.reason,
        )

    def status(self) -> Dict[str, object]:
        return {
            "ready": self.ready,
            "backend": self.backend,
            "samples_seen": self.samples_seen,
            "training_accuracy": self.training_accuracy,
            "labels": dict(self.label_to_bitstring),
            "reason": self.reason,
        }
