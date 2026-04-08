"""
Dock Queue scenario: forklifts queue up at the LoadingZone,
wait their turn, then cycle back through StagingArea.
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C
from .. import waypoints as wp
from ..forklift import STATE_DRIVE, STATE_IDLE


class DockQueueScenario(Scenario):
    name = "dock_queue"
    num_forklifts = 4

    def setup_forklifts(self):
        """Spawn forklifts spread across the staging area."""
        starts = [
            (C.NAV_X_MIN + 3.0, C.NAV_Y_MIN + 3.0),
            (C.NAV_X_MIN + 3.0, C.NAV_Y_MIN + 7.0),
            (C.NAV_X_MIN + 8.0, C.NAV_Y_MIN + 3.0),
            (C.NAV_X_MIN + 8.0, C.NAV_Y_MIN + 7.0),
        ]
        from .. import isaac_helpers as ih
        from ..forklift import Forklift
        for i, (sx, sy) in enumerate(starts):
            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           sx, sy, 0.0, 90.0)
            self.forklifts.append(Forklift(i, path, sx, sy))

    def _assign_initial_waypoints(self):
        """Route: StagingArea -> LoadingZone -> ShelvesArea -> loop."""
        staging = self.zone_mgr.get("StagingArea")
        loading = self.zone_mgr.get("LoadingZone")
        shelves = self.zone_mgr.get("ShelvesArea")
        for fl in self.forklifts:
            route = wp.gen_zone_route(
                [staging, loading, shelves],
                self.shelf_map, self.rng, points_per_zone=2
            )
            fl.set_waypoints(route, start_idx=fl.id * 2)

    def on_step(self, dt):
        """When a forklift enters LoadingZone and goes idle, extend its pause."""
        loading = self.zone_mgr.get("LoadingZone")
        for fl in self.forklifts:
            if fl.state == STATE_IDLE and loading.contains(fl.pos[0], fl.pos[1]):
                fl.enter_loading()

            # Re-route when waypoints exhausted
            if fl.state == STATE_DRIVE and fl.wp_idx == 0 and len(fl.waypoints) > 0:
                # Already looping — re-gen on completion
                pass
