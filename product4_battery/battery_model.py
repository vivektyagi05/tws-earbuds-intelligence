"""battery_model.py - telemetry schema + SIMULATED telemetry generator.

Ground-truth capacity fade used ONLY to generate data (the estimators never see it):
   cap(c) = ref * (1 - a*c - b*c^2),  c = charge cycles
Left fades slowly/linearly; right fades faster and accelerates (simulated defect).
Each record = one listening session between charges; SOC readings carry fuel-gauge
noise (+/-1.5 pp), which is what makes estimation non-trivial."""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List


@dataclass
class BatteryConfig:
    reference_capacity_mwh: float = 185.0     # new cell: 50 mAh @ 3.7 V (assumed)
    cutoff_soc_pct: float = 5.0               # device shuts down below this
    end_of_life_health_pct: float = 80.0      # common Li-ion convention, configurable


@dataclass
class TelemetryRecord:
    timestamp: datetime
    bud: str
    soc_start_pct: float
    soc_end_pct: float
    voltage_v: float
    temperature_c: float
    charge_duration_min: float
    cycle_count: int
    listen_min: float
    avg_power_mw: float


def simulate_telemetry(days=300, seed=11, cfg: BatteryConfig = BatteryConfig()) -> List[TelemetryRecord]:
    rng = random.Random(seed)
    params = {"left": (0.0003, 0.0, 33.0, 31.0), "right": (0.0004, 1.33e-6, 37.0, 35.5)}  # a, b, power, temp
    start, out = datetime(2025, 12, 1, 8, 0), []
    for day in range(days):
        for bud, (a, b, pwr, temp) in params.items():
            c = day
            true_cap = cfg.reference_capacity_mwh * (1 - a * c - b * c * c)
            p = max(15.0, rng.gauss(pwr, 3.0))
            listen_min = rng.uniform(70, 160)
            drop = (p * listen_min / 60) / true_cap * 100
            soc0 = rng.uniform(95, 100)
            soc1 = max(0.0, soc0 - drop)
            gauge = lambda v: min(100, max(0, v + rng.gauss(0, 1.5)))   # fuel-gauge noise
            out.append(TelemetryRecord(start + timedelta(days=day), bud, gauge(soc0), gauge(soc1),
                                       3.6 + 0.6 * soc1 / 100 + rng.gauss(0, 0.01),
                                       rng.gauss(temp, 1.5), rng.uniform(40, 75) * (1 + 0.003 * c),
                                       c, listen_min, p))
    return out


def by_bud(records, bud):
    return sorted([r for r in records if r.bud == bud], key=lambda r: r.timestamp)
