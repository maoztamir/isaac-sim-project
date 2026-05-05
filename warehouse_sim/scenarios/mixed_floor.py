"""
Mixed Floor scenario: 3 forklifts + 3 IRA-animated pedestrians.

Forklifts run the standard FSM dock-cycle (shelves → staging → dock → return)
with staggered starts so they naturally spread across the floor.  Pedestrians
walk rectangular patrol routes distributed east/centre/west so their paths
cross the forklifts' travel lanes — demonstrating mixed human/vehicle traffic.
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C
from .. import isaac_helpers as ih
from ..models.forklift import Forklift

_STAGGER_SECS   = 6.0   # seconds between successive forklift departures
_LOADING_SECS   = 8.0   # dock transfer time — long enough to observe queuing


class MixedFloorScenario(Scenario):
    name          = "mixed_floor"
    num_forklifts = 3
    _use_ira_loader = True   # warehouse opens as root stage for navmesh baking

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = _LOADING_SECS

    # ── Forklifts ─────────────────────────────────────────────────────────────

    def setup_forklifts(self):
        """3 forklifts near the south wall, staggered starts."""
        for i in range(self.num_forklifts):
            sx   = C.NAV_X_MIN + 4.0 + i * 8.0   # spread across X
            sy   = C.NAV_Y_MIN + 3.0
            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           sx, sy, 0.0, 90.0)
            fl = Forklift(i, path, sx, sy)
            fl.state_timer = i * _STAGGER_SECS   # staggered first departure
            self.forklifts.append(fl)

    # ── Pedestrians ───────────────────────────────────────────────────────────

    def setup_pedestrians(self):
        """3 pedestrians: east / centre / west patrol rectangles."""
        # East patrol — X -3 to -9, Y -13 to 4
        self.spawn_pedestrian(waypoints=[
            ( -3.0, -13.0),
            ( -3.0,   4.0),
            ( -9.0,   4.0),
            ( -9.0, -13.0),
        ], loop=True)

        # Centre patrol — X -10 to -15, Y -13 to 4
        self.spawn_pedestrian(waypoints=[
            (-10.0,   4.0),
            (-10.0, -13.0),
            (-15.0, -13.0),
            (-15.0,   4.0),
        ], loop=True)

        # West patrol — X -16 to -22, Y -13 to 4
        self.spawn_pedestrian(waypoints=[
            (-16.0, -13.0),
            (-16.0,   4.0),
            (-22.0,   4.0),
            (-22.0, -13.0),
        ], loop=True)

    # ── Initial state ─────────────────────────────────────────────────────────

    def _assign_initial_waypoints(self):
        """Open all three dock doors at start."""
        self.open_all_doors()
        print(f"[{self.name}] All dock doors open — "
              f"{self.num_forklifts} forklifts staggered by {_STAGGER_SECS}s, "
              f"loading duration {self.loading_duration}s")
