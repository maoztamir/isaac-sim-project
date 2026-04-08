"""
Area Build-Up scenario: all forklifts converge on the StagingArea,
causing crowding and dwell-time accumulation.
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C
from .. import waypoints as wp
from ..forklift import STATE_DRIVE


BUILDUP_THRESHOLD = 3       # occupancy that triggers a warning
DWELL_WARN_SECS   = 10.0    # seconds before per-forklift dwell warning


class AreaBuildUpScenario(Scenario):
    name = "area_buildup"
    num_forklifts = 4

    def _assign_initial_waypoints(self):
        staging = self.zone_mgr.get("StagingArea")
        shelves = self.zone_mgr.get("ShelvesArea")
        for fl in self.forklifts:
            # Heavy bias toward staging: 3 staging waypoints, 1 shelf
            route = (
                [wp.rand_zone_point(staging, self.shelf_map, self.rng)
                 for _ in range(3)]
                + [wp.rand_floor_point(self.shelf_map, self.rng, prefer_aisle=True)]
            )
            fl.set_waypoints(route, start_idx=fl.id)

    def on_step(self, dt):
        staging = self.zone_mgr.get("StagingArea")

        # Monitor build-up
        if staging.occupancy >= BUILDUP_THRESHOLD:
            for fl_id in staging.occupant_ids:
                dwell = staging.dwell_time(fl_id, self.sim_time)
                if dwell > DWELL_WARN_SECS:
                    print(f"[{self.name}] WARNING: FL{fl_id} in StagingArea "
                          f"for {dwell:.1f}s (build-up)")

        # Re-route forklifts that finish their loop back to staging
        for fl in self.forklifts:
            if (fl.state == STATE_DRIVE and
                    fl.wp_idx == 0 and
                    len(fl.waypoints) > 0):
                route = (
                    [wp.rand_zone_point(staging, self.shelf_map, self.rng)
                     for _ in range(3)]
                    + [wp.rand_floor_point(self.shelf_map, self.rng,
                                           prefer_aisle=True)]
                )
                fl.set_waypoints(route)
