"""device_state.py - data model for the three physical devices and their states.
All values are SIMULATED in this prototype; the real source is BLE/GATT events
from the phone OS plus battery reports sent by the buds/case while connected."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DeviceId(str, Enum):
    LEFT = "LEFT_BUD"
    RIGHT = "RIGHT_BUD"
    CASE = "CASE"


class ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class ProximityBand(str, Enum):
    UNKNOWN = "UNKNOWN"
    WEAK = "WEAK"
    MEDIUM = "MEDIUM"
    STRONG = "STRONG"


class RecoveryState(str, Enum):
    NOT_NEEDED = "NOT_NEEDED"                 # all expected devices connected / docked
    SEPARATION_SUSPECTED = "SEPARATION_SUSPECTED"   # disconnect seen, debouncing
    SEPARATED = "SEPARATED"                   # confirmed, show last-known location
    SEARCHING = "SEARCHING"                   # live BLE proximity guidance active
    LIVE_UNAVAILABLE = "LIVE_UNAVAILABLE"     # dead battery / no advertisements


@dataclass
class LastKnownLocation:
    label: str                 # user-named place, e.g. "Bedroom" (simulated place labelling)
    lat: float
    lon: float
    accuracy_m: float          # phone GPS/Wi-Fi accuracy: tens of metres outdoors, worse indoors
    timestamp: datetime
    source: str = "phone_location_at_last_connection (SIMULATED)"


@dataclass
class DeviceState:
    device_id: DeviceId
    connection: ConnectionState = ConnectionState.DISCONNECTED
    battery_pct: Optional[int] = None          # last REPORTED value (stale once disconnected)
    battery_reported_at: Optional[datetime] = None
    in_case: Optional[bool] = None             # docked in charging case (case-detect sensor)
    last_connected_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    last_known_location: Optional[LastKnownLocation] = None
    powered_off: bool = False                  # battery depleted -> radio silent
    history: list = field(default_factory=list)
