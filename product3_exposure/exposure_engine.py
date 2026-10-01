"""exposure_engine.py - EXPOSURE CALCULATION (pure maths, no policy, no messages).

Dose model (NIOSH-style, all parameters configurable):
    allowed_hours(L) = Tc / 2^((L - Lc)/q)      Lc=85 dBA, Tc=8 h, q=3 dB exchange rate
    dose(%)          = 100 * sum_i( t_i / allowed_hours(L_i) )
Equivalent energy view:  LEX,8h = 10*log10( sum_i t_i*10^(L_i/10) / 8h )   (q=3 dB)
Levels below `ignore_below_dba` add nothing. Computed per ear; worst ear is reported.
Prototype engineering exposure simulation. Production implementation requires per-model
acoustic calibration and validation against the selected applicable safe-listening
standard. Not a medical device; no hearing-loss diagnosis or certified hearing protection.
Note: LEX,8h is derived from the dose with q=3 dB, so it is consistent with the dose by
construction (the exact energy-equivalent exchange rate is 3.01 dB)."""
import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class ExposureConfig:
    criterion_dba: float = 85.0
    criterion_hours: float = 8.0
    exchange_rate_db: float = 3.0
    ignore_below_dba: float = 70.0
    window_hours: float = 24.0


@dataclass
class EarExposure:
    dose_pct: float
    lex8h_dba: float
    contributions: List[float] = field(default_factory=list)   # % per session


@dataclass
class ExposureResult:
    left: EarExposure
    right: EarExposure
    worst_ear: str
    dose_pct: float                 # worst ear
    total_minutes: float
    max_level_dba: float


def allowed_hours(level, cfg: ExposureConfig):
    return cfg.criterion_hours / 2 ** ((level - cfg.criterion_dba) / cfg.exchange_rate_db)


def _ear(levels, hours, cfg):
    contrib = [0.0 if lv < cfg.ignore_below_dba else 100 * h / allowed_hours(lv, cfg)
               for lv, h in zip(levels, hours)]
    dose = sum(contrib)
    lex = (cfg.criterion_dba + 10 * math.log10(dose / 100)) if dose > 0 else float("-inf")
    return EarExposure(dose, lex, contrib)


def compute_exposure(sessions, cfg: ExposureConfig = ExposureConfig()) -> ExposureResult:
    hours = [s.duration_min / 60 for s in sessions]
    l = _ear([s.level_left_dba for s in sessions], hours, cfg)
    r = _ear([s.level_right_dba for s in sessions], hours, cfg)
    worst = "left" if l.dose_pct >= r.dose_pct else "right"
    return ExposureResult(l, r, worst, max(l.dose_pct, r.dose_pct), sum(h * 60 for h in hours),
                          max([max(s.level_left_dba, s.level_right_dba) for s in sessions], default=0.0))
