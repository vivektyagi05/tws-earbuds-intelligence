"""verify_prototypes.py - stdlib unittest suite (no extra dependencies).
Run: python3 scripts/verify_prototypes.py      (from repo root)
Covers: exposure maths/state machine/input rejection, recovery logic incl. dead battery,
battery formulas + determinism, speech metrics + end-to-end run, snapshot contents."""
import importlib.util, io, json, math, os, pathlib, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
for d in ("product1_speech_isolation", "product2_recovery", "product3_exposure", "product4_battery"):
    sys.path.insert(0, str(ROOT / d))      # module names are unique across products (except main.py)


def load_main(folder, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / folder / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / folder))
    spec.loader.exec_module(mod)
    return mod


def _read(path):
    with open(path) as fh:
        return json.load(fh)


def run_main(folder, *args):
    return subprocess.run([sys.executable, "main.py", *args], cwd=ROOT / folder, capture_output=True, text=True)


T0 = datetime(2026, 10, 1, 12, 0)

# ----------------------------------------------------------------- Product 3
from session_tracker import ListeningSession, SessionTracker, SessionError
from exposure_engine import compute_exposure, allowed_hours, ExposureConfig
from risk_state import classify, RiskState, RiskThresholds
from recommendation_engine import RecommendationEngine


class TestExposure(unittest.TestCase):
    cfg = ExposureConfig()

    def test_allowed_hours_exchange_rate(self):
        for lvl, h in ((85, 8), (88, 4), (91, 2), (82, 16)):
            self.assertAlmostEqual(allowed_hours(lvl, self.cfg), h, places=9)

    def test_known_dose(self):
        r = compute_exposure([ListeningSession(T0, 60, 85, 85)])
        self.assertAlmostEqual(r.left.dose_pct, 12.5, places=6)
        self.assertAlmostEqual(r.dose_pct, 12.5, places=6)

    def test_below_floor_adds_nothing_and_empty_is_zero(self):
        self.assertEqual(compute_exposure([ListeningSession(T0, 60, 65, 65)]).dose_pct, 0.0)
        self.assertEqual(compute_exposure([]).dose_pct, 0.0)

    def test_worst_ear_reported(self):
        r = compute_exposure([ListeningSession(T0, 60, 80, 90)])
        self.assertEqual(r.worst_ear, "right")
        self.assertGreater(r.right.dose_pct, r.left.dose_pct)

    def test_invalid_input_rejected(self):
        bad = [(30, 150, 80), (30, 10, 80), (30, float("nan"), 80), (0, 80, 80), (-5, 80, 80),
               (float("nan"), 80, 80), (float("inf"), 80, 80), (30, 80, float("nan"))]
        for dur, l, r in bad:
            with self.subTest(dur=dur, l=l, r=r), self.assertRaises(SessionError):
                SessionTracker().add(ListeningSession(T0, dur, l, r))

    def test_rolling_window(self):
        t = SessionTracker()
        t.add(ListeningSession(T0 - timedelta(hours=26), 30, 85, 85))      # ended 25.5 h ago -> out
        t.add(ListeningSession(T0 - timedelta(hours=23), 30, 85, 85))      # ended 22.5 h ago -> in
        self.assertEqual(len(t.window(T0, 24)), 1)

    def test_state_boundaries_and_hysteresis(self):
        N, E, H = RiskState.NORMAL, RiskState.ELEVATED, RiskState.HIGH
        self.assertEqual([classify(x) for x in (49.9, 50, 99.9, 100)], [N, E, E, H])
        self.assertEqual(classify(46, E), E); self.assertEqual(classify(44, E), N)   # exit at 45
        self.assertEqual(classify(95, H), H); self.assertEqual(classify(85, H), E)   # exit at 90
        with self.assertRaises(ValueError):
            classify(10, N, RiskThresholds(elevated_pct=100, high_pct=50))

    def test_recommendation_policy(self):
        e = RecommendationEngine()
        self.assertFalse(e.recommend(RiskState.NORMAL, T0).notify)
        r = e.recommend(RiskState.ELEVATED, T0); self.assertTrue(r.notify)
        self.assertEqual(r.message, "Consider lowering volume.")
        self.assertFalse(e.recommend(RiskState.ELEVATED, T0 + timedelta(minutes=10)).notify)   # cooldown
        h = e.recommend(RiskState.HIGH, T0 + timedelta(minutes=11)); self.assertTrue(h.notify)  # escalation
        self.assertEqual(h.message, "Consider taking a listening break.")
        self.assertFalse(e.recommend(RiskState.HIGH, T0 + timedelta(minutes=20)).notify)
        self.assertTrue(e.recommend(RiskState.HIGH, T0 + timedelta(minutes=80)).notify)         # 60 min cooldown over

    def test_harness_survives_all_invalid_sessions(self):      # regression: used to raise TypeError
        m = load_main("product3_exposure", "p3_main")
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(m.run([ListeningSession(T0, 30, 150, 80, "bad")], "all invalid"))


