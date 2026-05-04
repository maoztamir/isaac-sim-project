"""
EventLogger — append-only typed event queue.

Supported event types (use the EVENT_* constants):
  EVENT_DOOR_OPEN          Loading door opened
  EVENT_DOOR_CLOSE         Loading door closed
  EVENT_QUEUE_FORMED       Queue depth reached or exceeded threshold
  EVENT_BUILDUP_THRESHOLD  Staging area occupancy hit capacity limit
  EVENT_STATE_HOLD         Forklift held in a state longer than threshold
  EVENT_PALLET_TRANSFER    Pallet picked up or deposited
  EVENT_PROXIMITY_ALERT    Two forklifts within near-miss distance
  EVENT_IDLE_ALERT         Forklift idle in non-designated area past threshold

Each event is an Event namedtuple:
  Event(type, sim_time, payload)
  payload is a plain dict — contents vary by event type (see log_* methods).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

# ── Event type constants ──────────────────────────────────────────────────────
EVENT_DOOR_OPEN          = "door_open"
EVENT_DOOR_CLOSE         = "door_close"
EVENT_QUEUE_FORMED       = "queue_formed"
EVENT_BUILDUP_THRESHOLD  = "buildup_threshold"
EVENT_STATE_HOLD         = "state_hold"
EVENT_PALLET_TRANSFER    = "pallet_transfer"
EVENT_PROXIMITY_ALERT        = "proximity_alert"
EVENT_IDLE_ALERT             = "idle_alert"
EVENT_PEDESTRIAN_NEAR_MISS   = "pedestrian_near_miss"


@dataclass
class Event:
    type: str
    sim_time: float
    payload: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[t={self.sim_time:.2f}s] {self.type}  {self.payload}"


class EventLogger:
    """
    Append-only log of typed simulation events.

    All log_* methods append an Event immediately. Consumers can poll
    get_recent() or get_by_type() to read events without clearing the log.
    """

    def __init__(self, print_events: bool = False):
        """
        Parameters
        ----------
        print_events : bool
            If True, each logged event is also printed to stdout.
        """
        self._events: list[Event] = []
        self.print_events = print_events

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _append(self, evt: Event) -> None:
        self._events.append(evt)
        if self.print_events:
            print(f"  [EventLogger] {evt}")

    def log_door_open(self, sim_time: float, gate_idx: int) -> None:
        self._append(Event(EVENT_DOOR_OPEN, sim_time, {"gate_idx": gate_idx}))

    def log_door_close(self, sim_time: float, gate_idx: int) -> None:
        self._append(Event(EVENT_DOOR_CLOSE, sim_time, {"gate_idx": gate_idx}))

    def log_queue_formed(self, sim_time: float, zone_name: str,
                         depth: int, threshold: int) -> None:
        self._append(Event(EVENT_QUEUE_FORMED, sim_time, {
            "zone": zone_name,
            "depth": depth,
            "threshold": threshold,
        }))

    def log_buildup_threshold(self, sim_time: float, zone_name: str,
                              occupancy: int, capacity: int) -> None:
        self._append(Event(EVENT_BUILDUP_THRESHOLD, sim_time, {
            "zone": zone_name,
            "occupancy": occupancy,
            "capacity": capacity,
        }))

    def log_state_hold(self, sim_time: float, fl_id: int,
                       state: str, held_secs: float, threshold: float) -> None:
        self._append(Event(EVENT_STATE_HOLD, sim_time, {
            "fl_id": fl_id,
            "state": state,
            "held_secs": held_secs,
            "threshold": threshold,
        }))

    def log_pallet_transfer(self, sim_time: float, fl_id: int,
                            action: str, pallet_id: int | None = None,
                            location: tuple[float, float] | None = None) -> None:
        """action should be 'pickup' or 'deposit'."""
        self._append(Event(EVENT_PALLET_TRANSFER, sim_time, {
            "fl_id": fl_id,
            "action": action,
            "pallet_id": pallet_id,
            "location": location,
        }))

    def log_proximity_alert(self, sim_time: float,
                            fl_id_a: int, fl_id_b: int,
                            distance: float,
                            speed_a: float, speed_b: float) -> None:
        self._append(Event(EVENT_PROXIMITY_ALERT, sim_time, {
            "fl_id_a": fl_id_a,
            "fl_id_b": fl_id_b,
            "distance": distance,
            "speed_a": speed_a,
            "speed_b": speed_b,
        }))

    def log_idle_alert(self, sim_time: float, fl_id: int,
                       idle_secs: float, zone_name: str | None) -> None:
        self._append(Event(EVENT_IDLE_ALERT, sim_time, {
            "fl_id": fl_id,
            "idle_secs": idle_secs,
            "zone": zone_name,
        }))

    def log_pedestrian_near_miss(self, sim_time: float,
                                 fl_id: int, ped_id: int,
                                 distance: float, fl_speed: float,
                                 stopped: bool) -> None:
        self._append(Event(EVENT_PEDESTRIAN_NEAR_MISS, sim_time, {
            "fl_id":    fl_id,
            "ped_id":   ped_id,
            "distance": distance,
            "fl_speed": fl_speed,
            "stopped":  stopped,
        }))

    # ── Query API ─────────────────────────────────────────────────────────────

    def get_recent(self, n: int) -> list[Event]:
        """Return up to the last n events."""
        return self._events[-n:]

    def get_by_type(self, event_type: str) -> list[Event]:
        """Return all events of the given type."""
        return [e for e in self._events if e.type == event_type]

    def get_since(self, sim_time: float) -> list[Event]:
        """Return all events at or after the given sim_time."""
        return [e for e in self._events if e.sim_time >= sim_time]

    def count(self, event_type: str | None = None) -> int:
        if event_type is None:
            return len(self._events)
        return sum(1 for e in self._events if e.type == event_type)

    def clear(self) -> None:
        self._events.clear()

    def all_events(self) -> list[Event]:
        return list(self._events)
