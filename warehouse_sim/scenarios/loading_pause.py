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
        """Open all doors at start; timed close/reopen handled in on_step."""
        self.open_all_doors()
        print(f"[{self.name}] doors open — will pause at T={PAUSE_AT_SEC}s "
              f"for {PAUSE_DURATION}s")

    def on_step(self, dt: float):
        # Close all doors at pause time
        if not self._pause_closed and self.sim_time >= PAUSE_AT_SEC:
            self.close_all_doors()
            self._pause_closed = True
            for i in range(len(self.doors)):
                self.evt_log.log_door_close(self.sim_time, gate_idx=i)
            print(f"[{self.name}] t={self.sim_time:.1f}s — all doors CLOSED "
                  f"(pause for {PAUSE_DURATION}s)")

        # Reopen all doors after pause duration
        if (self._pause_closed and not self._pause_reopened and
                self.sim_time >= PAUSE_AT_SEC + PAUSE_DURATION):
            self.open_all_doors()
            self._pause_reopened = True
            for i in range(len(self.doors)):
                self.evt_log.log_door_open(self.sim_time, gate_idx=i)
            print(f"[{self.name}] t={self.sim_time:.1f}s — all doors REOPENED")
