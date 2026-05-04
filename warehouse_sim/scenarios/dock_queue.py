"""
Dock Queue scenario.

Long loading duration (20 s) with a single dock slot causes forklifts to
queue up in staging while waiting their turn. Demonstrates queue formation
and dock-capacity bottleneck detection.

Levers (from C.SCENARIO_PRESETS["dock_queue"]):
  num_forklifts    = 4
  loading_duration = 20.0   — long dock time drives queue build-up
  dock_capacity    = 1      — one slot at a time (LOADING_AREA_CAPACITY)
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C
from .. import isaac_helpers as ih
from ..models.forklift import Forklift

# Seconds between each forklift's first departure — prevents all forklifts
# from arriving at the pickup point simultaneously and deadlocking on U-turn.
_STAGGER_SECS = 5.0

# Gate index that is closed for this scenario (unused dock).
# Gate 0 = left (offset -7), gate 1 = centre (offset 0), gate 2 = right (offset +7).
_CLOSED_GATE = 1  # middle door closed; gates 0 (left) and 2 (right) are active


class DockQueueScenario(Scenario):
    name = "dock_queue"
    num_forklifts = 4

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = 20.0   # long → queue builds naturally

    def setup_forklifts(self):
        """Spawn forklifts with staggered start timers."""
        for i in range(self.num_forklifts):
            sx = C.NAV_X_MIN + 3.0 + i * 7.0
            sy = C.NAV_Y_MIN + 3.0
            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           sx, sy, 0.0, 90.0)
            fl = Forklift(i, path, sx, sy)
            # Stagger: FL0 starts immediately, FL1 after 5 s, FL2 after 10 s …
            fl.state_timer = i * _STAGGER_SECS
            self.forklifts.append(fl)

    def _assign_initial_waypoints(self):
        """Open doors 0 and 2; close door 1 (middle).
        open() automatically shows the dock crate; close() hides it."""
        for i, door in enumerate(self.doors):
            if i == _CLOSED_GATE:
                door.close(self.stage)
            else:
                door.open(self.stage)
        print(f"[{self.name}] doors 0+2 open, door {_CLOSED_GATE} closed — "
              f"{self.num_forklifts} forklifts staggered by {_STAGGER_SECS}s, "
              f"loading duration {self.loading_duration}s")
