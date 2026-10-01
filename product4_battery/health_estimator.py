"""health_estimator.py - usable-capacity and State-of-Health ESTIMATE.

Per session:   energy_used(mWh) = avg_power(mW) * listen_h
               capacity_est     = energy_used / (delta_SOC/100)
Health(%)     = median(capacity_est of last N valid sessions) / reference_capacity * 100
Only sessions with delta_SOC >= 30 pp are used (small deltas amplify gauge noise).
Median (robust to outliers). Confidence depends on sample count and spread (MAD).
This is a PROTOTYPE SOH ESTIMATE - not a validated State-of-Health measurement.
Note: voltage and charge_duration are recorded in the telemetry schema but are NOT used
by any estimator in this prototype (temperature is used only for a warm-running flag)."""
import statistics
from dataclasses import dataclass
from typing import List, Tuple
from battery_model import BatteryConfig, TelemetryRecord


@dataclass
class HealthEstimate:
    health_pct: float
    capacity_mwh: float
    capacity_low_mwh: float        # 25th percentile
    capacity_high_mwh: float       # 75th percentile
    samples: int
    confidence: str


def capacity_series(records: List[TelemetryRecord], min_delta_soc=30.0) -> List[Tuple[int, float]]:
    """-> [(cycle_count, capacity_estimate_mwh)] for valid sessions."""
    out = []
    for r in records:
        d = r.soc_start_pct - r.soc_end_pct
        if d >= min_delta_soc and r.avg_power_mw > 0 and r.listen_min > 0:
            out.append((r.cycle_count, r.avg_power_mw * r.listen_min / 60 / (d / 100)))
    return out


def estimate_health(records, cfg: BatteryConfig, recent_n=20) -> HealthEstimate:
    series = capacity_series(records)
    if len(series) < 5:
        raise ValueError("insufficient telemetry: need >= 5 valid discharge sessions")
    caps = [c for _, c in series[-recent_n:]]
    med = statistics.median(caps)
    q = statistics.quantiles(caps, n=4) if len(caps) >= 4 else [min(caps), med, max(caps)]
    rel_spread = (q[2] - q[0]) / med
    conf = "high" if len(caps) >= 15 and rel_spread < 0.10 else "medium" if len(caps) >= 8 else "low"
    return HealthEstimate(100 * med / cfg.reference_capacity_mwh, med, q[0], q[2], len(caps), conf)
