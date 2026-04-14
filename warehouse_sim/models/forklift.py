"""
Forklift: 8-state FSM + kinematic bicycle model + load property.

  - 8-state FSM ladder driven by rule_engine (see logic/forklift_fsm.py)
  - `load` property (LOAD_LOADED / LOAD_UNLOADED) independent of state
  - Fork prim + pallet prim visual wiring driven by load property
  - `assigned_task`, `current_area_slot` for rule engine
"""

from __future__ import annotations
import math

from .. import config as C
from .. import isaac_helpers as ih
from ..shelves import ShelfMap


class Forklift:
    """One forklift: kinematic state + 8-state FSM + load property."""

    def __init__(self, fl_id: int, prim_path: str, x: float, y: float,
                 heading: float = 90.0):
        self.id = fl_id
        self.prim_path = prim_path
        self.pos = [x, y]
        self.heading = heading
        self.speed = 0.0
        self.steer_angle = 0.0

        # FSM — default to IDLE on spawn
        self.state = C.STATE_IDLE
        self.state_timer = 0.0

        # Load property — independent of state
        self.load = C.LOAD_UNLOADED

        # Rule-engine handles (set by Task #6 logic)
        self.assigned_task = None
        self.current_area_slot = None

        # Waypoints
        self.waypoints: list[tuple[float, float]] = []
        self.wp_idx = 0

        # Stuck-recovery timers
        self._stuck_secs: float = 0.0     # accumulates while blocked by another forklift
        self._recovery_secs: float = 0.0  # counts down during the reverse phase

        # Pallet prim path that rides on the fork when loaded
        self.pallet_prim_path = f"{prim_path}/carried_pallet"
        self._pallet_prim_spawned = False

    # ── Public interface ─────────────────────────────────────────────────────

    @property
    def has_pallet(self) -> bool:
        return self.load == C.LOAD_LOADED

    def set_waypoints(self, wps: list[tuple[float, float]], start_idx: int = 0):
        self.waypoints = wps
        self.wp_idx = start_idx % max(1, len(wps))

    def set_load(self, stage, load_state: str, assets_root: str | None = None) -> None:
        """Change the load property and update visuals.

        LOAD_LOADED   → spawn/show the carried pallet prim on the fork
        LOAD_UNLOADED → hide the carried pallet prim
        """
        assert load_state in (C.LOAD_LOADED, C.LOAD_UNLOADED)
        self.load = load_state

        if load_state == C.LOAD_LOADED:
            if not self._pallet_prim_spawned:
                if assets_root is None:
                    raise RuntimeError(
                        "set_load(LOADED) needs assets_root on first call "
                        "to spawn the carried-pallet prim."
                    )
                # Spawn pallet prim under the forklift, raised to fork travel height
                ih.spawn_asset(stage, self.pallet_prim_path,
                               C.PALLET_USD,
                               self.pos[0], self.pos[1],
                               C.FORK_TRAVEL_HEIGHT, self.heading,
                               scale=C.PALLET_SCALE)
                self._pallet_prim_spawned = True
            else:
                ih.make_visible(stage, self.pallet_prim_path)
        else:  # UNLOADED
            if self._pallet_prim_spawned:
                ih.make_invisible(stage, self.pallet_prim_path)

    # ── FSM ──────────────────────────────────────────────────────────────────

    def update(self, dt: float, stage, shelf_map: ShelfMap,
               all_forklifts: list["Forklift"]):
        """Advance one physics step.

        Note: state *transitions* will be driven by the rule engine (Task #6).
        This update() only executes movement / in-state behaviour.
        """
        if self.state == C.STATE_IDLE:
            # Count down any initial hold-off timer (used for staggered starts)
            if self.state_timer > 0.0:
                self.state_timer = max(0.0, self.state_timer - dt)
            # Pin prim so physics drift can't move it while we wait
            ih.update_prim_pose(stage, self.prim_path,
                                self.pos[0], self.pos[1], self.heading)
            return
        if self.state in (C.STATE_WAIT_IN_STAGING,
                          C.STATE_WAIT_AT_DOCK_QUEUE):
            self.speed = 0.0
            ih.update_prim_pose(stage, self.prim_path,
                                self.pos[0], self.pos[1], self.heading)
            return
        if self.state == C.STATE_PICKUP_AT_SHELVES:
            if self.waypoints:
                # Still traveling to pickup location
                self._tick_drive(dt, stage, shelf_map, all_forklifts)
            else:
                # At pickup location — count down timer; pin the prim
                self.state_timer -= dt
                ih.update_prim_pose(stage, self.prim_path,
                                    self.pos[0], self.pos[1], self.heading)
            return
        if self.state == C.STATE_LOADING:
            # Parked at dock — count down timer; pin the prim
            self.state_timer -= dt
            ih.update_prim_pose(stage, self.prim_path,
                                self.pos[0], self.pos[1], self.heading)
            return
        # Moving states: MOVE_TO_STAGING, MOVE_TO_LOADING, RETURNING
        self._tick_drive(dt, stage, shelf_map, all_forklifts)

    # ── Drive state (kinematics copied verbatim from original forklift.py) ──

    def _blocked_by_other(self, all_forklifts) -> bool:
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

    def _tick_drive(self, dt, stage, shelf_map, all_forklifts):
        if not self.waypoints:
            return

        # ── Stuck-recovery: reverse briefly to break look-ahead deadlocks ──────
        if self._recovery_secs > 0.0:
            self._recovery_secs -= dt
            # Move backward: opposite of the current heading direction
            rev_rad = math.radians(self.heading - C.FORKLIFT_HEADING_OFFSET + 180)
            nx = self.pos[0] + C.FORKLIFT_MIN_SPEED * dt * math.cos(rev_rad)
            ny = self.pos[1] + C.FORKLIFT_MIN_SPEED * dt * math.sin(rev_rad)
            nx = max(C.NAV_X_MIN, min(C.NAV_X_MAX, nx))
            ny = max(C.NAV_Y_MIN, min(C.NAV_Y_MAX, ny))
            self.pos = [nx, ny]
            self.speed = C.FORKLIFT_MIN_SPEED
            ih.update_prim_pose(stage, self.prim_path, nx, ny, self.heading)
            self._sync_carried_pallet(stage)
            # Reset stuck counter when reversal ends so it can't immediately re-arm
            if self._recovery_secs <= 0.0:
                self._stuck_secs = 0.0
            return
        # ─────────────────────────────────────────────────────────────────────────

        tx, ty = self.waypoints[self.wp_idx]

        for _ in range(len(self.waypoints)):
            if not shelf_map.inside_shelf(tx, ty, margin=0.0):
                break
            self._advance_waypoint()
            tx, ty = self.waypoints[self.wp_idx]

        fx, fy = self.pos
        dx, dy = tx - fx, ty - fy
        dist = math.hypot(dx, dy)

        if dist < C.FORKLIFT_ARRIVE_RADIUS:
            old_idx = self.wp_idx
            self._advance_waypoint()
            if self.wp_idx <= old_idx:
                # Wrapped — all waypoints visited; stop and signal arrival
                self.speed = 0.0
                self.waypoints = []
                ih.update_prim_pose(stage, self.prim_path, fx, fy, self.heading)
                self._sync_carried_pallet(stage)
            # else: intermediate waypoint reached — drive on next frame
            return

        if self._blocked_by_other(all_forklifts):
            self._stuck_secs += dt
            self.speed = 0.0
            if self._stuck_secs >= 2.0:   # raised from 0.8 — avoids hair-trigger on passing traffic
                self._stuck_secs = 0.0
                self._recovery_secs = 1.2
            return
        self._stuck_secs = 0.0

        # Snap to the aisle that serves the TARGET (tx), not the nearest aisle
        # to the forklift's current X — prevents wrong-aisle commitment.
        if shelf_map.in_shelf_area(fy) and shelf_map.aisle_xs:
            ax = shelf_map.nearest_aisle(tx)
            if abs(fx - ax) > C.AISLE_SNAP:
                dx, dy = ax - fx, 0.0
            else:
                dx, dy = ax - fx, ty - fy

        desired = math.degrees(math.atan2(dy, dx)) + C.FORKLIFT_HEADING_OFFSET
        err = (desired - self.heading + 180) % 360 - 180
        steer_target = max(-C.FORKLIFT_MAX_STEER,
                           min(C.FORKLIFT_MAX_STEER, err * 0.8))
        steer_diff = steer_target - self.steer_angle
        self.steer_angle += max(-C.FORKLIFT_STEER_RATE * dt,
                                min(C.FORKLIFT_STEER_RATE * dt, steer_diff))

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

        steer_rad = math.radians(self.steer_angle)
        heading_rate = self.speed * math.tan(steer_rad) / C.FORKLIFT_WHEELBASE
        self.heading += math.degrees(heading_rate) * dt

        move_rad = math.radians(self.heading - C.FORKLIFT_HEADING_OFFSET)
        nx = fx + self.speed * dt * math.cos(move_rad)
        ny = fy + self.speed * dt * math.sin(move_rad)

        if shelf_map.inside_shelf(nx, ny, margin=0.0):
            self._advance_waypoint()
            return

        nx = max(C.NAV_X_MIN, min(C.NAV_X_MAX, nx))
        ny = max(C.NAV_Y_MIN, min(C.NAV_Y_MAX, ny))

        for rx0, rx1, ry0, ry1 in shelf_map.rects:
            if rx0 < nx < rx1 and ry0 < ny < ry1:
                dl, dr = nx - rx0, rx1 - nx
                db, dt_ = ny - ry0, ry1 - ny
                d_min = min(dl, dr, db, dt_)
                if   d_min == dl: nx = rx0
                elif d_min == dr: nx = rx1
                elif d_min == db: ny = ry0
                else:             ny = ry1
                self.speed *= 0.4
                self._advance_waypoint()
                break

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

        # Hard-clamp to aisle corridor — prevents crossing into shelf blocks
        if shelf_map.in_shelf_area(ny) and shelf_map.aisle_xs:
            ax = shelf_map.nearest_aisle(nx)
            nx = ax + max(-C.AISLE_HALF_WIDTH, min(C.AISLE_HALF_WIDTH, nx - ax))

        self.pos = [nx, ny]
        ih.update_prim_pose(stage, self.prim_path, nx, ny, self.heading)
        self._sync_carried_pallet(stage)

    # ── Carried-pallet tracking ──────────────────────────────────────────────

    def _sync_carried_pallet(self, stage):
        """Keep the carried-pallet prim aligned with the forklift when loaded."""
        if self._pallet_prim_spawned and self.load == C.LOAD_LOADED:
            ih.update_prim_pose(stage, self.pallet_prim_path,
                                self.pos[0], self.pos[1], self.heading)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _advance_waypoint(self):
        if not self.waypoints:
            return
        self.wp_idx = (self.wp_idx + 1) % len(self.waypoints)

    def __repr__(self) -> str:
        return (f"Forklift(id={self.id}, state={self.state}, "
                f"load={self.load}, pos=({self.pos[0]:.1f},{self.pos[1]:.1f}))")