# ----------------------------------------------------------------- Product 2
from connection_manager import ConnectionManager, Event
from separation_detector import SeparationDetector
from proximity_engine import ProximityEngine
from device_state import DeviceId, LastKnownLocation, ProximityBand, RecoveryState


def _loc(at):
    lab = "Bedroom" if at < datetime(2026, 10, 1, 22, 50) else "Living room"
    return LastKnownLocation(lab, 0.0, 0.0, 25.0, at)


class TestRecovery(unittest.TestCase):
    D = datetime(2026, 10, 1, 22, 48)

    def _lost_right(self, in_case=False):
        cm = ConnectionManager(_loc)
        cm.handle(Event("CONNECTED", DeviceId.LEFT, self.D, battery_pct=60, in_case=False))
        cm.handle(Event("CONNECTED", DeviceId.RIGHT, self.D, battery_pct=34, in_case=in_case))
        cm.handle(Event("DISCONNECTED", DeviceId.RIGHT, self.D + timedelta(minutes=7), reason="LINK_LOSS"))
        cm.handle(Event("HEARTBEAT", DeviceId.LEFT, self.D + timedelta(minutes=7, seconds=1), battery_pct=59, in_case=False))
        return cm

    def test_last_known_location_is_at_last_connection(self):
        cm = self._lost_right()   # disconnect noticed at 22:55 (phone now in Living room)
        self.assertEqual(cm.devices[DeviceId.RIGHT].last_known_location.label, "Bedroom")

    def test_debounce_and_confirmation(self):
        cm = self._lost_right(); t = self.D + timedelta(minutes=7)
        det = SeparationDetector()
        self.assertFalse(det.evaluate(cm.devices, t + timedelta(seconds=10))[0].confirmed)
        self.assertTrue(det.evaluate(cm.devices, t + timedelta(seconds=25))[0].confirmed)

    def test_docked_bud_is_not_separation(self):
        cm = self._lost_right(in_case=True)
        self.assertEqual(SeparationDetector().evaluate(cm.devices, self.D + timedelta(minutes=30)), [])

    def test_proximity_bands_trend_and_loss(self):
        p = ProximityEngine()
        for v in (-90, -86, -80, -72, -66, -60) + (-55,) * 8:      # median(5)+EMA lag: let the filter settle
            p.update(v)
        self.assertEqual(p.band, ProximityBand.STRONG); self.assertEqual(p.trend(), "CLOSER")
        for _ in range(4):
            p.update(None)
        self.assertEqual(p.band, ProximityBand.UNKNOWN)       # no advertisements -> no band

    def test_dead_battery_scenario(self):
        m = load_main("product2_recovery", "p2_main"); snap = {}
        with redirect_stdout(io.StringIO()):
            m.scenario_b(snap)
        d = snap["recoveryDeadBattery"]
        self.assertEqual(d["state"], RecoveryState.LIVE_UNAVAILABLE.value)
        self.assertFalse(d["liveTracking"])
        self.assertIn("Live proximity unavailable.", d["guidance"])
        self.assertIn("Last confirmed connection: Bedroom, 10:48 PM.", d["guidance"])

    def test_live_guidance_only_when_scanning(self):
        m = load_main("product2_recovery", "p2_main2"); snap = {}
        with redirect_stdout(io.StringIO()):
            m.scenario_a(snap)
        self.assertTrue(snap["recovery"]["liveTracking"])
        self.assertEqual(snap["status"]["right"]["connection"], "DISCONNECTED")


# ----------------------------------------------------------------- Product 4
from battery_model import BatteryConfig, TelemetryRecord, simulate_telemetry, by_bud
from health_estimator import estimate_health, HealthEstimate
from runtime_predictor import predict_runtime
from degradation_detector import trend


def _rec(cycle, p=40.0, listen=90.0, cap=185.0):
    drop = p * listen / 60 / cap * 100
    return TelemetryRecord(T0 + timedelta(days=cycle), "left", 100.0, 100.0 - drop, 4.0, 30.0, 50.0, cycle, listen, p)


