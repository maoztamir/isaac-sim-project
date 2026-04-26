"""
DoorCycleScenario — periodic door open/close to test door-status detection.

Three loading dock gates cycle independently so the detection system always
sees a mix of open/closed states.  Three forklifts run the normal FSM and
naturally queue when a door closes mid-approach, then proceed on re-open.

Knobs
-----
OPEN_DURATION    seconds each door stays open
CLOSED_DURATION  seconds each door stays closed

Initial phase offsets are chosen so the doors never all toggle simultaneously:
  door 0 — starts OPEN,   expires after OPEN_DURATION        (first to toggle)
  door 1 — starts CLOSED, expires after CLOSED_DURATION*0.5  (toggles mid-cycle)
  door 2 — starts OPEN,   expires after OPEN_DURATION*0.7    (toggles late)
"""

from __future__ import annotations

from .base import Scenario
from .. import config as C

OPEN_DURATION   = 20.0   # seconds a door stays open
CLOSED_DURATION = 10.0   # seconds a door stays closed
LOG_INTERVAL    = 5.0    # seconds between door-state telemetry lines


class DoorCycleScenario(Scenario):
    name = "door_cycle"
    num_forklifts = 3

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        # Per-door countdown timers (populated in _assign_initial_waypoints)
        self._door_timers: list[float] = []
        self._log_timer: float = 0.0

    # ── Initial state ────────────────────────────────────────────────────────

    def _assign_initial_waypoints(self):
        """Stagger door phases so transitions don't all happen at once."""
        initial = [
            (True,  OPEN_DURATION),          # door 0: open, full open window
            (False, CLOSED_DURATION * 0.5),  # door 1: closed, half closed window
            (True,  OPEN_DURATION * 0.7),    # door 2: open, 70 % open window
        ]
        self._door_timers = []
        for i, (is_open, timer) in enumerate(initial):
            if is_open:
                self.doors[i].open(self.stage)
            else:
                self.doors[i].close(self.stage)
            self._door_timers.append(timer)
            state_str = "OPEN" if is_open else "CLOSED"
            print(f"[{self.name}] door {i} → {state_str}  (next toggle in {timer:.1f} s)")

    # ── Per-frame logic ───────────────────────────────────────────────────────

    def on_step(self, dt: float):
        self._tick_doors(dt)
        self._tick_status_log(dt)

    def _tick_doors(self, dt: float):
        for i, door in enumerate(self.doors):
            self._door_timers[i] -= dt
            if self._door_timers[i] > 0.0:
                continue

            # Timer expired — flip the door
            if door.is_open:
                door.close(self.stage)
                self._door_timers[i] = CLOSED_DURATION
                print(f"[{self.name}] t={self.sim_time:.1f}s  door {i}  OPEN → CLOSED"
                      f"  (stays closed {CLOSED_DURATION:.0f} s)")
            else:
                door.open(self.stage)
                self._door_timers[i] = OPEN_DURATION
                print(f"[{self.name}] t={self.sim_time:.1f}s  door {i}  CLOSED → OPEN"
                      f"  (stays open {OPEN_DURATION:.0f} s)")

    def _tick_status_log(self, dt: float):
        self._log_timer += dt
        if self._log_timer < LOG_INTERVAL:
            return
        self._log_timer = 0.0

        states = "  ".join(
            f"door_{i}={'OPEN  ' if d.is_open else 'CLOSED'}"
            for i, d in enumerate(self.doors)
        )
        fl_states = "  ".join(
            f"FL{fl.id}={fl.state}" for fl in self.forklifts
        )
        print(f"[{self.name}] t={self.sim_time:.0f}s | {states} | {fl_states}")
