"""
ConfigScenario: a scenario driven entirely by a dict entry in config.CONFIG_SCENARIOS.

No Python subclass needed — define your scenario as a dict and set SCENARIO
to the dict key in main.py.

Supported dict keys
-------------------
  num_forklifts    (int)        how many forklifts to spawn
  loading_duration (float)      seconds at dock per cycle
  pickup_duration  (float)      seconds at shelf pickup per cycle
  spawn_strategy   (str)        "grid" | "near_aisle"
  near_aisle_x     (float|None) X for near_aisle; None = auto from ShelfMap
  doors            (dict):
      open_all_at_start (bool)
      events: [{"at_sim_time": t,
                "action": "open_all"|"close_all"|"open_gate_N"|"close_gate_N"}, ...]
  idle_forklift_ids (list[int]) forklifts that remain stationary (no tasks)
  thresholds        (dict)      per-scenario overrides: IDLE_WARN_SECS, NEAR_MISS_DIST
"""

from __future__ import annotations
import math

from .base import Scenario
from .. import config as C
from .. import isaac_helpers as ih
from ..models.forklift import Forklift


class ConfigScenario(Scenario):
    """A scenario defined entirely by a configuration dict."""

    def __init__(self, cfg: dict, seed: int = 42):
        super().__init__(seed)

        self.num_forklifts    = cfg.get("num_forklifts", 3)
        self.loading_duration = cfg.get("loading_duration", C.LOADING_DURATION)
        self.pickup_duration  = cfg.get("pickup_duration", C.PICKUP_DURATION)

        self._spawn_strategy  = cfg.get("spawn_strategy", "grid")
        self._near_aisle_x    = cfg.get("near_aisle_x", None)
        self._pinned_idle_ids = set(cfg.get("idle_forklift_ids", []))
        self._thresholds      = dict(cfg.get("thresholds", {}))

        door_cfg = cfg.get("doors", {})
        self._open_all_at_start = door_cfg.get("open_all_at_start", True)
        raw_events = door_cfg.get("events", [])
        self._door_events = sorted(raw_events, key=lambda e: e["at_sim_time"])
        self._evt_cursor  = 0

    # ── Override points ──────────────────────────────────────────────────────

    def setup_forklifts(self):
        """Spawn forklifts using the configured strategy."""
        if self._spawn_strategy == "near_aisle" and self._near_aisle_x is not None:
            cluster_x = self._near_aisle_x
            spawn_y   = C.NAV_Y_MIN + 3.0
            for i in range(self.num_forklifts):
                sx = cluster_x + (i - self.num_forklifts // 2) * 1.2
                path = f"/World/Forklifts/forklift_{i}"
                ih.spawn_asset(self.stage, path,
                               self.assets_root + C.FORKLIFT_USD,
                               sx, spawn_y, 0.0, 90.0)
                self.forklifts.append(Forklift(i, path, sx, spawn_y))
        else:
            # Default grid layout (same as base Scenario.setup_forklifts)
            super().setup_forklifts()

    def _assign_initial_waypoints(self):
        """Open/close doors per config; pin idle forklifts; resolve near-aisle."""
        # Doors
        if self._open_all_at_start:
            self.open_all_doors()

        # Lazy near-aisle resolution (ShelfMap is ready now)
        if self._spawn_strategy == "near_aisle" and self._near_aisle_x is None:
            if self.shelf_map.aisle_xs:
                mid = len(self.shelf_map.aisle_xs) // 2
                target_x = self.shelf_map.aisle_xs[mid]
                for fl in self.forklifts:
                    new_x = target_x + (fl.id - self.num_forklifts // 2) * 1.2
                    if self.stage is not None:
                        ih.update_prim_pose(self.stage, fl.prim_path,
                                            new_x, fl.pos[1], fl.heading)
                    fl.pos = [new_x, fl.pos[1]]

        # Pin idle forklifts — take them out of normal FSM cycling
        for fl in self.forklifts:
            if fl.id in self._pinned_idle_ids:
                fl.state = C.STATE_IDLE
                fl.set_waypoints([])

    def on_step(self, dt: float):
        """Re-enforce idle pins each frame and fire timed door events."""
        # Re-enforce pinned forklifts — the rule engine cannot route them out
        for fl in self.forklifts:
            if fl.id in self._pinned_idle_ids:
                fl.state = C.STATE_IDLE
                fl.speed = 0.0

        # Sweep-line door events (O(1) per frame once cursor reaches the end)
        while (self._evt_cursor < len(self._door_events) and
               self.sim_time >= self._door_events[self._evt_cursor]["at_sim_time"]):
            self._fire_door_event(self._door_events[self._evt_cursor])
            self._evt_cursor += 1

    # ── Threshold-aware event checks ─────────────────────────────────────────

    def _check_idle(self, dt: float) -> None:
        """Like base, but skips pinned forklifts and respects threshold overrides."""
        idle_warn = self._thresholds.get("IDLE_WARN_SECS", C.IDLE_WARN_SECS)
        for fl in self.forklifts:
            if fl.id in self._pinned_idle_ids:
                self._idle_secs[fl.id] = 0.0  # suppress alert for intentionally idle
                continue
            if fl.state == C.STATE_IDLE:
                self._idle_secs[fl.id] = self._idle_secs.get(fl.id, 0.0) + dt
                if self._idle_secs[fl.id] >= idle_warn:
                    area = self.area_mgr.area_of(fl.pos[0], fl.pos[1])
                    self.evt_log.log_idle_alert(
                        self.sim_time, fl.id,
                        self._idle_secs[fl.id],
                        area.name if area else None,
                    )
                    self._idle_secs[fl.id] = 0.0
            else:
                self._idle_secs[fl.id] = 0.0

    def _check_proximity(self) -> None:
        """Like base, but respects NEAR_MISS_DIST threshold override."""
        near_miss_dist = self._thresholds.get("NEAR_MISS_DIST", C.NEAR_MISS_DIST)
        fls = self.forklifts
        cooldown = 5.0
        for i in range(len(fls)):
            for j in range(i + 1, len(fls)):
                a, b = fls[i], fls[j]
                dist = math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1])
                if dist > near_miss_dist:
                    continue
                if (a.speed < C.NEAR_MISS_SPEED_MIN and
                        b.speed < C.NEAR_MISS_SPEED_MIN):
                    continue
                key = (min(a.id, b.id), max(a.id, b.id))
                last = self._prox_cooldown.get(key, -999.0)
                if self.sim_time - last < cooldown:
                    continue
                self._prox_cooldown[key] = self.sim_time
                self.evt_log.log_proximity_alert(
                    self.sim_time, a.id, b.id, dist, a.speed, b.speed
                )

    # ── Door event dispatcher ─────────────────────────────────────────────────

    def _fire_door_event(self, evt: dict) -> None:
        action = evt["action"]
        t = self.sim_time
        if action == "open_all":
            self.open_all_doors()
            for i in range(len(self.doors)):
                self.evt_log.log_door_open(t, gate_idx=i)
        elif action == "close_all":
            self.close_all_doors()
            for i in range(len(self.doors)):
                self.evt_log.log_door_close(t, gate_idx=i)
        elif action.startswith("open_gate_"):
            try:
                idx = int(action[len("open_gate_"):])
            except ValueError:
                return
            if 0 <= idx < len(self.doors):
                self.doors[idx].open(self.stage)
                self.evt_log.log_door_open(t, gate_idx=idx)
        elif action.startswith("close_gate_"):
            try:
                idx = int(action[len("close_gate_"):])
            except ValueError:
                return
            if 0 <= idx < len(self.doors):
                self.doors[idx].close(self.stage)
                self.evt_log.log_door_close(t, gate_idx=idx)
