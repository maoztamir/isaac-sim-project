"""
Base scenario class. All presets inherit from this.

Physics-step order (per frame):
  1. Lazy ShelfMap.init()
  2. sim_time += dt
  3. rule_engine.tick(dt)   — FSM transitions before movement
  4. Forklift movement
  5. Pedestrian movement
  6. Area occupancy update
  7. ZoneMonitor tick
  8. MetricsWriter tick
  9. Event checks (proximity, idle, staging buildup, dock queue depth,
                    pedestrian near-miss)
 10. Scenario on_step(dt) hook
 11. Telemetry every 10 s
"""

from __future__ import annotations
import math
import random

from .. import config as C
from .. import isaac_helpers as ih
from ..shelves import ShelfMap
from ..areas import AreaManager
from ..models.forklift import Forklift
from ..models.loading_door import LoadingDoor
from ..models.pallet import Pallet
from ..models.pedestrian import Pedestrian
from ..logic.rule_engine import RuleEngine
from ..logic.queue_manager import QueueManager
from ..monitoring import ZoneMonitor, EventLogger, MetricsWriter
from ..monitoring.event_logger import (
    EVENT_PROXIMITY_ALERT, EVENT_IDLE_ALERT,
    EVENT_QUEUE_FORMED, EVENT_BUILDUP_THRESHOLD,
    EVENT_PEDESTRIAN_NEAR_MISS,
)
from .. import waypoints as wp


