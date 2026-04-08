"""
Forklift finite state machine and movement.
"""

from __future__ import annotations
import math

from . import config as C
from . import isaac_helpers as ih
from .shelves import ShelfMap


# ── FSM States ──────────────────────────────────────────────────────────────
STATE_DRIVE   = "drive"
STATE_IDLE    = "idle"     # paused at a waypoint (pickup/dropoff)
STATE_LOADING = "loading"  # at loading dock, longer pause
STATE_WAITING = "waiting"  # queued behind another forklift


class Forklift:
    """One forklift: kinematic state + FSM + movement logic."""

    def __init__(self, fl_id: int, prim_path: str, x: float, y: float,
                 heading: float = 90.0):
        self.id = fl_id
        self.prim_path = prim_path
        self.pos = [x, y]
        self.heading = heading
        self.speed = 0.0
        self.steer_angle = 0.0

        # FSM
        self.state = STATE_DRIVE
        self.state_timer = 0.0

        # Waypoints
        self.waypoints: list[tuple[float, float]] = []
        self.wp_idx = 0

    # ── Public interface ─────────────────────────────────────────────────

    def set_waypoints(self, wps: list[tuple[float, float]], start_idx=0):
        self.waypoints = wps
        self.wp_idx = start_idx % max(1, len(wps))

    def update(self, dt: float, stage, shelf_map: ShelfMap,
               all_forklifts: list[Forklift]):
        """Advance one physics step."""
        if self.state == STATE_IDLE:
            self._tick_idle(dt)
            return
        if self.state == STATE_LOADING:
            self._tick_loading(dt)
            return
        if self.state == STATE_WAITING:
            self._tick_waiting(dt, all_forklifts)
            return
        self._tick_drive(dt, stage, shelf_map, all_forklifts)

    # ── IDLE state ───────────────────────────────────────────────────────

    def _tick_idle(self, dt):
        self.state_timer -= dt
        if self.state_timer <= 0:
            self.state = STATE_DRIVE
            self._advance_waypoint()

    # ── LOADING state ────────────────────────────────────────────────────

    def _tick_loading(self, dt):
        self.state_timer -= dt
        if self.state_timer <= 0:
            self.state = STATE_DRIVE
            self._advance_waypoint()

    # ── WAITING state (queued behind another forklift) ───────────────────

    def _tick_waiting(self, dt, all_forklifts):
        # Check if the path ahead is clear
        if not self._blocked_by_other(all_forklifts):
            self.state = STATE_DRIVE

    def _blocked_by_other(self, all_forklifts) -> bool:
        """True if another forklift is too close directly ahead."""
        look_dist = C.FORKLIFT_BODY_HALF * 4.0
        rad = math.radians(self.heading - C.FORKLIFT_HEADING_OFFSET)
        look_x = self.pos[0] + look_dist * math.cos(rad)
        look_y = self.pos[1] + look_dist * math.sin(rad)
        for other in all_forklifts:
            if other.id == self.id:
                continue
            d = math.hypot(look_x - other.pos[0], look_y - other.pos[1])
            if d < C.FORKLIFT_BODY_HALF * 3.0:
                return True
        return False

    # ── DRIVE state ──────────────────────────────────────────────────────

    def _tick_drive(self, dt, stage, shelf_map, all_forklifts):
        if not self.waypoints:
            return

        tx, ty = self.waypoints[self.wp_idx]

        # Skip waypoints inside shelves
        for _ in range(len(self.waypoints)):
            if not shelf_map.inside_shelf(tx, ty, margin=1.5):
                break
            self._advance_waypoint()
            tx, ty = self.waypoints[self.wp_idx]

        fx, fy = self.pos
        dx, dy = tx - fx, ty - fy
        dist = math.hypot(dx, dy)

        # Arrival
        if dist < C.FORKLIFT_ARRIVE_RADIUS:
            self.speed = 0.0
            self.state = STATE_IDLE
            self.state_timer = C.IDLE_DURATION
            ih.update_prim_pose(stage, self.prim_path, fx, fy, self.heading)
            return

        # Check if blocked
        if self._blocked_by_other(all_forklifts):
            self.speed = 0.0
            self.state = STATE_WAITING
            return

        # Lane constraint in shelf area
        if shelf_map.in_shelf_area(fy) and shelf_map.aisle_xs:
            ax = shelf_map.nearest_aisle(fx)
            if abs(fx - ax) > C.AISLE_SNAP:
                dx, dy = ax - fx, 0.0
            else:
                dx, dy = ax - fx, ty - fy

        # Steering
        desired = math.degrees(math.atan2(dy, dx)) + C.FORKLIFT_HEADING_OFFSET
        err = (desired - self.heading + 180) % 360 - 180
        steer_target = max(-C.FORKLIFT_MAX_STEER,
                           min(C.FORKLIFT_MAX_STEER, err * 0.8))
        steer_diff = steer_target - self.steer_angle
        self.steer_angle += max(-C.FORKLIFT_STEER_RATE * dt,
                                min(C.FORKLIFT_STEER_RATE * dt, steer_diff))

        # Speed
        steer_ratio = abs(self.steer_angle) / C.FORKLIFT_MAX_STEER
        max_spd = C.FORKLIFT_MAX_SPEED * (1.0 - 0.75 * steer_ratio)
        brake_dist = (self.speed ** 2) / (2.0 * C.FORKLIFT_BRAKE)
        if dist < brake_dist + 0.5:
            target_spd = max(C.FORKLIFT_MIN_SPEED,
                             math.sqrt(max(0, 2 * C.FORKLIFT_BRAKE * (dist - 0.3))))
        else:
            target_spd = max_spd

        if target_spd > self.speed:
            self.speed = min(self.speed + C.FORKLIFT_ACCEL * dt, target_spd)
        else:
            self.speed = max(self.speed - C.FORKLIFT_BRAKE * dt, target_spd)
        self.speed = max(0.0, self.speed)

        # Kinematic update
        steer_rad = math.radians(self.steer_angle)
        heading_rate = self.speed * math.tan(steer_rad) / C.FORKLIFT_WHEELBASE
        self.heading += math.degrees(heading_rate) * dt

        move_rad = math.radians(self.heading - C.FORKLIFT_HEADING_OFFSET)
        nx = fx + self.speed * dt * math.cos(move_rad)
        ny = fy + self.speed * dt * math.sin(move_rad)

        # Look-ahead shelf rejection
        if shelf_map.inside_shelf(nx, ny, margin=C.FORKLIFT_BODY_HALF):
            self._advance_waypoint()
            return

        # Wall clamp
        nx = max(C.NAV_X_MIN, min(C.NAV_X_MAX, nx))
        ny = max(C.NAV_Y_MIN, min(C.NAV_Y_MAX, ny))

        # Shelf push-out
        for rx0, rx1, ry0, ry1 in shelf_map.rects:
            ex0 = rx0 - C.FORKLIFT_BODY_HALF
            ex1 = rx1 + C.FORKLIFT_BODY_HALF
            ey0 = ry0 - C.FORKLIFT_BODY_HALF
            ey1 = ry1 + C.FORKLIFT_BODY_HALF
            if ex0 < nx < ex1 and ey0 < ny < ey1:
                dl, dr = nx - ex0, ex1 - nx
                db, dt_ = ny - ey0, ey1 - ny
                d_min = min(dl, dr, db, dt_)
                if   d_min == dl: nx = ex0
                elif d_min == dr: nx = ex1
                elif d_min == db: ny = ey0
                else:             ny = ey1
                self.speed *= 0.4
                self._advance_waypoint()
                break

        # Forklift-to-forklift separation
        sep = C.FORKLIFT_BODY_HALF * 2.2
        for other in all_forklifts:
            if other.id == self.id:
                continue
            d = math.hypot(nx - other.pos[0], ny - other.pos[1])
            if 0.001 < d < sep:
                push = sep - d
                nx += (nx - other.pos[0]) / d * push
                ny += (ny - other.pos[1]) / d * push
                nx = max(C.NAV_X_MIN, min(C.NAV_X_MAX, nx))
                ny = max(C.NAV_Y_MIN, min(C.NAV_Y_MAX, ny))
                self.speed *= 0.5

        self.pos = [nx, ny]
        ih.update_prim_pose(stage, self.prim_path, nx, ny, self.heading)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _advance_waypoint(self):
        if not self.waypoints:
            return
        self.wp_idx = (self.wp_idx + 1) % len(self.waypoints)

    def enter_loading(self):
        """Transition to LOADING state (called by scenario logic)."""
        self.state = STATE_LOADING
        self.state_timer = C.LOADING_DURATION
        self.speed = 0.0
