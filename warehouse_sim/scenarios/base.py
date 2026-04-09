"""
Base scenario class. All presets inherit from this.
"""

from __future__ import annotations
import random

from .. import config as C
from .. import isaac_helpers as ih
from ..shelves import ShelfMap
from ..areas import AreaManager
from ..forklift import Forklift
from .. import waypoints as wp


class Scenario:
    """Override setup_forklifts() and on_step() in subclasses."""

    name = "base"
    num_forklifts = 3

    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.stage = None
        self.assets_root = None
        self.shelf_map = ShelfMap()
        self.area_mgr = AreaManager()
        self.forklifts: list[Forklift] = []
        self.sim_time = 0.0
        self._telemetry_timer = 0.0

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def build(self):
        """Set up the full scene. Call once from main.py."""
        print(f"[{self.name}] Getting stage...")
        self.stage = ih.get_stage()
        await ih.next_update()

        print(f"[{self.name}] Resolving assets root...")
        self.assets_root = ih.get_assets_root()
        await ih.next_update()

        print(f"[{self.name}] Clearing /World...")
        ih.clear_world(self.stage)
        await ih.next_update()

        print(f"[{self.name}] Loading warehouse USD...")
        ih.spawn_asset(self.stage, "/World/Warehouse",
                       self.assets_root + C.WAREHOUSE_USD, 0, 0, 0)
        await ih.next_update()

        ih.create_physics_scene(self.stage)

        self._spawn_loading_doors()
        await ih.next_update()

        self._spawn_loading_markings()
        self._spawn_staging_markings()
        await ih.next_update()

        self._spawn_staging_props()
        await ih.next_update()

        for name, (x0, x1, y0, y1) in C.ZONES.items():
            cap = C.LOADING_AREA_CAPACITY  if name == "LoadingZone"  else \
                  C.STAGING_AREA_CAPACITY  if name == "StagingArea"  else None
            self.area_mgr.add(name, x0, x1, y0, y1, capacity=cap)

        self.setup_forklifts()

        print(f"[{self.name}] Scene built: {len(self.forklifts)} forklifts, "
              f"{len(self.area_mgr.areas)} areas.")

    def start(self):
        """Subscribe to physics and play."""
        self._sub = ih.subscribe_physics_step(self._on_physics_step)
        ih.play_timeline()
        print(f"[{self.name}] Simulation started.")

    # ── Override points ──────────────────────────────────────────────────

    def setup_forklifts(self):
        """Spawn forklifts and assign initial waypoints. Override in presets."""
        for i in range(self.num_forklifts):
            sx = C.NAV_X_MIN + 3.0 + i * 7.0
            sy = C.NAV_Y_MIN + 3.0
            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           sx, sy, 0.0, 90.0)
            fl = Forklift(i, path, sx, sy)
            self.forklifts.append(fl)

    def on_step(self, dt: float):
        """Per-frame scenario logic hook. Override for custom behaviour."""
        pass

    # ── Physics callback ─────────────────────────────────────────────────

    def _on_physics_step(self, dt):
        # Lazy shelf init
        if not self.shelf_map.ready:
            self.shelf_map.init(self.stage)
            self._assign_initial_waypoints()

        self.sim_time += dt

        # Move forklifts
        for fl in self.forklifts:
            fl.update(dt, self.stage, self.shelf_map, self.forklifts)

        # Zone occupancy
        for fl in self.forklifts:
            self.area_mgr.update(fl.id, fl.pos[0], fl.pos[1], self.sim_time)

        # Scenario-specific logic
        self.on_step(dt)

        # Telemetry
        self._telemetry_timer += dt
        if self._telemetry_timer >= 10.0:
            self._telemetry_timer = 0.0
            self._print_status()

    def _assign_initial_waypoints(self):
        """Default: random patrol. Override in subclasses for scenario routes."""
        for fl in self.forklifts:
            if not fl.waypoints:
                fl.set_waypoints(
                    wp.gen_patrol(self.shelf_map, self.rng),
                    start_idx=fl.id * 2
                )

    # ── Telemetry ────────────────────────────────────────────────────────

    def _print_status(self):
        print(f"[{self.name}] t={self.sim_time:.1f}s")
        for fl in self.forklifts:
            a = self.area_mgr.area_of(fl.pos[0], fl.pos[1])
            zname = a.name if a else "open"
            print(f"  FL{fl.id}: ({fl.pos[0]:6.1f},{fl.pos[1]:6.1f}) "
                  f"spd={fl.speed:.1f} state={fl.state} zone={zname}")
        self.area_mgr.print_status(self.sim_time)

    # ── Scene construction helpers ───────────────────────────────────────

    def _spawn_loading_doors(self):
        """3 loading dock gates on the south wall."""
        for i, offset in enumerate(C.GATE_OFFSETS):
            ih.spawn_gate(self.stage, i, C.WAREHOUSE_CX + offset, C)
        print(f"[{self.name}] 3 loading dock gates spawned.")

    def _spawn_loading_markings(self):
        """Zebra tape around each loading zone in front of the doors."""
        for i, offset in enumerate(C.GATE_OFFSETS):
            door_cx = C.WAREHOUSE_CX + offset
            load_cy = C.WALL_Y_MIN + C.LOAD_D / 2.0
            ih.spawn_zebra_rect(self.stage, f"/World/LoadingAreas/zone_{i}",
                                door_cx, load_cy, C.LOAD_W, C.LOAD_D, C)

    def _spawn_staging_markings(self):
        """Zebra tape around each staging zone (between loading and shelves)."""
        for i, offset in enumerate(C.GATE_OFFSETS):
            ih.spawn_zebra_rect(self.stage, f"/World/StagingAreas/zone_{i}",
                                C.WAREHOUSE_CX + offset,
                                C.STAGING_CENTER_Y,
                                C.STAGING_W, C.STAGING_D, C)

    def _spawn_staging_props(self):
        """Pallets + cardboard box stacks in the staging areas."""
        rng = random.Random(7)  # fixed seed for deterministic layout
        for zi, offset in enumerate(C.GATE_OFFSETS):
            zone_cx = C.WAREHOUSE_CX + offset
            hw = C.STAGING_W / 2 - 1.2
            hd = C.STAGING_D / 2 - 1.0
            n_stacks = rng.randint(3, 6)
            for pi in range(n_stacks):
                px = zone_cx + rng.uniform(-hw, hw)
                py = C.STAGING_CENTER_Y + rng.uniform(-hd, hd)
                yaw = rng.choice([0.0, 90.0, 180.0, -90.0])
                base = f"/World/StagingProps/zone_{zi}_stack_{pi}"

                # Pallet on the floor
                ih.spawn_asset(self.stage, f"{base}_pallet",
                               self.assets_root + C.PALLET_USD,
                               px, py, 0.0, yaw)
                ih.apply_static_collision(self.stage, f"{base}_pallet")

                # 1-3 cardboard boxes on top
                z = C.PALLET_H
                for bi in range(rng.randint(1, 3)):
                    box_usd = rng.choice(C.BOX_USDS)
                    ih.spawn_asset(self.stage, f"{base}_box_{bi}",
                                   self.assets_root + box_usd,
                                   px, py, z, yaw)
                    ih.apply_static_collision(self.stage, f"{base}_box_{bi}")
                    z += 0.55
        print(f"[{self.name}] Staging props spawned.")
