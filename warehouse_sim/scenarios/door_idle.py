"""
Door Idle scenario — WAREHOUSE_DOOR_IDLE_003.

SpecScenario subclass. Camera, pallets, and door states come from the spec.
Forklifts are spawned directly here as background patrol actors that move with
natural bicycle-steering between two waypoints, never approaching the idle door.
IRA pedestrians walk continuous east/west patrol loops.

Spec: docs/scenarios/003_door_idle.txt
"""

from __future__ import annotations
import math

from .spec_runner import SpecScenario
from .. import config as C
from .. import isaac_helpers as ih
from .. import waypoints as wp
from ..models.forklift import Forklift
from .specs.door_idle import SPEC


class DoorIdleScenario(SpecScenario):

    # Enable IRA navmesh loader so pedestrians can walk autonomously.
    _use_ira_loader = True

    def __init__(self, seed: int = 42):
        super().__init__(SPEC, seed=seed)
        self._door_idle_secs  = 0.0
        self._print_timer     = 0.0
        # Populated in setup_forklifts()
        self._bg_endpoints: list[tuple] = []
        self._bg_at_far:    list[bool]  = []

    # ── Background forklifts ──────────────────────────────────────────────────

    def setup_forklifts(self):
        """Two patrol forklifts: left side (gate 0 column) and right side (gate 2 column).

        Each shuttles between its far-staging position (north) and its staging-hold
        position (south) using the forklift's natural bicycle-steering model.
        They start far from the centre so _preferred_gate never routes them to gate 1.
        """
        self._bg_endpoints = [
            (wp.named_position("far_approach_0"), wp.named_position("staging_hold_0")),
            (wp.named_position("far_approach_2"), wp.named_position("staging_hold_2")),
        ]
        self._bg_at_far = [True, True]   # each forklift starts at the far end

        for i, (far_pt, near_pt) in enumerate(self._bg_endpoints):
            sx, sy = far_pt
            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           sx, sy, 0.0, 0.0)
            fl = Forklift(i, path, sx, sy, heading=0.0)
            fl.state = C.STATE_RETURNING   # moving state → uses _tick_drive
            fl.set_waypoints([near_pt])    # first leg: drive south to staging
            self.forklifts.append(fl)

    # ── Pedestrians ───────────────────────────────────────────────────────────

    def setup_pedestrians(self):
        """Two background patrol loops — east and west of the centre aisle."""
        self.spawn_pedestrian(waypoints=[
            ( -3.0, -13.0),
            ( -3.0,   4.0),
            ( -9.0,   4.0),
            ( -9.0, -13.0),
        ], loop=True)

        self.spawn_pedestrian(waypoints=[
            (-16.0, -13.0),
            (-16.0,   4.0),
            (-22.0,   4.0),
            (-22.0, -13.0),
        ], loop=True)

    # ── Per-step ──────────────────────────────────────────────────────────────

    def on_step(self, dt: float) -> None:
        super().on_step(dt)   # TimelineDirector.tick() — no-op (empty timeline)

        # Patrol reassignment: when a forklift reaches its waypoint, toggle
        # direction and send it to the other end of the patrol corridor.
        for i, fl in enumerate(self.forklifts):
            if not fl.waypoints:
                far_pt, near_pt = self._bg_endpoints[i]
                self._bg_at_far[i] = not self._bg_at_far[i]
                fl.set_waypoints([far_pt if self._bg_at_far[i] else near_pt])
                fl.state = C.STATE_RETURNING

        # door_idle observability
        self._door_idle_secs += dt
        self._print_timer    += dt
        if self._print_timer < 2.0:
            return
        self._print_timer = 0.0

        door_x = C.WAREHOUSE_CX + C.GATE_OFFSETS[1]
        door_y = C.WALL_Y_MIN

        if self.forklifts:
            nearest = min(
                math.hypot(fl.pos[0] - door_x, fl.pos[1] - door_y)
                for fl in self.forklifts
            )
        else:
            nearest = float("inf")

        print(
            f"[door_idle] t={self.sim_time:.1f}s  "
            f"door_idle_duration={self._door_idle_secs:.1f}s  "
            f"dock_occupied=False  "
            f"forklift_proximity_to_door={nearest:.1f}m"
        )
