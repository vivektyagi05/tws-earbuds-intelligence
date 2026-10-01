"""main.py - Telemetry -> Health -> Runtime -> Degradation -> Dashboard (SIMULATED telemetry)."""
import argparse, json, statistics
from battery_model import BatteryConfig, simulate_telemetry, by_bud
from health_estimator import estimate_health
from runtime_predictor import predict_runtime
from degradation_detector import trend, detect

CURRENT_SOC = {"left": 95.0, "right": 62.0}      # SIMULATED live readings


def analyse():
    cfg, recs = BatteryConfig(), simulate_telemetry()
    res = {}
    for bud in ("left", "right"):
        r = by_bud(recs, bud)
        h = estimate_health(r, cfg)
        res[bud] = dict(h=h, rt=predict_runtime(r, h, cfg, CURRENT_SOC[bud]), tr=trend(r, cfg),
                        temp=statistics.median(x.temperature_c for x in r[-30:]), n=len(r), cycles=r[-1].cycle_count)
    findings = detect(res["left"]["h"].health_pct, res["right"]["h"].health_pct, res["left"]["tr"],
                      res["right"]["tr"], res["left"]["temp"], res["right"]["temp"])
    return cfg, recs, res, findings


def dashboard(res, findings, cfg):
    print("=" * 66 + "\n  EARBUD BATTERY DASHBOARD   (prototype SOH estimates, SIMULATED data)\n" + "=" * 66)
    for bud in ("left", "right"):
        d = res[bud]; h, rt, tr = d["h"], d["rt"], d["tr"]
        print(f"\n{bud.upper()} BUD   cycles={d['cycles']}  sessions={d['n']}  confidence={h.confidence}")
        print(f"  Prototype SOH est.  : {h.health_pct:5.1f}%   [capacity {h.capacity_mwh:.0f} mWh, IQR {h.capacity_low_mwh:.0f}-{h.capacity_high_mwh:.0f}]")
        print(f"  Runtime on full chg : {rt.full_charge_hours:4.1f} h   (new reference cell, same cutoff & load: ~{(100-cfg.cutoff_soc_pct)/100*cfg.reference_capacity_mwh/rt.recent_power_mw:.1f} h)")
        print(f"  Runtime now ({CURRENT_SOC[bud]:.0f}% ) : {rt.hours:4.1f} h   range {rt.low_hours:.1f}-{rt.high_hours:.1f} h   [recent load {rt.recent_power_mw:.1f} mW]")
        print(f"  Degradation trend   : {tr.slope_pp_per_100_cycles:+.2f} pts/100 cycles, acceleration {tr.acceleration_pp:+.2f}")
        print(f"  Cycles to 80% health: {'~%d' % tr.cycles_to_eol if tr.cycles_to_eol else 'n/a (already at/below 80% or not degrading)'}")
    print("\nFINDINGS")
    for f in findings or []:
        print(f"  [{f.severity.upper()}] {f.message}")
    if not findings:
        print("  Left/right behave consistently.")
    print("\nNOTE: Prototype SOH estimate from simulated software-level telemetry; not a validated or laboratory-certified battery-health measurement.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--json"); a = ap.parse_args()
    cfg, recs, res, findings = analyse()
    dashboard(res, findings, cfg)
    if a.json:
        warn = next((f.message for f in findings if f.severity == "warning"), None)
        json.dump({side: {"health": round(res[side]["h"].health_pct), "estimatedRuntimeHours": round(res[side]["rt"].hours, 1),
                          "fullChargeRuntimeHours": round(res[side]["rt"].full_charge_hours, 1), "confidence": res[side]["h"].confidence,
                          "trendPointsPer100Cycles": round(res[side]["tr"].slope_pp_per_100_cycles, 2)}
                   for side in ("left", "right")} | {"warning": warn, "estimateType": "prototype_soh_estimate", "findings": [f.__dict__ for f in findings]},
                  open(a.json, "w"), indent=2)
