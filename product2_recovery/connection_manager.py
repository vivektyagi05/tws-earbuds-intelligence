"""connection_manager.py - the single owner of device state.
Consumes events (what the phone's Bluetooth stack would deliver) and updates
DeviceState. KEY RULE: a bud's last-known location is the phone's location at the
LAST MOMENT IT WAS CONNECTED - not the phone's location when we notice the loss."""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Optional
from device_state import *


@dataclass
class Event:
    type: str                      # CONNECTED | DISCONNECTED | HEARTBEAT | BATTERY | IN_CASE
    device: DeviceId
    at: datetime
    battery_pct: Optional[int] = None
    in_case: Optional[bool] = None
    reason: Optional[str] = None   # e.g. "LINK_LOSS", "BATTERY_DEAD"


class ConnectionManager:
    def __init__(self, location_provider: Callable[[datetime], LastKnownLocation]):
        self._loc = location_provider
        self.devices: Dict[DeviceId, DeviceState] = {d: DeviceState(d) for d in DeviceId}
        self.log: list = []

    def handle(self, ev: Event):
        d = self.devices.get(ev.device)
        if d is None:
            raise ValueError(f"unknown device {ev.device}")
        if ev.battery_pct is not None:
            if not 0 <= ev.battery_pct <= 100:
                raise ValueError("battery_pct out of range")
            d.battery_pct, d.battery_reported_at = ev.battery_pct, ev.at
        if ev.in_case is not None:
            d.in_case = ev.in_case
        if ev.type in ("CONNECTED", "HEARTBEAT"):
            d.connection, d.powered_off, d.disconnected_at = ConnectionState.CONNECTED, False, None
            d.last_connected_at = ev.at
            d.last_known_location = self._loc(ev.at)       # refreshed while link is alive
        elif ev.type == "DISCONNECTED":
            if d.connection == ConnectionState.CONNECTED:
                d.disconnected_at = ev.at
            d.connection = ConnectionState.DISCONNECTED
            if ev.reason == "BATTERY_DEAD" or (ev.battery_pct == 0):
                d.powered_off = True
        elif ev.type not in ("BATTERY", "IN_CASE"):
            raise ValueError(f"unknown event type {ev.type}")
        self.log.append(f"{ev.at:%H:%M:%S} {ev.device.value:<9} {ev.type}"
                        + (f" ({ev.reason})" if ev.reason else "")
                        + (f" batt={ev.battery_pct}%" if ev.battery_pct is not None else ""))
