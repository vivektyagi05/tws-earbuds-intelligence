"""runtime_predictor.py - transparent runtime formula (no black box):

   usable_mWh   = (SOC - cutoff)/100 * capacity_est
   power_recent = EWMA of avg_power over last sessions (half-weight ~3 sessions)
   runtime_h    = usable_mWh / power_recent
Range: same formula with 25th/75th percentile capacity and the power std-dev."""
import statistics
from dataclasses import dataclass


@dataclass
class RuntimeEstimate:
    hours: float
    low_hours: float
    high_hours: float
    full_charge_hours: float
    recent_power_mw: float


def ewma_power(records, n=15, alpha=0.25):
    vals = [r.avg_power_mw for r in records[-n:]]
    if not vals:
        raise ValueError("no power telemetry")
    e = vals[0]
    for v in vals[1:]:
        e = alpha * v + (1 - alpha) * e
    return e, (statistics.pstdev(vals) if len(vals) > 1 else 0.0)


def predict_runtime(records, health, cfg, current_soc_pct) -> RuntimeEstimate:
    p, sd = ewma_power(records)
    usable = lambda cap, soc: max(soc - cfg.cutoff_soc_pct, 0) / 100 * cap
    hrs = usable(health.capacity_mwh, current_soc_pct) / p
    low = usable(health.capacity_low_mwh, current_soc_pct) / (p + sd)
    high = usable(health.capacity_high_mwh, current_soc_pct) / max(p - sd, 1.0)
    full = usable(health.capacity_mwh, 100) / p
    return RuntimeEstimate(hours=hrs, low_hours=low, high_hours=high, full_charge_hours=full, recent_power_mw=p)
