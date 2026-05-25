"""
Showcase scenario — LinkedIn demo.

Designed for visual impact:
  - Gates 0 (left) and 2 (right) open immediately with crates visible at dock.
    Gate 1 (middle) stays closed — active vs inactive contrast is instant.
  - FL0 and FL1 start pre-loaded (pallets on forks) and head straight to dock.
    FL2 and FL3 start unloaded and head to shelves, so all four stages of the
    cycle are visible simultaneously from the first second.
  - 4 visible staging scenery pallets fill the staging zone from the start.
  - 18 s loading duration keeps loaded forklifts at dock long enough to be
    clearly visible; staging queue builds naturally.
  - 2 IRA pedestrians patrol opposite halves of the main floor, creating
    natural near-miss interactions with the forklifts.
  - Per-step telemetry prints loaded/unloaded counts and queue depth every 10 s.
"""

from __future__ import annotations

from .base import Scenario
from .. import config as C
from .. import isaac_helpers as ih
from ..models.forklift import Forklift
from ..models.pallet import Pallet, LOC_SHELVES, LOC_FORKLIFT

_STAGGER_SECS  = 8.0    # seconds between each forklift's first move
_LOG_INTERVAL  = 10.0   # seconds between showcase status prints

# Forklifts that start pre-loaded (index into self.forklifts)
_PRELOADED_FL_INDICES = (0, 1)


