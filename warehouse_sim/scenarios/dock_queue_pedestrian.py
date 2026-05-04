"""
Dock Queue with Pedestrians scenario.

Identical to dock_queue (4 forklifts queuing at the dock, long loading duration)
but adds two warehouse workers walking through active forklift traffic areas:

  Worker 0 — crosses east-west through the staging area where forklifts queue.
             High chance of triggering pedestrian_near_miss events.

  Worker 1 — walks north-south along the west aisle between the loading zone
             and the shelf area.  Lower traffic, demonstrates background patrol.
"""

from __future__ import annotations
from .. import config as C
from .dock_queue import DockQueueScenario


class DockQueuePedestrianScenario(DockQueueScenario):
    name = "dock_queue_pedestrian"

    def setup_pedestrians(self):
        stag_y  = C.STAGING_CENTER_Y
        west_x  = C.NAV_X_MIN + 1.5   # near west wall, clear of forklift lanes
        east_x  = C.NAV_X_MAX - 1.5   # near east wall

        # Worker 0: east-west patrol through the staging area
        self.spawn_pedestrian(
            x=west_x, y=stag_y,
            waypoints=[(east_x, stag_y), (west_x, stag_y)],
            loop=True,
        )

        # Worker 1: north-south patrol on the west side (loading zone → shelves)
        load_y   = C.WALL_Y_MIN + C.LOAD_D + 1.0   # just north of loading zone
        shelf_y  = C.STAGING_Y_FAR + 2.0            # just north of staging
        patrol_x = C.NAV_X_MIN + 2.5

        self.spawn_pedestrian(
            x=patrol_x, y=load_y,
            waypoints=[(patrol_x, shelf_y), (patrol_x, load_y)],
            loop=True,
        )
