"""
Area Build-Up scenario.

Five forklifts cycle through the warehouse with a 12 s loading duration.
Because loading is slow and dock capacity = 1, forklifts accumulate in
staging faster than they can be released — staging fills up and
buildup threshold events fire from base._check_area_thresholds().

Levers (from C.SCENARIO_PRESETS["area_buildup"]):
  num_forklifts    = 5
  loading_duration = 12.0   — slow release from staging
  release_interval = 8.0    — (informational — slowness comes from loading_duration)
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C

# Dwell threshold for a per-forklift warning printed in on_step
DWELL_WARN_SECS = 15.0


class AreaBuildUpScenario(Scenario):
    name = "area_buildup"
    num_forklifts = 5

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = 12.0

    def _assign_initial_waypoints(self):
        """Open all doors; FSM cycles forklifts; slow loading causes staging build-up."""
        self.open_all_doors()
        print(f"[{self.name}] {self.num_forklifts} forklifts, "
              f"{self.loading_duration}s loading — staging build-up expected")

    def on_step(self, dt: float):
        """Log per-forklift dwell warnings when staging gets crowded."""
        staging = self.area_mgr.get("StagingArea")
        if staging is None:
            return
        if staging.occupancy >= 3:
            for fl_id in staging.occupant_ids:
                dwell = staging.dwell_time(fl_id, self.sim_time)
                if dwell >= DWELL_WARN_SECS:
                    print(f"[{self.name}] t={self.sim_time:.1f}s  "
                          f"FL{fl_id} in StagingArea for {dwell:.1f}s — build-up")
