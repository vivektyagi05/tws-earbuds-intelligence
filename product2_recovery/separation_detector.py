"""separation_detector.py - decides whether a disconnect means 'lost' or 'normal'.
Rules (all thresholds configurable):
  * bud docked in case when last seen -> normal disconnect (not separation)
  * disconnect shorter than debounce_s -> radio dropout, ignore
  * one bud CONNECTED while the other is not -> strong signal of separation
  * both buds DISCONNECTED -> ambiguous (phone BT off / out of range): only flagged
    after the longer 'both_gone_s' timeout"""
from dataclasses import dataclass
from datetime import datetime
from typing import List
from device_state import *


@dataclass
class Separation:
    device: DeviceId
    since: datetime
    reason: str
    confirmed: bool


class SeparationDetector:
    def __init__(self, debounce_s=20, both_gone_s=300):
        self.debounce_s, self.both_gone_s = debounce_s, both_gone_s

    def evaluate(self, devices, now: datetime) -> List[Separation]:
        buds = [devices[DeviceId.LEFT], devices[DeviceId.RIGHT]]
        out = []
        for b in buds:
            if b.connection == ConnectionState.CONNECTED or b.disconnected_at is None:
                continue
            if b.in_case:
                continue                                    # docked: expected
            other = buds[1] if b is buds[0] else buds[0]
            gone = (now - b.disconnected_at).total_seconds()
            if other.connection == ConnectionState.CONNECTED:
                out.append(Separation(b.device_id, b.disconnected_at,
                                      "other bud still connected",
                                      confirmed=gone >= self.debounce_s))
            elif other.in_case is not True:
                out.append(Separation(b.device_id, b.disconnected_at,
                                      "both buds disconnected (ambiguous)",
                                      confirmed=gone >= self.both_gone_s))
        return out
