from __future__ import annotations

from typing import Any


def recommend_steps(history: list[dict[str, Any]]) -> tuple[int, str]:
    """
    Quantum-ML policy for ARC runner.
    Возвращает (recommended_steps, mode).
    mode:
      - "qml"       : если доступен PennyLane и расчёт выполнен
      - "classical" : если fallback без QML
    """
    if not history:
        return 10, "classical"

    # Базовый статистический fallback.
    ok = [h for h in history if h.get("ok")]
    if not ok:
        return 10, "classical"
    avg_actions = sum(int(h.get("total_actions", 0) or 0) for h in ok) / max(1, len(ok))
    classical_steps = max(5, min(200, int(avg_actions) if avg_actions > 0 else 10))

    # Опциональный QML слой (если библиотека установлена).
    try:
        import pennylane as qml  # type: ignore
        from pennylane import numpy as np  # type: ignore

        dev = qml.device("default.qubit", wires=2)

        @qml.qnode(dev)
        def circuit(x1, x2, w):
            qml.RX(x1, wires=0)
            qml.RY(x2, wires=1)
            qml.CNOT(wires=[0, 1])
            qml.RY(w, wires=0)
            return qml.expval(qml.PauliZ(0))

        # features: normalized score and actions
        last = ok[-1]
        score = float(last.get("score", 0.0) or 0.0)
        actions = float(last.get("total_actions", classical_steps) or classical_steps)
        x1 = np.clip(score, 0.0, 1.0)
        x2 = np.clip(actions / 200.0, 0.0, 1.0)
        out = float(circuit(x1, x2, 0.7))

        # map [-1..1] -> [0.7..1.3] multiplier
        mult = 1.0 + 0.3 * out
        qml_steps = int(max(5, min(200, classical_steps * mult)))
        return qml_steps, "qml"
    except Exception:
        return classical_steps, "classical"
