"""
Loading Pause scenario: one forklift stalls at the loading dock for an
extended period, forcing others to reroute or wait.
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C
from .. import waypoints as wp
from ..forklift import STATE_IDLE, STATE_LOADING


STALL_FORKLIFT = 0
STALL_DURATION = 15.0  # seconds the stalled forklift stays at the dock


class LoadingPauseScenario(Scenario):
    name = "loading_pause"
    num_forklifts = 3

    def __init__(self, seed=42):
        super().__init__(seed)
        self._stall_triggered = False

    def _assign_initial_waypoints(self):
        loading = self.zone_mgr.get("LoadingZone")
        shelves = self.zone_mgr.get("ShelvesArea")
        staging = self.zone_mgr.get("StagingArea")
        for fl in self.forklifts:
            if fl.id == STALL_FORKLIFT:
                # This one heads straight to the dock
                route = wp.gen_zone_route(
                    [loading], self.shelf_map, self.rng, points_per_zone=1
                )
            else:
                route = wp.gen_zone_route(
                    [staging, shelves, loading],
                    self.shelf_map, self.rng, points_per_zone=2
                )
            fl.set_waypoints(route, start_idx=0)

    def on_step(self, dt):
        loading = self.zone_mgr.get("LoadingZone")
        stall_fl = self.forklifts[STALL_FORKLIFT]

        # Once the stall forklift arrives at the loading zone, lock it there
        if (not self._stall_triggered and
                stall_fl.state == STATE_IDLE and
                loading.contains(stall_fl.pos[0], stall_fl.pos[1])):
            stall_fl.state = STATE_LOADING
            stall_fl.state_timer = STALL_DURATION
            self._stall_triggered = True
            print(f"[{self.name}] FL{STALL_FORKLIFT} stalled at dock for "
                  f"{STALL_DURATION}s!")
