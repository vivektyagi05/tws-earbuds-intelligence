"""main.py - Product 2 end-to-end simulation (all hardware/BLE data SIMULATED).
Scenario A: right bud lost, then found using proximity guidance.
Scenario B: right bud battery dies -> live proximity unavailable."""
import argparse, json
from datetime import datetime, timedelta
from connection_manager import ConnectionManager, Event
from separation_detector import SeparationDetector
from proximity_engine import ProximityEngine, SimulatedBleScanner
from recovery_engine import build_guidance
from device_state import *

D0 = datetime(2026, 10, 1, 22, 42, 0)
PLACES = [(D0, "Bedroom", 27.4924, 77.6737), (D0 + timedelta(minutes=8), "Living room", 27.4925, 77.6738)]


def phone_location(at):          # SIMULATED room-level place label from the phone
    label, lat, lon = PLACES[0][1:] if at < D0 + timedelta(minutes=8) else PLACES[1][1:]
    return LastKnownLocation(label, lat, lon, accuracy_m=25.0, timestamp=at)


def show(title, g, now):
    print(f"[{now:%H:%M:%S}] {title}: state={g.state.value} proximity={g.proximity.value}")
    for l in g.lines:
        if l:
            print("            " + l)


def scenario_a(snapshot):
    print("\n===== SCENARIO A: lost right bud, found via BLE proximity =====")
    cm, det, prox = ConnectionManager(phone_location), SeparationDetector(), ProximityEngine()
    for d, b in ((DeviceId.LEFT, 62), (DeviceId.RIGHT, 34), (DeviceId.CASE, 80)):
        cm.handle(Event("CONNECTED", d, D0, battery_pct=b, in_case=(d == DeviceId.CASE) or False))
    cm.handle(Event("HEARTBEAT", DeviceId.RIGHT, D0 + timedelta(minutes=6), battery_pct=34, in_case=False))
    cm.handle(Event("HEARTBEAT", DeviceId.LEFT, D0 + timedelta(minutes=6), battery_pct=60, in_case=False))
    print("22:42 both earbuds connected.")
    t_dis = D0 + timedelta(minutes=6, seconds=10)
    cm.handle(Event("DISCONNECTED", DeviceId.RIGHT, t_dis, reason="LINK_LOSS"))
    cm.handle(Event("HEARTBEAT", DeviceId.LEFT, t_dis + timedelta(seconds=30), battery_pct=60, in_case=False))
    for dt in (5, 25):
        now = t_dis + timedelta(seconds=dt)
        show("status", build_guidance(cm.devices, det.evaluate(cm.devices, now), now,
                                       prox.band, prox.trend(), False), now)
    # user walks toward the bud: true distance (m) over time (SIMULATED path)
    path = lambda t: max(14 - 0.55 * t, 0.5)
    scanner = SimulatedBleScanner(path)
    start = D0 + timedelta(minutes=20)
    print("\n-- 23:02 user taps 'Find' and starts walking (BLE scan every 2 s) --")
    for t in range(0, 34, 2):
        now = start + timedelta(seconds=t)
        rssi = scanner.scan(t)
        prox.update(rssi)
        g = build_guidance(cm.devices, det.evaluate(cm.devices, now), now, prox.band, prox.trend(), True)
        print(f"t={t:2d}s true_dist={path(t):4.1f}m rssi={'  --' if rssi is None else f'{rssi:5.1f}'} "
              f"band={prox.band.value:<7} trend={prox.trend():<7} | {g.lines[0]}")
    snapshot["status"] = {
        "left": {"connection": "CONNECTED", "batteryPct": 60},
        "right": {"connection": "DISCONNECTED", "batteryPct": 34},
        "case": {"connection": "CONNECTED", "batteryPct": 80}}
    snapshot["recovery"] = {"state": g.state.value, "device": g.device.value, "proximity": g.proximity.value,
                            "liveTracking": g.live_tracking, "guidance": [l for l in g.lines if l]}
    print("\nEvent log:"); [print("  " + l) for l in cm.log]


def scenario_b(snapshot):
    print("\n===== SCENARIO B: right bud battery depleted =====")
    cm, det = ConnectionManager(phone_location), SeparationDetector()
    cm.handle(Event("CONNECTED", DeviceId.LEFT, D0, battery_pct=60, in_case=False))
    cm.handle(Event("CONNECTED", DeviceId.RIGHT, D0, battery_pct=34, in_case=False))
    cm.handle(Event("HEARTBEAT", DeviceId.RIGHT, D0 + timedelta(minutes=6), battery_pct=34, in_case=False))
    cm.handle(Event("DISCONNECTED", DeviceId.RIGHT, D0 + timedelta(minutes=6, seconds=1), reason="LINK_LOSS"))
    # later the bud drains to zero while away from the phone: radio goes silent, nobody tells us.
    cm.handle(Event("HEARTBEAT", DeviceId.LEFT, D0 + timedelta(minutes=40), battery_pct=41, in_case=False))
    cm.devices[DeviceId.RIGHT].powered_off = True       # inferred: no advertisements + last batt low (SIMULATED)
    scanner = SimulatedBleScanner(lambda t: 3.0); scanner.advertising = False
    prox = ProximityEngine()
    for t in range(5):
        prox.update(scanner.scan(t))
    now = D0 + timedelta(hours=1)
    g = build_guidance(cm.devices, det.evaluate(cm.devices, now), now, prox.band, prox.trend(), True)
    show("status", g, now)
    snapshot["recoveryDeadBattery"] = {"state": g.state.value, "liveTracking": g.live_tracking,
                                       "guidance": [l for l in g.lines if l]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--json")
    a = ap.parse_args()
    snap = {}
    scenario_a(snap); scenario_b(snap)
    if a.json:
        json.dump(snap, open(a.json, "w"), indent=2)
