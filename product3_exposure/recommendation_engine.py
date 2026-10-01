"""recommendation_engine.py - USER RECOMMENDATION with anti-annoyance policy.
 * Notify on ESCALATION immediately (NORMAL->ELEVATED, ->HIGH).
 * Re-notify the same state only after a cooldown (ELEVATED 3 h, HIGH 1 h).
 * NORMAL never notifies. Wording is advisory ('consider'), never diagnostic."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from risk_state import RiskState

MESSAGES = {
    RiskState.NORMAL: "Continue monitoring.",
    RiskState.ELEVATED: "Consider lowering volume.",
    RiskState.HIGH: "Consider taking a listening break.",
}
ORDER = {RiskState.NORMAL: 0, RiskState.ELEVATED: 1, RiskState.HIGH: 2}


@dataclass
class Recommendation:
    state: RiskState
    message: str
    notify: bool
    reason: str


class RecommendationEngine:
    def __init__(self, cooldown_min=None):
        self.cooldown = cooldown_min or {RiskState.ELEVATED: 180, RiskState.HIGH: 60}
        self._last_state = RiskState.NORMAL
        self._last_notified: Optional[datetime] = None
        self._last_notified_state = RiskState.NORMAL

    def recommend(self, state: RiskState, now: datetime) -> Recommendation:
        prev, self._last_state = self._last_state, state
        if state == RiskState.NORMAL:
            return Recommendation(state, MESSAGES[state], False, "normal: no alert")
        if ORDER[state] > ORDER[prev] and ORDER[state] > ORDER[self._last_notified_state]:
            return self._fire(state, now, "escalation")
        wait = timedelta(minutes=self.cooldown[state])
        if self._last_notified is None or now - self._last_notified >= wait:
            return self._fire(state, now, "cooldown elapsed")
        left = (self._last_notified + wait - now).seconds // 60
        return Recommendation(state, MESSAGES[state], False, f"suppressed (cooldown, {left} min left)")

    def _fire(self, state, now, why):
        self._last_notified, self._last_notified_state = now, state
        return Recommendation(state, MESSAGES[state], True, why)
