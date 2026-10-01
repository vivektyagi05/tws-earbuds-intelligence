"""degradation_detector.py - trend, imbalance and abnormal-degradation rules.

Trend: bin capacity estimates per 10 cycles (median) -> Theil-Sen slope (median of
pairwise slopes; robust to noise/outliers) in percentage points of health per 100
cycles. Acceleration = slope(last half) - slope(first half).
Abnormal if any (thresholds configurable):
  R1  health gap between buds >= gap_pp
  R2  one bud fades >= ratio x faster than the other AND faster than min_slope
  R3  fade slope accelerating by >= accel_pp and worse than min_slope
  R4  median session temperature > temp_c (thermal stress flag)"""
import statistics
from dataclasses import dataclass, field
from itertools import combinations
from typing import List
from health_estimator import capacity_series


@dataclass
class DegradationThresholds:
    gap_pp: float = 10.0
    ratio: float = 2.0
    min_slope_pp_per_100: float = 2.0
    accel_pp: float = 3.0       # noise floor of the half-vs-half estimate is ~1.5-2 pts on this data
    temp_c: float = 40.0


@dataclass
class Trend:
    slope_pp_per_100_cycles: float      # negative = losing health
    acceleration_pp: float
    cycles_to_eol: float                # None if not degrading / already past
    points: int


def trend(records, cfg) -> Trend:
    s = capacity_series(records)
    bins = {}
    for c, cap in s:
        bins.setdefault(c // 10, []).append(100 * cap / cfg.reference_capacity_mwh)
    pts = [(k * 10 + 5, statistics.median(v)) for k, v in sorted(bins.items())]
    if len(pts) < 4:
        raise ValueError("insufficient history for trend (need >= 4 bins of 10 cycles)")
    slope = lambda p: statistics.median([(y2 - y1) / (x2 - x1) for (x1, y1), (x2, y2) in combinations(p, 2)]) * 100
    half = len(pts) // 2
    sl, early, late = slope(pts), slope(pts[:half]), slope(pts[half:])
    cur = statistics.median([y for _, y in pts[-3:]])
    eol = (cur - cfg.end_of_life_health_pct) / (-sl / 100) if sl < 0 and cur > cfg.end_of_life_health_pct else None
    return Trend(sl, late - early, eol, len(pts))


@dataclass
class Finding:
    severity: str
    message: str


def detect(left_health, right_health, left_trend, right_trend, left_temp, right_temp,
           th: DegradationThresholds = DegradationThresholds()) -> List[Finding]:
    f, out = lambda s, m: Finding(s, m), []
    gap = left_health - right_health
    worse, better = ("right", "left") if gap > 0 else ("left", "right")
    tr = {"left": left_trend, "right": right_trend}
    if abs(gap) >= th.gap_pp:
        out.append(f("warning", f"{worse.capitalize()} earbud degradation is significantly higher "
                                f"(health gap {abs(gap):.0f} points)."))
    sw, sb = -tr[worse].slope_pp_per_100_cycles, -tr[better].slope_pp_per_100_cycles
    if sw >= th.min_slope_pp_per_100 and sw >= th.ratio * max(sb, 0.1):
        out.append(f("warning", f"{worse.capitalize()} earbud is fading {sw/max(sb,0.1):.1f}x faster "
                                f"({sw:.1f} vs {sb:.1f} points per 100 cycles)."))
    for side in ("left", "right"):
        t = tr[side]
        if -t.slope_pp_per_100_cycles >= th.min_slope_pp_per_100 and -t.acceleration_pp >= th.accel_pp:
            out.append(f("watch", f"{side.capitalize()} degradation is accelerating "
                                  f"({t.acceleration_pp:+.1f} points/100 cycles between early and recent history)."))
    for side, temp in (("left", left_temp), ("right", right_temp)):
        if temp > th.temp_c:
            out.append(f("watch", f"{side.capitalize()} earbud runs warm (median {temp:.0f} C)."))
    return out
