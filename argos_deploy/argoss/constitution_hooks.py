"""
argoss/constitution_hooks.py — Хуки конституции ARGOS
===================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import yaml
except ImportError:
    yaml = None

from argos_constitution import (
    ActionRequest,
    ArgosConstitution,
    ArgosMode,
    ChannelState,
    PatchPlan,
    ResourceState,
)

try:
    from argos_logger import get_logger
    log = get_logger("argos.constitution")
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("argos.constitution")


@dataclass
class HookResult:
    ok: bool
    message: str
    forced_mode: Optional[str] = None


class ConstitutionHooks:
    """Хуки для интеграции конституции с ядром ARGOS."""

    def __init__(
        self, core: Any, config_path: str = "argoss/ARGOS_CONSTITUTION.yaml"
    ):
        self.core = core
        self.config_path = Path(config_path)
        self.constitution = self._load_constitution()
        self._last_mode = None

    def _load_constitution(self) -> ArgosConstitution:
        if yaml is None:
            raise RuntimeError("PyYAML не установлен: pip install pyyaml")
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Не найден конфиг конституции: {self.config_path}"
            )
        cfg = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        return ArgosConstitution(cfg)

    def _resource_state(self) -> ResourceState:
        cpu = 0.0
        ram = 0.0
        disk = 0.0
        try:
            import psutil

            cpu = float(psutil.cpu_percent(interval=0.2))
            ram = float(psutil.virtual_memory().percent)
            disk = float(psutil.disk_usage("/").percent)
        except Exception as e:
            log.warning("psutil metrics unavailable: %s", e)

        llm_calls = int(
            getattr(self.core, "_local_llm_calls_per_minute", 0) or 0
        )
        heavy_tasks = int(
            getattr(self.core, "_heavy_tasks_running", 0) or 0
        )

        return ResourceState(
            cpu_percent=cpu,
            ram_percent=ram,
            disk_percent=disk,
            local_llm_calls_per_minute=llm_calls,
            heavy_tasks=heavy_tasks,
        )

    def _channel_state(self) -> ChannelState:
        telegram_alive = bool(
            getattr(self.core, "telegram_bot", None)
            or getattr(self.core, "_telegram", None)
        )
        web_alive = bool(getattr(self.core, "_dashboard", None))
        console_alive = True
        slack_alive = bool(getattr(self.core, "slack_bridge", None))

        return ChannelState(
            telegram=telegram_alive,
            web=web_alive,
            console=console_alive,
            slack=slack_alive,
        )

    def tick(self) -> HookResult:
        """Основной цикл проверки конституции."""
        resources = self._resource_state()
        channels = self._channel_state()

        channel_decision = self.constitution.validate_channels(channels)
        if not channel_decision.allowed:
            self._force_mode(channel_decision.forced_mode or ArgosMode.RECOVERY)
            return HookResult(
                False, channel_decision.reason, self.constitution.mode.value
            )

        mode = self.constitution.evaluate_mode(resources)
        if mode != self._last_mode:
            self._apply_mode(mode)
            self._last_mode = mode

        return HookResult(
            True,
            self.constitution.report(resources, channels),
            mode.value,
        )

    def _force_mode(self, mode: ArgosMode) -> None:
        self.constitution.mode = mode
        self._apply_mode(mode)

    def _apply_mode(self, mode: ArgosMode) -> None:
        log.warning("ARGOS mode => %s", mode.value)
        setattr(self.core, "argos_mode", mode.value)

        if mode == ArgosMode.NORMAL:
            self._enable_normal_mode()
        elif mode == ArgosMode.LOW_POWER:
            self._enable_low_power_mode()
        elif mode == ArgosMode.SAFE_MODE:
            self._enable_safe_mode()
        elif mode == ArgosMode.RECOVERY:
            self._enable_recovery_mode()

    def _enable_normal_mode(self) -> None:
        setattr(self.core, "_auto_patch_allowed", True)
        setattr(self.core, "_heavy_tasks_allowed", True)

    def _enable_low_power_mode(self) -> None:
        setattr(self.core, "_heavy_tasks_allowed", False)
        setattr(self.core, "_auto_patch_allowed", False)
        for attr in ("vision", "web_explorer", "iot_emulator"):
            if hasattr(self.core, attr):
                setattr(self.core, attr, None)

    def _enable_safe_mode(self) -> None:
        setattr(self.core, "_heavy_tasks_allowed", False)
        setattr(self.core, "_auto_patch_allowed", False)
        setattr(self.core, "_agent_self_modify_allowed", False)
        for attr in (
            "vision",
            "iot_bridge",
            "iot_emulator",
            "mesh_net",
            "web_explorer",
            "dag_manager",
            "marketplace",
        ):
            if hasattr(self.core, attr):
                setattr(self.core, attr, None)

    def _enable_recovery_mode(self) -> None:
        self._enable_safe_mode()

    def guard_patch(
        self,
        patch_id: str,
        *,
        touches_live_core: bool,
        has_backup: bool,
        has_staging: bool,
        has_healthcheck: bool,
        has_rollback_plan: bool,
    ) -> HookResult:
        """Проверка патча перед применением."""
        patch = PatchPlan(
            patch_id=patch_id,
            touches_live_core=touches_live_core,
            has_backup=has_backup,
            has_staging=has_staging,
            has_healthcheck=has_healthcheck,
            has_rollback_plan=has_rollback_plan,
        )

        decision = self.constitution.validate_patch(patch)
        if not decision.allowed:
            log.error("PATCH BLOCKED %s: %s", patch_id, decision.reason)
            if decision.forced_mode:
                self._force_mode(decision.forced_mode)
            return HookResult(
                False, decision.reason, self.constitution.mode.value
            )

        log.info("PATCH ALLOWED %s", patch_id)
        return HookResult(True, decision.reason, self.constitution.mode.value)

    def guard_shell(self, command: str) -> HookResult:
        """Проверка shell-команды."""
        decision = self.constitution.validate_action(
            ActionRequest(action_type="shell", command=command)
        )
        if not decision.allowed:
            log.error("SHELL BLOCKED: %s | %s", command, decision.reason)
            return HookResult(
                False, decision.reason, self.constitution.mode.value
            )
        return HookResult(True, "Shell command allowed", self.constitution.mode.value)

    # Telegram команды
    def telegram_status(self) -> str:
        resources = self._resource_state()
        channels = self._channel_state()
        return self.constitution.report(resources, channels)

    def telegram_enter_safe_mode(self) -> str:
        self._force_mode(ArgosMode.SAFE_MODE)
        return "🛡 Argos переведён в SAFE MODE"

    def telegram_enter_normal_mode(self) -> str:
        self._force_mode(ArgosMode.NORMAL)
        return "✅ Argos переведён в NORMAL MODE"

    def telegram_can_autopatch(self) -> str:
        allowed = bool(getattr(self.core, "_auto_patch_allowed", False))
        return f"Autopatch: {'ON' if allowed else 'OFF'} | mode={getattr(self.core, 'argos_mode', 'unknown')}"

    # Autopatch hooks
    def before_autopatch(
        self, patch_id: str, touches_live_core: bool = True
    ) -> None:
        result = self.guard_patch(
            patch_id,
            touches_live_core=touches_live_core,
            has_backup=True,
            has_staging=True,
            has_healthcheck=True,
            has_rollback_plan=True,
        )
        if not result.ok:
            raise RuntimeError(f"Autopatch blocked by constitution: {result.message}")

    def after_failed_autopatch(
        self, patch_id: str, rollback_fn: Optional[Callable[[], None]] = None
    ) -> None:
        log.error("Autopatch failed: %s", patch_id)
        self._force_mode(ArgosMode.RECOVERY)
        if rollback_fn:
            try:
                rollback_fn()
                log.warning("Rollback completed for %s", patch_id)
            except Exception as e:
                log.exception("Rollback failed for %s: %s", patch_id, e)

    def after_successful_autopatch(self, patch_id: str) -> None:
        log.info("Autopatch success: %s", patch_id)
        if self.constitution.mode == ArgosMode.RECOVERY:
            self._force_mode(ArgosMode.SAFE_MODE)

    def healthcheck_boot(self) -> HookResult:
        checks = [
            ("core", self.core is not None),
            ("memory", getattr(self.core, "memory", None) is not None),
            ("mode", hasattr(self.core, "argos_mode")),
        ]
        failed = [name for name, ok in checks if not ok]
        if failed:
            self._force_mode(ArgosMode.RECOVERY)
            return HookResult(
                False,
                f"Boot healthcheck failed: {', '.join(failed)}",
                self.constitution.mode.value,
            )
        return HookResult(
            True, "Boot healthcheck OK", self.constitution.mode.value
        )