class Scenario:
    """Override setup_forklifts() and on_step() in subclasses."""

    name = "base"
    num_forklifts = 3

    # Set True in subclasses that have IRA pedestrians.  When True, build()
    # uses SimulationManager to open the warehouse as the ROOT stage (required
    # for navmesh baking to see the floor mesh), then continues building the
    # remaining scene elements on the live stage.
    _use_ira_loader: bool = False

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.stage = None
        self.assets_root = None
        self.shelf_map = ShelfMap()
        self.area_mgr = AreaManager()
        self.forklifts:   list[Forklift]   = []
        self.pedestrians: list[Pedestrian] = []

        # Object-state models (populated in build())
        self.doors:   list[LoadingDoor] = []
        self.pallets: list[Pallet]      = []

        # Logic layer (populated after setup_forklifts())
        self.queue_mgr:   QueueManager | None = None
        self.rule_engine: RuleEngine   | None = None

        # Monitoring layer (populated in build())
        self.evt_log:        EventLogger    | None = None
        self.zone_mon:       ZoneMonitor    | None = None
        self.metrics_writer: MetricsWriter  | None = None

        # Per-scenario timing (subclasses set this in __init__ before build())
        self.loading_duration: float = C.LOADING_DURATION
        self.pickup_duration:  float = C.PICKUP_DURATION

        # Gate layout — subclasses override before build() for non-standard layouts
        self.gate_offsets:      list  = list(C.GATE_OFFSETS)
        self.gate_door_numbers: list | None = None   # None → labels 1, 2, 3, …

        # Internal timers
        self.sim_time = 0.0
        self._telemetry_timer = 0.0

        # Per-forklift idle tracking: fl_id → cumulative seconds in STATE_IDLE
        self._idle_secs: dict[int, float] = {}
        # Proximity alert cool-down: (min_id, max_id) → sim_time of last alert
        self._prox_cooldown: dict[tuple[int, int], float] = {}
        # Pedestrian near-miss cool-down: (fl_id, ped_id) → sim_time of last alert
        self._ped_prox_cooldown: dict[tuple[int, int], float] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def build(self):
        """Set up the full scene. Call once from main.py."""
        print(f"[{self.name}] Getting stage...")
        self.stage = ih.get_stage()
        await ih.next_update()

        print(f"[{self.name}] Resolving assets root...")
        self.assets_root = ih.get_assets_root()
        await ih.next_update()

        if self._use_ira_loader:
            # IRA path: register pedestrians first so _open_ira_scene() knows
            # how many characters to spawn, then open via SimulationManager.
            self.setup_pedestrians()
            await self._open_ira_scene()
            self.stage = ih.get_stage()   # SimulationManager replaced the stage
        else:
            # Reference path: clear world and load warehouse as a reference prim.
            print(f"[{self.name}] Clearing /World...")
            ih.clear_world(self.stage)
            await ih.next_update()

            print(f"[{self.name}] Loading warehouse USD...")
            _assets_waiter = ih.wait_for_assets_loaded()
            ih.spawn_asset(self.stage, "/World/Warehouse",
                           self.assets_root + C.WAREHOUSE_USD, 0, 0, 0)
            await _assets_waiter

        ih.create_physics_scene(self.stage)

        self._spawn_cameras()

        # LoadingDoor objects must exist before _spawn_loading_doors() so that
        # method can wire crate_prim_path onto each door.
        self.doors = [LoadingDoor(i, is_open=False)
                      for i in range(len(self.gate_offsets))]

        self._spawn_loading_doors()
        await ih.next_update()

        self._spawn_loading_markings()
        self._spawn_staging_markings()
        await ih.next_update()

        # Areas — computed from this scenario's gate layout
        for name, (x0, x1, y0, y1) in C.compute_zones(self.gate_offsets).items():
            cap = C.LOADING_AREA_CAPACITY if name == "LoadingZone" else \
                  C.STAGING_AREA_CAPACITY if name == "StagingArea" else None
            self.area_mgr.add(name, x0, x1, y0, y1, capacity=cap)

        # Monitoring — instantiate before forklifts so subclasses can log in setup
        self.evt_log = EventLogger(print_events=False)
        self.zone_mon = ZoneMonitor(self.area_mgr)
        self.metrics_writer = MetricsWriter(
            self.zone_mon, self.evt_log,
            flush_interval=30.0,
            snapshot_interval=1.0,
        )

        # Forklifts (subclass override point)
        self.setup_forklifts()
        await ih.next_update()
        self._idle_secs = {fl.id: 0.0 for fl in self.forklifts}

        # Pedestrians — IRA path already spawned them; reference path spawns here.
        if not self._use_ira_loader:
            self.setup_pedestrians()
            if self.pedestrians:
                await self._setup_ira_pedestrians()

        # Logic — needs forklifts + doors populated
        self.queue_mgr = QueueManager(self.shelf_map)
        self.rule_engine = RuleEngine(
            forklifts=self.forklifts,
            doors=self.doors,
            pallets=self.pallets,
            area_mgr=self.area_mgr,
            queue_mgr=self.queue_mgr,
            shelf_map=self.shelf_map,
            stage=self.stage,
            assets_root=self.assets_root,
            loading_duration=self.loading_duration,
            pickup_duration=self.pickup_duration,
            gate_offsets=self.gate_offsets,
        )

        print(f"[{self.name}] Scene built: {len(self.forklifts)} forklifts, "
              f"{len(self.pedestrians)} pedestrians, "
              f"{len(self.area_mgr.areas)} areas, {len(self.doors)} doors.")

    def start(self):
        """Subscribe to physics and play."""
        self._sub = ih.subscribe_physics_step(self._on_physics_step)
        ih.play_timeline()
        print(f"[{self.name}] Simulation started.")

    # ── Override points ──────────────────────────────────────────────────────

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

    def setup_pedestrians(self):
        """Spawn pedestrians and set their waypoints.  Override in presets.

        Unlike forklifts, pedestrian waypoints are assigned here (not lazily
        on the first physics step) because they do not depend on ShelfMap.

        Call self.spawn_pedestrian() for each pedestrian needed.
        Default: no pedestrians.
        """
        pass

    def on_step(self, dt: float):
        """Per-frame scenario logic hook. Override for custom behaviour."""
        pass

    # ── Physics callback ─────────────────────────────────────────────────────

    def _on_physics_step(self, dt: float):
        try:
            self._on_physics_step_inner(dt)
        except Exception as _exc:
            import traceback
            traceback.print_exc()
            # If the USD stage has expired (Script Editor re-run without Stop),
            # unsubscribe immediately so errors don't spam every physics tick.
            if "Invalid stage" in str(_exc) or "invalid stage" in str(_exc).lower():
                print(f"[{self.name}] Stale physics callback — unsubscribing.")
                self._sub = None

    def _on_physics_step_inner(self, dt: float):
        # Refresh stage — the stored self.stage can go stale when the Script
        # Editor re-runs without stopping the previous simulation first.
        fresh = ih.get_stage()
        if fresh is not None:
            self.stage = fresh

        # 1. Lazy shelf init
        if not self.shelf_map.ready:
            print(f"[{self.name}] First physics step — initialising ShelfMap...")
            self.shelf_map.init(self.stage)
            self._assign_initial_waypoints()
            print(f"[{self.name}] ShelfMap ready, waypoints assigned.")

        # 2. Advance sim time
        self.sim_time += dt

        # 3. Rule engine — FSM transitions before movement
        if self.rule_engine is not None:
            self.rule_engine.tick(dt)

        # 4. Forklift movement
        for fl in self.forklifts:
            fl.update(dt, self.stage, self.shelf_map, self.forklifts)

        # 5. Pedestrian movement
        for ped in self.pedestrians:
            ped.update(dt, self.stage)

        # 6. Area occupancy
        for fl in self.forklifts:
            self.area_mgr.update(fl.id, fl.pos[0], fl.pos[1], self.sim_time)

        # 7. Zone monitor
        if self.zone_mon is not None:
            self.zone_mon.tick(self.forklifts, self.sim_time, dt)

        # 8. Metrics writer
        if self.metrics_writer is not None:
            self.metrics_writer.tick(self.sim_time, dt)

        # 9. Event checks
        self._check_events(dt)

        # 9. Scenario hook
        self.on_step(dt)

        # 10. Telemetry
        self._telemetry_timer += dt
        if self._telemetry_timer >= 10.0:
            self._telemetry_timer = 0.0
            self._print_status()

    def _assign_initial_waypoints(self):
        """Default: open all doors; FSM drives forklifts from STATE_IDLE automatically.
        Override in subclasses for scenario-specific door state or forced initial states."""
        self.open_all_doors()

    def open_all_doors(self) -> None:
        """Open all loading dock doors."""
        for door in self.doors:
            door.open(self.stage)

    def close_all_doors(self) -> None:
        """Close all loading dock doors."""
        for door in self.doors:
            door.close(self.stage)

    # ── Event checks ─────────────────────────────────────────────────────────

    def _check_events(self, dt: float) -> None:
        """Scan for proximity alerts, idle alerts, and area threshold crossings."""
        if self.evt_log is None:
            return

        self._check_proximity()
        self._check_idle(dt)
        self._check_area_thresholds()
        if self.pedestrians:
            self._check_pedestrian_proximity()

    def _check_proximity(self) -> None:
        """Log a proximity alert when two forklifts are within NEAR_MISS_DIST."""
        fls = self.forklifts
        cooldown = 5.0  # seconds between repeated alerts for the same pair
        for i in range(len(fls)):
            for j in range(i + 1, len(fls)):
                a, b = fls[i], fls[j]
                dist = math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1])
                if dist > C.NEAR_MISS_DIST:
                    continue
                # At least one must be moving
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

    def _check_idle(self, dt: float) -> None:
        """Log an idle alert when a forklift has been in STATE_IDLE too long."""
        for fl in self.forklifts:
            if fl.state == C.STATE_IDLE:
                self._idle_secs[fl.id] = self._idle_secs.get(fl.id, 0.0) + dt
                if self._idle_secs[fl.id] >= C.IDLE_WARN_SECS:
                    area = self.area_mgr.area_of(fl.pos[0], fl.pos[1])
                    self.evt_log.log_idle_alert(
                        self.sim_time, fl.id,
                        self._idle_secs[fl.id],
                        area.name if area else None,
                    )
                    # Reset so we don't spam — fires again after another IDLE_WARN_SECS
                    self._idle_secs[fl.id] = 0.0
            else:
                self._idle_secs[fl.id] = 0.0

    def _check_area_thresholds(self) -> None:
        """Log queue-formed and buildup events when areas hit capacity."""
        for area in self.area_mgr.areas.values():
            if area.capacity is None:
                continue
            occ = area.occupancy
            cap = area.capacity

            # Buildup: occupancy has reached or exceeded capacity
            if occ >= cap:
                self.evt_log.log_buildup_threshold(
                    self.sim_time, area.name, occ, cap
                )

            # Queue formed: use staging area occupancy as a proxy for dock queue depth
            if area.name == "StagingArea" and occ >= 2:
                self.evt_log.log_queue_formed(
                    self.sim_time, area.name,
                    depth=occ, threshold=2
                )

    # ── Telemetry ─────────────────────────────────────────────────────────────

    def _print_status(self):
        print(f"[{self.name}] t={self.sim_time:.1f}s")
        for fl in self.forklifts:
            a = self.area_mgr.area_of(fl.pos[0], fl.pos[1])
            aname = a.name if a else "open"
            print(f"  FL{fl.id}: ({fl.pos[0]:6.1f},{fl.pos[1]:6.1f}) "
                  f"spd={fl.speed:.1f} state={fl.state} area={aname}")
        self.area_mgr.print_status(self.sim_time)
        if self.zone_mon is not None:
            self.zone_mon.print_summary()
        for ped in self.pedestrians:
            print(f"  {ped}")
        if self.evt_log is not None:
            n = self.evt_log.count()
            if n:
                print(f"  [events] total={n}  "
                      f"proximity={self.evt_log.count(EVENT_PROXIMITY_ALERT)}  "
                      f"idle={self.evt_log.count(EVENT_IDLE_ALERT)}  "
                      f"queue={self.evt_log.count(EVENT_QUEUE_FORMED)}  "
                      f"buildup={self.evt_log.count(EVENT_BUILDUP_THRESHOLD)}  "
                      f"ped_near_miss={self.evt_log.count(EVENT_PEDESTRIAN_NEAR_MISS)}")

    # ── Pedestrian helpers ────────────────────────────────────────────────────

    def spawn_pedestrian(self, waypoints: list[tuple[float, float]],
                         loop: bool = True) -> Pedestrian:
        """Register one IRA-animated pedestrian with a waypoint patrol route.

        Characters are not spawned here — actual USD loading and navmesh
        setup happens in _setup_ira_pedestrians(), called from build().
        """
        ped_id = len(self.pedestrians)
        if ped_id == 0:
            char_name = "Character"
        elif ped_id < 10:
            char_name = f"Character_0{ped_id}"
        else:
            char_name = f"Character_{ped_id}"
        prim_path = f"/World/Characters/{char_name}"

        ped = Pedestrian(ped_id, prim_path, char_name)
        ped.waypoints = list(waypoints)
        ped.loop = loop
        self.pedestrians.append(ped)
        print(f"[{self.name}] Pedestrian {ped_id} registered: {char_name}, "
              f"{len(waypoints)} waypoints, loop={loop}")
        return ped

    async def _open_ira_scene(self) -> None:
        """Open the warehouse via SimulationManager and spawn IRA pedestrians.

        SimulationManager opens the warehouse USD as the ROOT stage, which
        gives the navmesh baker direct access to the floor mesh.  Called only
        when _use_ira_loader=True; setup_pedestrians() must run first so that
        self.pedestrians is populated with waypoints.
        """
        import asyncio
        import carb.settings
        from isaacsim.replicator.agent.core.simulation import SimulationManager

        config_path = "/tmp/warehouse_sim_ira_config.yaml"
        cmd_path    = "/tmp/warehouse_sim_ira_commands.txt"

        ih.generate_ira_command_file(self.pedestrians, cmd_path)

        yaml_text = (
            "isaacsim.replicator.agent:\n"
            "  version: 0.7.0\n"
            "  global:\n"
            "    seed: 42\n"
            "    simulation_length: 9000\n"
            "  scene:\n"
            f"    asset_path: {C.IRA_WAREHOUSE_USD}\n"
            "  character:\n"
            f"    asset_path: {C.IRA_CHARACTERS_DIR}\n"
            f"    command_file: {cmd_path}\n"
            "    filters: []\n"
            f"    num: {len(self.pedestrians)}\n"
            "    spawn_area: []\n"
            "    navigation_area: []\n"
        )
        with open(config_path, "w") as fh:
            fh.write(yaml_text)

        s = carb.settings.get_settings()
        s.set("/exts/isaacsim.replicator.agent/asset_settings/default_biped_assets_path",
              C.IRA_BIPED_USD)
        s.set("/exts/omni.anim.people/command_settings/number_of_loop", "inf")
        s.set("/exts/omni.anim.people/navigation_settings/navmesh_enabled", True)

        sim = SimulationManager()
        setup_done = asyncio.Event()

        def _on_done(event):
            setup_done.set()

        _handle = sim.register_set_up_simulation_done_callback(_on_done)

        ok = sim.load_config_file(config_path)
        if not ok:
            print(f"[{self.name}] ERROR: IRA config file failed to load — "
                  "check IRA_WAREHOUSE_USD in config.py")
            _handle = None
            return

        sim.set_up_simulation_from_config_file()
        print(f"[{self.name}] Waiting for IRA setup "
              f"(navmesh bake + {len(self.pedestrians)} pedestrian(s)) …")

        try:
            await asyncio.wait_for(setup_done.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            print(f"[{self.name}] ERROR: IRA setup timed out — "
                  "check Isaac Sim console for navmesh or asset errors")
        finally:
            _handle = None

        print(f"[{self.name}] IRA scene open — "
              f"{len(self.pedestrians)} pedestrian(s) spawned and wired")

    async def _setup_ira_pedestrians(self) -> None:
        """Generate the IRA command file and spawn all registered pedestrians."""
        cmd_path = "/tmp/warehouse_sim_pedestrians.txt"
        ih.generate_ira_command_file(self.pedestrians, cmd_path)
        await ih.setup_ira_pedestrians(
            C.IRA_BIPED_USD, C.IRA_CHARACTER_USD, cmd_path, len(self.pedestrians)
        )

    def _check_pedestrian_proximity(self) -> None:
        # USD position query for IRA characters — deferred pending future work.
        pass

    # ── Scene construction helpers ────────────────────────────────────────────

    def _spawn_cameras(self):
        """Load four surveillance cameras from the reference USD positions file."""
        created = ih.spawn_cameras_from_usd(self.stage, C.CAMERA_POSITIONS_USD)
        print(f"[{self.name}] {len(created)} surveillance cameras loaded from USD.")

    def _spawn_loading_doors(self):
        """Loading dock gates on the south wall, each with a hidden dock crate."""
        for i, offset in enumerate(self.gate_offsets):
            door_cx = C.WAREHOUSE_CX + offset
            ih.spawn_gate(self.stage, i, door_cx, C)

            # Crate at the dock service position — hidden until door.open() is called.
            crate_path = f"/World/DockCrates/crate_gate_{i}"
            ih.spawn_asset(self.stage, crate_path, C.CRATE_USD,
                           door_cx, C.WALL_Y_MIN + C.LOAD_D / 2.0,
                           0.0, 0.0, scale=C.CRATE_SCALE)
            ih.make_invisible(self.stage, crate_path)
            self.doors[i].crate_prim_path = crate_path

            door_num = self.gate_door_numbers[i] if self.gate_door_numbers else i + 1
            ih.spawn_door_label(self.stage, i, door_cx, C, number=door_num)

        print(f"[{self.name}] {len(self.gate_offsets)} loading dock gates + crates spawned.")

    def _spawn_loading_markings(self):
        """Zebra tape around each loading zone in front of the doors."""
        for i, offset in enumerate(self.gate_offsets):
            door_cx = C.WAREHOUSE_CX + offset
            load_cy = C.WALL_Y_MIN + C.LOAD_D / 2.0
            ih.spawn_zebra_rect(self.stage, f"/World/LoadingAreas/zone_{i}",
                                door_cx, load_cy, C.LOAD_W, C.LOAD_D, C)

    def _spawn_staging_markings(self):
        """Zebra tape around each staging zone (between loading and shelves)."""
        for i, offset in enumerate(self.gate_offsets):
            ih.spawn_zebra_rect(self.stage, f"/World/StagingAreas/zone_{i}",
                                C.WAREHOUSE_CX + offset,
                                C.STAGING_CENTER_Y,
                                C.STAGING_W, C.STAGING_D, C)
