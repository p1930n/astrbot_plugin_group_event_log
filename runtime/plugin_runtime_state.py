from __future__ import annotations

from dataclasses import dataclass, field

try:
    from ..domain.models import PluginConfig
except ImportError:
    from domain.models import PluginConfig


@dataclass(slots=True)
class PluginRuntimeState:
    config: PluginConfig = field(default_factory=PluginConfig)
    is_ready: bool = False
    is_running: bool = True
