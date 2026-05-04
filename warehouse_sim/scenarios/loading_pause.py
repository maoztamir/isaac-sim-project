"""
Loading Pause scenario.

All three doors open at the start. At T=PAUSE_AT_SEC all doors close —
the FSM condition `any(d.is_open for d in doors)` becomes False, so no
forklift can transition from staging to loading. Queues form in staging
until doors reopen at T=PAUSE_AT_SEC + PAUSE_DURATION.

Levers (from C.SCENARIO_PRESETS["loading_pause"]):
  num_forklifts    = 3
  loading_duration = 8.0
  pause_at_sec     = 30.0
  pause_duration   = 20.0
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C

# ── Scenario knobs ────────────────────────────────────────────────────────────
PAUSE_AT_SEC   = 30.0   # sim-seconds before all doors close
PAUSE_DURATION = 20.0   # how long doors stay closed


class LoadingPauseScenario(Scenario):
    name = "loading_pause"
    num_forklifts = 3

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = 8.0
        self._pause_closed = False
        self._pause_reopened = False

    def _assign_initial_waypoints(self):
        """Open first and last gates only; timed close/reopen handled in on_step."""
        self.doors[0].open(self.stage)
        self.doors[-1].open(self.stage)
        self.doors[1].close(self.stage)
        print(f"[{self.name}] gates 0+2 open, gate 1 closed — "
              f"will pause at T={PAUSE_AT_SEC}s for {PAUSE_DURATION}s")

    def on_step(self, dt: float):
        # Close active gates (0 and 2) at pause time
        if not self._pause_closed and self.sim_time >= PAUSE_AT_SEC:
            for i in (0, 2):
                self.doors[i].close(self.stage)
                self.evt_log.log_door_close(self.sim_time, gate_idx=i)
            self._pause_closed = True
            print(f"[{self.name}] t={self.sim_time:.1f}s — gates 0+2 CLOSED "
                  f"(pause for {PAUSE_DURATION}s)")

        # Reopen active gates after pause duration
        if (self._pause_closed and not self._pause_reopened and
                self.sim_time >= PAUSE_AT_SEC + PAUSE_DURATION):
            for i in (0, 2):
                self.doors[i].open(self.stage)
                self.evt_log.log_door_open(self.sim_time, gate_idx=i)
            self._pause_reopened = True
            print(f"[{self.name}] t={self.sim_time:.1f}s — gates 0+2 REOPENED")
