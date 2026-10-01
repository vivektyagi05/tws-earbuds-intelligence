"""recovery_engine.py - combines state + separation + proximity into user guidance.
Warmer/colder guidance is based on filtered RSSI trend/bands. When the bud is not
transmitting, live proximity is unavailable. Honesty rules: never show live tracking without live evidence (fresh advertisements);
never claim a position - only last confirmed connection and coarse signal bands."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from device_state import *
from separation_detector import Separation


@dataclass
class Guidance:
    state: RecoveryState
    device: Optional[DeviceId]
    lines: List[str] = field(default_factory=list)
    proximity: ProximityBand = ProximityBand.UNKNOWN
    live_tracking: bool = False


def _fmt_time(ts):
    return ts.strftime("%I:%M %p").lstrip("0")


def _name(d: DeviceId):
    return d.value.replace("_", " ").lower()


# NOTE: guidance targets ONE bud at a time (first confirmed separation).
def build_guidance(devices, separations: List[Separation], now: datetime,
                   band: ProximityBand, trend: str, scanning: bool) -> Guidance:
    if not separations:
        return Guidance(RecoveryState.NOT_NEEDED, None, ["All earbuds accounted for."])
    s = next((x for x in separations if x.confirmed), separations[0])
    d = devices[s.device]
    if not s.confirmed:
        return Guidance(RecoveryState.SEPARATION_SUSPECTED, s.device,
                        [f"Checking the {_name(s.device)} connection..."])
    loc = d.last_known_location
    last = (f"Last confirmed connection: {loc.label}, {_fmt_time(d.last_connected_at)}."
            if loc and d.last_connected_at else "No confirmed location available.")
    batt = (f"Last reported battery: {d.battery_pct}% (as of {_fmt_time(d.battery_reported_at)})."
            if d.battery_pct is not None else "")
    # Dead battery -> NO fake live tracking
    if d.powered_off or d.battery_pct == 0:
        return Guidance(RecoveryState.LIVE_UNAVAILABLE, s.device,
                        ["Live proximity unavailable.", last, batt,
                         "The earbud is not transmitting. Search where you last used it; "
                         "live guidance resumes if it is charged or placed in its case."])
    if not scanning or band == ProximityBand.UNKNOWN:
        return Guidance(RecoveryState.SEPARATED, s.device,
                        [f"{_name(s.device).capitalize()} disconnected.", last, batt,
                         "Tap 'Find' and walk toward it to see live signal strength."])
    msg = {"CLOSER": f"You are getting closer to the {_name(s.device)}.",
           "FARTHER": f"You are moving away from the {_name(s.device)}.",
           "STEADY": f"Signal steady - try moving to a different spot.",
           "UNKNOWN": f"Searching for the {_name(s.device)}..."}[trend]
    hint = {ProximityBand.STRONG: "Signal strong: it is likely within a few metres.",
            ProximityBand.MEDIUM: "Signal medium: probably in the same area/room.",
            ProximityBand.WEAK: "Signal weak: probably several rooms or metres away."}[band]
    return Guidance(RecoveryState.SEARCHING, s.device, [msg, hint, last, batt],
                    proximity=band, live_tracking=True)
