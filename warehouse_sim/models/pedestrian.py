"""
Pedestrian: kinematic actor that walks a waypoint path at a fixed speed.

States
------
  walking  — moving toward current waypoint
  idle     — stationary (reached end of non-looping path, or explicitly set)
  stopped  — emergency halt (proximity trigger); optionally timed

The model is intentionally simple: straight-line segments between waypoints,
heading snapped to direction of travel.  No bicycle model, no collision
avoidance — safety logic lives in the base Scenario's proximity checker.
"""

from __future__ import annotations
import math

from .. import config as C
from .. import isaac_helpers as ih

STATE_WALKING = "walking"
STATE_IDLE    = "idle"
STATE_STOPPED = "stopped"

_WAYPOINT_REACH_DIST = 0.15   # metres — waypoint considered reached within this radius


class Pedestrian:
    """One pedestrian: kinematic movement along a waypoint list."""

    def __init__(self, ped_id: int, prim_path: str,
                 x: float, y: float, heading: float = 0.0):
        self.id        = ped_id
        self.prim_path = prim_path
        self.pos       = [x, y]
        self.heading   = heading   # degrees CCW from +X axis (same convention as Forklift)
        self.speed     = C.PEDESTRIAN_SPEED

        self.state     = STATE_WALKING
        self.waypoints: list[tuple[float, float]] = []
        self.wp_idx    = 0
        self.loop      = True      # wrap around at end of waypoint list

        self._resume_timer: float = 0.0   # counts down timed stops

    # ── Waypoint control ─────────────────────────────────────────────────────

    def set_waypoints(self, waypoints: list[tuple[float, float]],
                      loop: bool = True) -> None:
        self.waypoints = list(waypoints)
        self.wp_idx    = 0
        self.loop      = loop

    # ── State transitions ────────────────────────────────────────────────────

    def stop(self) -> None:
        """Emergency halt — remains stopped until resume() is called."""
        self.state = STATE_STOPPED
        self._resume_timer = 0.0

    def stop_for(self, duration: float) -> None:
        """Stop for *duration* seconds then automatically resume walking."""
        self.state = STATE_STOPPED
        self._resume_timer = duration

    def resume(self) -> None:
        self.state = STATE_WALKING
        self._resume_timer = 0.0

    def idle(self) -> None:
        """Park in place (does not auto-resume)."""
        self.state = STATE_IDLE

    # ── Geometry helpers ─────────────────────────────────────────────────────

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.pos[0] - x, self.pos[1] - y)

    # ── Per-frame update ─────────────────────────────────────────────────────

    def update(self, dt: float, stage) -> None:
        """Sync self.pos from the character prim (moved by omni.anim.people).

        Does NOT move the prim — omni.anim.people drives it.  We just read
        the world position so proximity checks stay accurate.
        """
        if self.state == STATE_STOPPED and self._resume_timer > 0.0:
            self._resume_timer -= dt
            if self._resume_timer <= 0.0:
                self.state = STATE_WALKING

        xy = ih.get_prim_world_xy(stage, self.prim_path)
        if xy is not None:
            self.pos = list(xy)

    def __repr__(self) -> str:
        return (f"Pedestrian(id={self.id}, state={self.state}, "
                f"pos=({self.pos[0]:.1f},{self.pos[1]:.1f}), "
                f"wp={self.wp_idx}/{len(self.waypoints)})")
