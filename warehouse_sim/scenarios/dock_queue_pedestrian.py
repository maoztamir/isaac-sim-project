"""
Dock Queue with Pedestrian scenario.

Identical to dock_queue (4 forklifts queuing at the loading dock) but adds
one warehouse worker walking a rectangular patrol through the main floor area
between the loading zone and the shelves.
"""

from __future__ import annotations
from .. import config as C
from .dock_queue import DockQueueScenario


class DockQueuePedestrianScenario(DockQueueScenario):
    name = "dock_queue_pedestrian"

    def setup_pedestrians(self):
        # Rectangular patrol through the main open floor, clear of shelf aisles.
        x_west = C.NAV_X_MIN + 2.0    # -22.5 — near west wall
        x_east = C.NAV_X_MAX - 2.0    #   1.5 — near east wall
        y_near = C.WALL_Y_MIN + C.LOAD_D + 1.5   # just north of loading zone
        y_far  = C.STAGING_Y_FAR + 1.0            # just north of staging area

        self.spawn_pedestrian(
            waypoints=[
                (x_west, y_near),
                (x_east, y_near),
                (x_east, y_far),
                (x_west, y_far),
            ],
            loop=True,
        )
