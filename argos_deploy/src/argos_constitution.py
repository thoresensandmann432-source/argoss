from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ArgosMode(str, Enum):
    NORMAL = "normal"
    LOW_POWER = "low_power"
    SAFE_MODE = "safe_mode"
    STAGING = "staging"
    RECOVERY = "recovery"


@dataclass
class ResourceState:
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    disk_percent: float = 0.0
    local_llm_calls_per_minute: int = 0
    heavy_tasks: int = 0


@dataclass
class ChannelState:
    telegram: bool = False
    web: bool = False
    console: bool = True
    slack: bool = False

    def alive_channels(self) -> List[str]:
        return [name for name, value in vars(self).items() if value]


@dataclass
class PatchPlan:
    patch_id: str
    touches_live_core: bool = False
    has_backup: bool = False
    has_staging: bool = False
    has_healthcheck: bool = False
    has_rollback_plan: bool = False


@dataclass
class ActionRequest:
    action_type: str
    command: Optional[str] = None
    module: Optional[str] = None
    cost: Optional[float] = None
    dangerous: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstitutionDecision:
    allowed: bool
    reason: str
    forced_mode: Optional[ArgosMode] = None
    require_owner_approval: bool = False
    require_rollback: bool = False


class ArgosConstitution:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config: Dict[str, Any] = config or {}
        default_mode = self.config.get("modes", {}).get("default", ArgosMode.NORMAL.value)
        self.mode = ArgosMode(default_mode)

    # Compatibility with old style: obj.init(config)
    def init(self, config: Dict[str, Any]):
        self.__init__(config)

    def _threshold(self, section: str, key: str, default: float) -> float:
        return float(self.config.get("resources", {}).get(section, {}).get(key, default))

    def evaluate_mode(self, resources: ResourceState) -> ArgosMode:
        cpu_crit = self._threshold("cpu", "critical_threshold", 92)
        ram_crit = self._threshold("ram", "critical_threshold", 92)
        disk_crit = self._threshold("disk", "critical_threshold", 95)

        cpu_low = self._threshold("cpu", "low_power_threshold", 80)
        ram_low = self._threshold("ram", "low_power_threshold", 80)

        if (
            resources.cpu_percent >= cpu_crit
            or resources.ram_percent >= ram_crit
            or resources.disk_percent >= disk_crit
        ):
            self.mode = ArgosMode.SAFE_MODE
        elif resources.cpu_percent >= cpu_low or resources.ram_percent >= ram_low:
            self.mode = ArgosMode.LOW_POWER
        else:
            self.mode = ArgosMode.NORMAL
        return self.mode

    def validate_channels(self, channels: ChannelState) -> ConstitutionDecision:
        require_alive = self.config.get("channels", {}).get("require_at_least_one_alive", True)
        if require_alive and not channels.alive_channels():
            return ConstitutionDecision(
                allowed=False,
                reason="Нет ни одного живого канала связи",
                forced_mode=ArgosMode.RECOVERY,
            )
        return ConstitutionDecision(allowed=True, reason="Каналы связи валидны")

    def validate_patch(self, patch: PatchPlan) -> ConstitutionDecision:
        patch_cfg = self.config.get("self_patch", {})
        if not patch_cfg.get("enabled", True):
            return ConstitutionDecision(False, "Автопатчи отключены")

        if patch.touches_live_core and not patch_cfg.get("live_patch_allowed", False):
            return ConstitutionDecision(
                allowed=False,
                reason="Live patch ядра запрещен конституцией",
                require_owner_approval=True,
            )

        required_checks = [
            (patch_cfg.get("require_backup", True), patch.has_backup, "Нет backup"),
            (patch_cfg.get("require_staging", True), patch.has_staging, "Нет staging"),
            (patch_cfg.get("require_healthcheck", True), patch.has_healthcheck, "Нет health-check"),
            (patch_cfg.get("require_rollback_plan", True), patch.has_rollback_plan, "Нет rollback plan"),
        ]
        for required, actual, message in required_checks:
            if required and not actual:
                return ConstitutionDecision(
                    allowed=False,
                    reason=message,
                    require_owner_approval=True,
                )

        return ConstitutionDecision(
            allowed=True,
            reason="Патч соответствует конституции",
            require_rollback=True,
        )

    def validate_shell(self, command: str) -> ConstitutionDecision:
        shell_cfg = self.config.get("shell", {})
        if not shell_cfg.get("whitelist_only", True):
            return ConstitutionDecision(True, "Whitelist отключен")

        allowed_commands = set(shell_cfg.get("allowed_commands", []))
        normalized = (command or "").strip()
        if normalized not in allowed_commands:
            return ConstitutionDecision(
                allowed=False,
                reason=f"Shell-команда не в белом списке: {normalized}",
                require_owner_approval=True,
            )
        return ConstitutionDecision(True, "Shell-команда разрешена")

    def validate_action(self, action: ActionRequest) -> ConstitutionDecision:
        forbidden = set(self.config.get("forbidden_actions", []))
        if action.action_type in forbidden:
            return ConstitutionDecision(False, f"Действие запрещено: {action.action_type}")

        if action.action_type == "shell" and action.command:
            return self.validate_shell(action.command)

        if action.dangerous:
            return ConstitutionDecision(
                allowed=False,
                reason="Опасное действие требует ручного подтверждения",
                require_owner_approval=True,
            )

        return ConstitutionDecision(True, "Действие разрешено")

    def report(self, resources: ResourceState, channels: ChannelState) -> str:
        mode = self.evaluate_mode(resources)
        alive = ", ".join(channels.alive_channels()) or "нет"
        return (
            "ARGOS Constitution Report\n"
            f"mode={mode.value}\n"
            f"cpu={resources.cpu_percent:.1f}% ram={resources.ram_percent:.1f}% "
            f"disk={resources.disk_percent:.1f}%\n"
            f"alive_channels={alive}\n"
        )
