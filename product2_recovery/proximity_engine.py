"""proximity_engine.py - turns noisy RSSI into Weak/Medium/Strong + a trend.

RSSI is a noisy proximity signal, not an indoor positioning system.
RSSI follows a log-distance path-loss model with heavy shadow fading, so it is a
COARSE hint of 'warmer/colder', never a position. We therefore expose bands and
a trend, not metres. Smoothing: median of last N samples, then EMA. Hysteresis
(+/-3 dB) prevents the band flickering at thresholds."""
import math, random
from collections import deque
from datetime import datetime
from typing import Callable, Optional
from device_state import ProximityBand


class SimulatedBleScanner:
    """SIMULATED. rssi = txpower_1m - 10*n*log10(d) + N(0, sigma). Returns None
    when the bud is not advertising (powered off) or out of radio range."""
    def __init__(self, distance_fn: Callable[[float], float], tx_1m=-59.0, n=2.2,
                 sigma=3.5, sensitivity=-95.0, seed=7):
        self.distance_fn, self.tx, self.n, self.sigma, self.sens = distance_fn, tx_1m, n, sigma, sensitivity
        self.rng = random.Random(seed)
        self.advertising = True

    def scan(self, t: float) -> Optional[float]:
        if not self.advertising:
            return None
        d = max(self.distance_fn(t), 0.3)
        rssi = self.tx - 10 * self.n * math.log10(d) + self.rng.gauss(0, self.sigma)
        return rssi if rssi > self.sens else None


class ProximityEngine:
    STRONG_DBM, MEDIUM_DBM, HYST = -66.0, -78.0, 3.0

    def __init__(self, window=5, alpha=0.5, lost_after_misses=4):
        self.raw = deque(maxlen=window)
        self.alpha, self.ema, self.misses, self.lost_after = alpha, None, 0, lost_after_misses
        self.band = ProximityBand.UNKNOWN
        self.ema_history = deque(maxlen=6)

    def update(self, rssi: Optional[float]):
        if rssi is None:
            self.misses += 1
            if self.misses >= self.lost_after:
                self.band = ProximityBand.UNKNOWN
            return self.band
        self.misses = 0
        self.raw.append(rssi)
        med = sorted(self.raw)[len(self.raw) // 2]
        self.ema = med if self.ema is None else self.alpha * med + (1 - self.alpha) * self.ema
        self.ema_history.append(self.ema)
        self.band = self._band_with_hysteresis(self.ema)
        return self.band

    def _band_with_hysteresis(self, v):
        h, b = self.HYST, self.band
        if v >= self.STRONG_DBM + (h if b != ProximityBand.STRONG else -h):
            return ProximityBand.STRONG
        if v >= self.MEDIUM_DBM + (h if b == ProximityBand.WEAK or b == ProximityBand.UNKNOWN else -h):
            return ProximityBand.MEDIUM
        return ProximityBand.WEAK

    def trend(self) -> str:
        """CLOSER / FARTHER / STEADY from smoothed signal change (needs >=4 points)."""
        if len(self.ema_history) < 4:
            return "UNKNOWN"
        delta = self.ema_history[-1] - self.ema_history[0]
        return "CLOSER" if delta > 2.5 else "FARTHER" if delta < -2.5 else "STEADY"
