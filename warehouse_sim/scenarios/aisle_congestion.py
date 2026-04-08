"""
Aisle Congestion scenario: multiple forklifts funnel through
the same shelf aisle, creating queuing and tight-gap navigation.
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C
from .. import waypoints as wp


class AisleCongestionScenario(Scenario):
    name = "aisle_congestion"
    num_forklifts = 3

    def __init__(self, seed=42):
        super().__init__(seed)
        self._target_aisle_x = None

    def _assign_initial_waypoints(self):
        # Pick the middle aisle as the bottleneck
        if self.shelf_map.aisle_xs:
            mid = len(self.shelf_map.aisle_xs) // 2
            self._target_aisle_x = self.shelf_map.aisle_xs[mid]
        else:
            self._target_aisle_x = (C.NAV_X_MIN + C.NAV_X_MAX) / 2.0

        ax = self._target_aisle_x
        y_min = self.shelf_map.area_y_min or 2.0
        y_max = self.shelf_map.area_y_max or 25.0

        for fl in self.forklifts:
            # Each forklift: approach from a different angle, enter same aisle
            spread = (fl.id - 1) * 5.0
            route = [
                # Start position (south, spread out)
                (ax + spread, C.NAV_Y_MIN + 3.0 + fl.id * 2.0),
                # Converge on aisle entrance
                (ax, y_min - 1.0),
                # Drive up the aisle
                (ax, (y_min + y_max) / 2.0 + fl.id * 2.0),
                # Exit north
                (ax, y_max + 1.0),
                # Loop back south via open floor
                (ax + spread + 4.0, C.NAV_Y_MIN + 5.0),
            ]
            fl.set_waypoints(route, start_idx=fl.id)

    def on_step(self, dt):
        # Monitor how many forklifts are in the shelf area simultaneously
        if self.shelf_map.area_y_min is not None:
            in_aisle = sum(
                1 for fl in self.forklifts
                if self.shelf_map.in_shelf_area(fl.pos[1])
            )
            if in_aisle >= 2 and int(self.sim_time) % 10 == 0:
                print(f"[{self.name}] {in_aisle} forklifts in shelf area — "
                      f"congestion active")
