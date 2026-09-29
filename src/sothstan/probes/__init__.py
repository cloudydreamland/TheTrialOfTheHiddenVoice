"""探测器注册表。"""

from __future__ import annotations

from sothstan.probes.base import Probe, ProbeContext
from sothstan.probes.errors import ErrorFamilyProbe
from sothstan.probes.limits import LimitsProbe
from sothstan.probes.reasoning import ReasoningProbe
from sothstan.probes.template import TemplateProbe
from sothstan.probes.token_count import TokenCountProbe

ALL_PROBES: list[type[Probe]] = [
    TokenCountProbe,
    TemplateProbe,
    LimitsProbe,
    ErrorFamilyProbe,
    ReasoningProbe,
]
PROBE_NAMES: list[str] = [p.name for p in ALL_PROBES]
TIER_OF: dict[str, int] = {p.name: p.tier for p in ALL_PROBES}

__all__ = ["ALL_PROBES", "PROBE_NAMES", "TIER_OF", "Probe", "ProbeContext"]
