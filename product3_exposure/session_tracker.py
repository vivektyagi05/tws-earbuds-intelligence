"""session_tracker.py - RAW INPUT layer: validated listening sessions.
Contains NO audio: only timestamps, durations and an ESTIMATED level (dBA) per ear.
In production the level comes from the earbud firmware: digital gain x driver
sensitivity curve x (optional) ear-coupling model, calibrated per product."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List


class SessionError(ValueError):
    pass


@dataclass(frozen=True)
class ListeningSession:
    start: datetime
    duration_min: float
    level_left_dba: float          # SIMULATED estimate
    level_right_dba: float
    label: str = ""
    calibration: str = "SIMULATED"

    @property
    def end(self):
        return self.start + timedelta(minutes=self.duration_min)

    def validate(self):
        if not self.duration_min > 0 or self.duration_min > 24 * 60:
            raise SessionError(f"bad duration {self.duration_min}")
        for lv in (self.level_left_dba, self.level_right_dba):
            if not (20 <= lv <= 130):          # outside = sensor/estimation fault, reject
                raise SessionError(f"implausible level {lv} dBA")
        return self


class SessionTracker:
    def __init__(self):
        self._sessions: List[ListeningSession] = []

    def add(self, s: ListeningSession):
        self._sessions.append(s.validate())

    def window(self, now: datetime, hours: float = 24.0) -> List[ListeningSession]:
        lo = now - timedelta(hours=hours)
        return [s for s in self._sessions if s.end <= now and s.end > lo]
