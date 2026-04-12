"""
Aisle Congestion scenario.

Six forklifts are spawned clustered near the centre-aisle X coordinate.
Because the rule engine assigns pickup points by nearest aisle, most
forklifts are routed to the same corridor, creating congestion.
on_step() logs when two or more forklifts are simultaneously in the
shelf area.

Levers (from C.SCENARIO_PRESETS["aisle_congestion"]):
  num_forklifts    = 6
  loading_duration = 6.0
  target_aisle_x   = None  (auto-picked from ShelfMap on first physics step)
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C
from .. import isaac_helpers as ih


class AisleCongestionScenario(Scenario):
    name = "aisle_congestion"
    num_forklifts = 6

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = 6.0
        self._target_aisle_x: float | None = None   # resolved on first physics step
        self._congestion_logged_at: float = -999.0  # throttle log every 10 s

    def setup_forklifts(self):
        """Spawn all forklifts near the warehouse centre X so they share an aisle."""
        cluster_x = C.WAREHOUSE_CX   # ~-10.4 m — near the middle aisle
        spawn_y   = C.NAV_Y_MIN + 3.0
        for i in range(self.num_forklifts):
            # Spread slightly in X (±1 m) so they don't overlap on spawn
            sx = cluster_x + (i - self.num_forklifts // 2) * 1.2
            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           sx, spawn_y, 0.0, 90.0)
            fl_cls = self.forklifts.__class__  # list
            from ..models.forklift import Forklift
            self.forklifts.append(Forklift(i, path, sx, spawn_y))

    def _assign_initial_waypoints(self):
        """Open all doors; resolve middle aisle once ShelfMap is ready."""
        self.open_all_doors()
        if self.shelf_map.aisle_xs:
            mid = len(self.shelf_map.aisle_xs) // 2
            self._target_aisle_x = self.shelf_map.aisle_xs[mid]
            print(f"[{self.name}] target aisle X = {self._target_aisle_x:.2f}  "
                  f"({self.num_forklifts} forklifts converging)")

    def on_step(self, dt: float):
        """Log congestion whenever ≥2 forklifts are in the shelf area."""
        if self.shelf_map.area_y_min is None:
            return
        in_shelf = sum(
            1 for fl in self.forklifts
            if self.shelf_map.in_shelf_area(fl.pos[1])
        )
        if in_shelf >= 2 and self.sim_time - self._congestion_logged_at >= 10.0:
            self._congestion_logged_at = self.sim_time
            print(f"[{self.name}] t={self.sim_time:.1f}s — "
                  f"{in_shelf} forklifts in shelf area (congestion active)")
