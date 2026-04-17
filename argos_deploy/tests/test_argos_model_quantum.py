import unittest


def _is_trained(model) -> bool:
    return getattr(model, "_pipeline", None) is not None


def _redirect_model_storage(monkeypatch_obj, tmp_path, module):
    model_dir = tmp_path / "argos_model"
    monkeypatch_obj(module, "MODEL_DIR", model_dir)
    monkeypatch_obj(module, "MODEL_FILE", model_dir / "argos_intent_model.pkl")
    monkeypatch_obj(module, "VECTORIZER_FILE", model_dir / "argos_vectorizer.pkl")
    monkeypatch_obj(module, "META_FILE", model_dir / "model_meta.json")
    monkeypatch_obj(module, "TRAINING_LOG", model_dir / "training_history.jsonl")


class ArgosOwnModelQuantumTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        import src.argos_model as argos_model

        self.argos_model = argos_model
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        self._patched = []
        _redirect_model_storage(self._patch_attr, self.tmp_path, self.argos_model)

    def tearDown(self):
        for target, name, old_value in reversed(self._patched):
            setattr(target, name, old_value)
        self._tmpdir.cleanup()

    def _patch_attr(self, target, name, value):
        self._patched.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def test_argos_own_model_trains_with_quantum_router(self):
        model = self.argos_model.ArgosOwnModel()

        report = model.train()

        self.assertTrue(_is_trained(model))
        self.assertIn("МОДЕЛЬ ОБУЧЕНА", report)
        self.assertIn("Квантовый слой", report)

        prediction = model.predict("покажи статус системы")
        self.assertIn(prediction["intent"], model._meta.classes)
        self.assertGreaterEqual(prediction["confidence"], 0.0)
        self.assertLessEqual(prediction["confidence"], 1.0)
        self.assertTrue(prediction["source"].startswith("argos_hybrid_model_v"))
        self.assertIn("quantum", prediction)
        self.assertIn(
            prediction["quantum"]["label"],
            {"execute_local", "ask_cloud", "delegate_p2p", "defer"},
        )
        self.assertIn("quantum_head", prediction)

        status = model.status()
        self.assertIn("ГИБРИДНАЯ", status)
        self.assertIn("Quantum policy", status)
        self.assertIn("Quantum head", status)
        self.assertIn("слишком много классов", model.quantum_status())

    def test_argos_own_model_routes_answer_through_core(self):
        class CoreStub:
            def process(self, text):
                return {"answer": f"core:{text}"}

        model = self.argos_model.ArgosOwnModel(core=CoreStub())
        model.train()
        self._patch_attr(
            self.argos_model.ArgosOwnModel,
            "_quantum_route",
            lambda _self, _text, _proba: {
                "enabled": True,
                "label": "execute_local",
                "backend": "test",
                "ok": True,
                "reason": "",
                "features": [],
                "probabilities": {"00": 1.0},
                "bitstring": "00",
            },
        )

        answer = model.ask("покажи файлы")

        self.assertIn("Гибридная модель", answer)
        self.assertIn("Квантовый маршрут", answer)
        self.assertIn("core:[model_routed:", answer)

    def test_argos_own_model_fallback_without_quantum_engine(self):
        self._patch_attr(self.argos_model.ArgosOwnModel, "_create_quantum_engine", lambda _self: None)

        model = self.argos_model.ArgosOwnModel()
        report = model.train()
        prediction = model.predict("сканируй сеть")

        self.assertIn("fallback", report)
        self.assertFalse(prediction["quantum"]["enabled"])
        self.assertEqual(prediction["quantum"]["backend"], "disabled")
        self.assertEqual(prediction["quantum"]["label"], "execute_local")

    def test_argos_own_model_activates_quantum_head_for_small_class_set(self):
        def small_dataset(_self):
            texts = [
                "статус cpu",
                "проверь память",
                "покажи процессы",
                "отчёт по системе",
                "открой файл",
                "прочитай документ",
                "создай папку",
                "переименуй файл",
                "просканируй сеть",
                "мой ip адрес",
                "ping шлюз",
                "покажи маршруты",
            ]
            labels = [
                "system",
                "system",
                "system",
                "system",
                "file",
                "file",
                "file",
                "file",
                "network",
                "network",
                "network",
                "network",
            ]
            return texts, labels

        self._patch_attr(self.argos_model.ArgosOwnModel, "_collect_training_data", small_dataset)
        model = self.argos_model.ArgosOwnModel()

        report = model.train()
        prediction = model.predict("покажи ip сети")

        self.assertIn("Quantum head: активен", report)
        self.assertTrue(model._meta.quantum_head_enabled)
        self.assertEqual(sorted(model._meta.quantum_head_classes), ["file", "network", "system"])
        self.assertTrue(prediction["source"].startswith("argos_quantum_head_v"))
        self.assertTrue(prediction["quantum_head"]["ok"])
        self.assertIn("Quantum head:   активен", model.quantum_status())


if __name__ == "__main__":
    unittest.main()