class TestBattery(unittest.TestCase):
    cfg = BatteryConfig()

    def test_capacity_and_health_formula(self):
        h = estimate_health([_rec(i, cap=120.0) for i in range(6)], self.cfg)
        self.assertAlmostEqual(h.capacity_mwh, 120.0, places=6)               # 40 mW*1.5 h / 0.5
        self.assertAlmostEqual(h.health_pct, 100 * 120 / 185, places=6)

    def test_insufficient_or_shallow_data_rejected(self):
        with self.assertRaises(ValueError):
            estimate_health([_rec(i) for i in range(4)], self.cfg)
        shallow = [_rec(i, p=10.0, listen=30.0) for i in range(10)]            # dSOC ~ 2.7 pp -> excluded
        with self.assertRaises(ValueError):
            estimate_health(shallow, self.cfg)

    def test_runtime_formula(self):
        recs = [_rec(i, p=25.0) for i in range(6)]
        h = HealthEstimate(100 * 150 / 185, 150.0, 140.0, 160.0, 6, "high")
        rt = predict_runtime(recs, h, self.cfg, current_soc_pct=55.0)
        self.assertAlmostEqual(rt.hours, (55 - 5) / 100 * 150 / 25.0, places=9)  # 3.0 h

    def test_theil_sen_recovers_known_slope(self):
        recs = [_rec(c, cap=185.0 * (1 - 0.0002 * c)) for c in range(200)]      # -2.0 pts per 100 cycles
        self.assertAlmostEqual(trend(recs, self.cfg).slope_pp_per_100_cycles, -2.0, delta=0.05)

    def test_deterministic_and_expected_findings(self):
        a, b = simulate_telemetry(), simulate_telemetry()
        self.assertEqual(a, b)
        m = load_main("product4_battery", "p4_main")
        _, _, r1, f1 = m.analyse(); _, _, r2, f2 = m.analyse()
        self.assertEqual(r1["left"]["h"], r2["left"]["h"]); self.assertEqual([x.message for x in f1], [x.message for x in f2])
        self.assertTrue(88 <= r1["left"]["h"].health_pct <= 94)
        self.assertTrue(73 <= r1["right"]["h"].health_pct <= 82)
        self.assertLess(r1["right"]["tr"].slope_pp_per_100_cycles, r1["left"]["tr"].slope_pp_per_100_cycles)
        self.assertTrue(any(x.severity == "warning" and x.message.startswith("Right earbud") for x in f1))


# ----------------------------------------------------------------- Product 1
import numpy as np, audio_input as ai, metrics as mt


class TestSpeech(unittest.TestCase):
    def test_metrics_sanity(self):
        x = ai.synth_speech_like(2.0)
        self.assertAlmostEqual(mt.snr_db(x, 0.1 * x), 20.0, places=4)
        self.assertGreater(mt.si_sdr(x, x * 0.5), 60)                          # scale invariant

    def test_noise_lengths_match_input(self):
        for n in (16001, 31337, 48123):
            for k in ("traffic", "wind", "cafe", "mixed"):
                self.assertEqual(len(ai.synth_noise(k, n)), n)

    def test_end_to_end_metrics_and_determinism(self):
        with tempfile.TemporaryDirectory() as td:
            outs = []
            for i in range(2):
                j = os.path.join(td, f"w{i}.json")
                r = run_main("product1_speech_isolation", "--scenario", "wind", "--no-plot", "--out-dir", td, "--json", j)
                self.assertEqual(r.returncode, 0, r.stderr)
                outs.append(_read(j))
            self.assertEqual(outs[0], outs[1])                                  # deterministic
            m = outs[0]["metrics"]
            self.assertGreater(m["snr_improvement_db"], 3.0)
            self.assertLess(m["speech_attenuation_db"], 3.0)
            self.assertGreater(m["si_sdr_out_db"], m["si_sdr_in_db"])
            self.assertTrue((pathlib.Path(td) / "enhanced.wav").exists())
            # documented limitation: babble is NOT solved by single-channel enhancement
            j = os.path.join(td, "c.json")
            run_main("product1_speech_isolation", "--scenario", "cafe", "--no-plot", "--out-dir", td, "--json", j)
            self.assertLess(_read(j)["metrics"]["snr_improvement_db"], 2.0)

    def test_missing_file_is_clean_error(self):
        r = run_main("product1_speech_isolation", "--speech", "does_not_exist.wav")
        self.assertNotEqual(r.returncode, 0); self.assertIn("ERROR", r.stderr)


# ----------------------------------------------------------------- independent runs + snapshot
class TestIndependentRunsAndSnapshot(unittest.TestCase):
    def test_each_prototype_runs_standalone(self):
        for folder, extra in (("product2_recovery", []), ("product3_exposure", []), ("product4_battery", [])):
            r = run_main(folder, *extra)
            self.assertEqual(r.returncode, 0, f"{folder}: {r.stderr}")

    def test_snapshot_contents(self):
        f = ROOT / "node-api" / "data" / "snapshot.json"
        if not f.exists():
            self.skipTest("snapshot not exported yet (run scripts/export_snapshot.py)")
        s = json.loads(f.read_text())
        for k in ("context", "recovery", "exposure", "battery", "_meta"):
            self.assertIn(k, s)
        self.assertTrue(s["_meta"]["simulated"])
        self.assertEqual(s["battery"]["estimateType"], "prototype_soh_estimate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