class ShowcaseScenario(Scenario):
    name = "showcase"
    num_forklifts = 4

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = 18.0   # long dock time → loaded forklifts visible
        self.pickup_duration  = 5.0    # slightly longer pickup for visual clarity
        self._log_timer: float = 0.0

    # ── Scene setup ──────────────────────────────────────────────────────────

    def setup_forklifts(self):
        """Spawn 4 forklifts with staggered departure timers, pallets, and scenery."""
        for i in range(self.num_forklifts):
            sx = C.NAV_X_MIN + 3.0 + i * 7.0
            sy = C.NAV_Y_MIN + 3.0
            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           sx, sy, 0.0, 90.0)
            fl = Forklift(i, path, sx, sy)
            fl.state_timer = i * _STAGGER_SECS   # FL0 moves first, others follow
            self.forklifts.append(fl)

        # Pallets and scenery are spawned here (not in _assign_initial_waypoints)
        # so they exist after build() — before the first physics step.
        self._spawn_tracked_pallets()
        self._spawn_staging_scenery()

        # Pre-load FL0 and FL1 here (during build, not in the physics callback)
        # so the carried-pallet prim USD reference is added before simulation starts.
        # Wiring to rule_engine._fl_pallet is deferred to _assign_initial_waypoints
        # (after RuleEngine is constructed).
        for fl_idx in _PRELOADED_FL_INDICES:
            fl = self.forklifts[fl_idx]
            fl.set_load(self.stage, C.LOAD_LOADED, assets_root=self.assets_root)
        print(f"[{self.name}] FL{list(_PRELOADED_FL_INDICES)} carried-pallet prims spawned")

    def _assign_initial_waypoints(self):
        """Gates 0+2 open, gate 1 closed. FL0 and FL1 start pre-loaded."""
        self.doors[0].open(self.stage)
        self.doors[1].close(self.stage)
        self.doors[2].open(self.stage)
        print(f"[{self.name}] gates 0+2 open, gate 1 closed")

        # Carried-pallet prims were already spawned in setup_forklifts (build phase).
        # Here we only wire each pallet object into the rule engine so it knows
        # the forklift is already loaded and won't re-assign a pallet.
        for fl_idx, pal_idx in zip(_PRELOADED_FL_INDICES,
                                   range(len(_PRELOADED_FL_INDICES))):
            fl = self.forklifts[fl_idx]
            pallet = self.pallets[pal_idx]
            pallet.assigned_forklift_id = fl.id
            pallet.set_location(LOC_FORKLIFT)
            if self.rule_engine is not None:
                self.rule_engine._fl_pallet[fl.id] = pallet
        print(f"[{self.name}] FL{list(_PRELOADED_FL_INDICES)} pre-loaded")

    def _spawn_tracked_pallets(self):
        """Spawn one Pallet per forklift, hidden in the shelf area.

        Appending to self.pallets (the same list held by RuleEngine) means
        _find_free_pallet() will return these as forklifts complete pickups,
        triggering the visual fork-mounted pallet prim on each forklift.
        """
        shelf_y = C.STAGING_Y_FAR + 4.0   # behind staging, inside shelf area
        spacing = 6.0
        base_x  = C.WAREHOUSE_CX - spacing * (self.num_forklifts - 1) / 2.0
        for i in range(self.num_forklifts):
            path = f"/World/Pallets/pallet_{i}"
            p = Pallet(i, path, location=LOC_SHELVES)
            p.spawn(self.stage, self.assets_root,
                    base_x + i * spacing, shelf_y)
            p.hide(self.stage)
            self.pallets.append(p)
        print(f"[{self.name}] {self.num_forklifts} tracked pallets spawned (hidden)")

    def _spawn_staging_scenery(self):
        """Spawn visible static pallet props as staging area visual dressing.

        Positions are chosen to sit between and to the sides of the three gate
        columns so forklifts are not obstructed.
        """
        props = [
            (C.WAREHOUSE_CX - 10.0, C.STAGING_CENTER_Y + 1.0),
            (C.WAREHOUSE_CX -  3.5, C.STAGING_CENTER_Y + 2.5),
            (C.WAREHOUSE_CX +  3.5, C.STAGING_CENTER_Y - 2.5),
            (C.WAREHOUSE_CX + 10.0, C.STAGING_CENTER_Y + 1.0),
        ]
        for j, (sx, sy) in enumerate(props):
            ih.spawn_asset(self.stage, f"/World/StagingProps/prop_{j}",
                           C.PALLET_USD, sx, sy, 0.0, 0.0,
                           scale=C.PALLET_SCALE)
        print(f"[{self.name}] {len(props)} staging scenery props spawned")

    def setup_pedestrians(self):
        """Two workers patrolling opposite halves of the main open floor.

        PED 0 covers the east half (right of centre), PED 1 covers the west
        half (left of centre).  Both routes run between the top of the loading
        zone and the north edge of the staging area — the busiest corridor for
        forklift traffic — for maximum visual impact.
        """
        y_near = C.WALL_Y_MIN + C.LOAD_D + 1.5   # just north of loading zone
        y_far  = C.STAGING_Y_FAR + 1.0            # just north of staging area

        # East half: from warehouse centre to east nav boundary
        x_mid  = C.WAREHOUSE_CX + 1.0
        x_east = C.NAV_X_MAX - 2.0
        self.spawn_pedestrian(
            waypoints=[
                (x_mid,  y_near),
                (x_east, y_near),
                (x_east, y_far),
                (x_mid,  y_far),
            ],
            loop=True,
        )

        # West half: from west nav boundary to warehouse centre
        x_west = C.NAV_X_MIN + 2.0
        x_mid_w = C.WAREHOUSE_CX - 1.0
        self.spawn_pedestrian(
            waypoints=[
                (x_west,  y_near),
                (x_mid_w, y_near),
                (x_mid_w, y_far),
                (x_west,  y_far),
            ],
            loop=True,
        )

    # ── Per-frame logic ───────────────────────────────────────────────────────

    def on_step(self, dt: float):
        self._tick_status_log(dt)

    def _tick_status_log(self, dt: float):
        """Print a concise showcase status line every _LOG_INTERVAL seconds."""
        self._log_timer += dt
        if self._log_timer < _LOG_INTERVAL:
            return
        self._log_timer = 0.0

        loaded   = sum(1 for fl in self.forklifts if fl.load == C.LOAD_LOADED)
        unloaded = len(self.forklifts) - loaded

        staging  = self.area_mgr.get("StagingArea")
        q_depth  = staging.occupancy if staging else 0

        loading  = self.area_mgr.get("LoadingZone")
        at_dock  = loading.occupancy if loading else 0

        print(
            f"[{self.name}] t={self.sim_time:.0f}s | "
            f"loaded={loaded} unloaded={unloaded} | "
            f"at_dock={at_dock} staging_queue={q_depth}"
        )
