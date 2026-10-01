"""main.py - Product 3 (PROTOTYPE ENGINEERING EXPOSURE SIMULATION): RAW INPUT -> EXPOSURE CALCULATION -> STATE -> RECOMMENDATION.
All levels are SIMULATED estimates. 'moderate' = 82 dBA, 'higher' = 92 dBA (assumed mapping)."""
import argparse, json
from datetime import datetime, timedelta
from session_tracker import ListeningSession, SessionTracker, SessionError
from exposure_engine import compute_exposure, ExposureConfig
from risk_state import classify, RiskState
from recommendation_engine import RecommendationEngine

DAY = datetime(2026, 10, 1)
SESSIONS = [
    ListeningSession(DAY.replace(hour=9), 60, 82, 80, "Session 1 - moderate"),
    ListeningSession(DAY.replace(hour=12, minute=30), 45, 92, 93, "Session 2 - higher"),
    ListeningSession(DAY.replace(hour=19), 90, 82, 81, "Session 3 - moderate"),
]


def run(sessions, title, json_path=None):
    print(f"\n########## {title} ##########")
    print("(Prototype engineering exposure simulation - not a medical device; levels are SIMULATED)")
    cfg, tracker, engine, state = ExposureConfig(), SessionTracker(), RecommendationEngine(), RiskState.NORMAL
    last = None
    for s in sessions:
        print(f"\nRAW INPUT      : {s.label}: {s.duration_min:.0f} min, L={s.level_left_dba} dBA / R={s.level_right_dba} dBA [{s.calibration}]")
        try:
            tracker.add(s)
        except SessionError as e:
            print(f"REJECTED       : {e}"); continue
        now = s.end
        res = compute_exposure(tracker.window(now, cfg.window_hours), cfg)
        state = classify(res.dose_pct, state)
        rec = engine.recommend(state, now)
        print(f"EXPOSURE       : L dose {res.left.dose_pct:5.1f}% | R dose {res.right.dose_pct:5.1f}% | worst={res.worst_ear} "
              f"| LEX,8h {res.right.lex8h_dba if res.worst_ear=='right' else res.left.lex8h_dba:.1f} dBA | "
              f"this session adds {max(res.left.contributions[-1], res.right.contributions[-1]):.1f}%")
        print(f"STATE          : {state.value}")
        print(f"RECOMMENDATION : \"{rec.message}\"  notify={rec.notify}  ({rec.reason})")
        last = (res, state, rec, now)
    if last is None:
        print("\nNo valid sessions: nothing to evaluate.")
        return None
    res, state, rec, now = last
    again = engine.recommend(state, now + timedelta(minutes=10))
    print(f"\n10 min later, still {state.value}: notify={again.notify} ({again.reason})")
    return {"doseLeftPct": round(res.left.dose_pct, 1), "doseRightPct": round(res.right.dose_pct, 1),
            "state": state.value, "recommendation": rec.message, "totalListeningMinutes": res.total_minutes,
            "disclaimer": "Estimated listening exposure for wellness feedback. Not a medical device or diagnosis."}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--json"); a = ap.parse_args()
    out = run(SESSIONS, "SCENARIO A: moderate / higher / moderate")
    heavy = SESSIONS[:2] + [ListeningSession(DAY.replace(hour=19), 60, 95, 95, "Session 3 - loud")]
    run(heavy, "SCENARIO B: heavy day (escalation to HIGH)")
    run([ListeningSession(DAY.replace(hour=9), 30, 150, 80, "bad sensor value")] + SESSIONS[:1], "SCENARIO C: invalid input handling")
    if a.json:
        json.dump(out, open(a.json, "w"), indent=2)
