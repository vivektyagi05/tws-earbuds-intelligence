"""risk_state.py - EXPOSURE STATE: maps dose % to NORMAL / ELEVATED / HIGH.
Hysteresis: a state is left only when dose falls 10% below its entry threshold,
so the state does not flap around a boundary."""
from dataclasses import dataclass
from enum import Enum


class RiskState(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"


@dataclass
class RiskThresholds:
    elevated_pct: float = 50.0
    high_pct: float = 100.0
    hysteresis: float = 0.10


def classify(dose_pct: float, previous: RiskState = RiskState.NORMAL,
             th: RiskThresholds = RiskThresholds()) -> RiskState:
    if th.elevated_pct >= th.high_pct:
        raise ValueError("elevated threshold must be below high threshold")
    h = 1 - th.hysteresis
    high_cut = th.high_pct * (h if previous == RiskState.HIGH else 1)
    elev_cut = th.elevated_pct * (h if previous in (RiskState.ELEVATED, RiskState.HIGH) else 1)
    if dose_pct >= high_cut:
        return RiskState.HIGH
    if dose_pct >= elev_cut:
        return RiskState.ELEVATED
    return RiskState.NORMAL
