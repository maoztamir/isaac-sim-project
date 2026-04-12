"""
Visual test for Task #11 — ConfigScenario (config-driven scenario mechanism).

Verifies ConfigScenario behaviour using lightweight stubs — no Isaac Sim
scene required.

─────────────────────────────────────────────────────────────────────────────
EXPECTED VISUAL OUTCOMES
─────────────────────────────────────────────────────────────────────────────

STEP 1: Module import
  EXPECT: "warehouse_sim loaded from: .../isaac-sim-project/..."
  PASS IF: Path contains "isaac-sim-project"
  FAIL SIGN: ModuleNotFoundError or wrong path

STEP 2: CONFIG_SCENARIOS contains "vehicle_idle"
  EXPECT: "[test] CONFIG_SCENARIOS keys: vehicle_idle ✓"
  PASS IF: "vehicle_idle" in C.CONFIG_SCENARIOS
  FAIL SIGN: KeyError or missing key

STEP 3: get_scenario_class for a PRESETS name returns the Python class
  EXPECT: "[test] get_scenario_class('dock_queue') → DockQueueScenario ✓"
  PASS IF: returned object is DockQueueScenario (the actual class)
  FAIL SIGN: returns a factory instead of the class, or raises KeyError

STEP 4: get_scenario_class for a CONFIG_SCENARIOS name returns a factory
  EXPECT: "[test] get_scenario_class('vehicle_idle') → ConfigScenario[vehicle_idle] ✓"
  PASS IF: callable and __name__ == "ConfigScenario[vehicle_idle]"
  FAIL SIGN: raises KeyError or wrong __name__

STEP 5: ConfigScenario init wires config correctly
  EXPECT: "[test] vehicle_idle init: 4 forklifts, loading_dur=6.0, pinned={1, 2} ✓"
  PASS IF: num_forklifts=4, loading_duration=6.0, _pinned_idle_ids=={1,2}
  FAIL SIGN: wrong values

STEP 6: _assign_initial_waypoints with open_all_at_start=True opens all doors
  EXPECT: "[test] vehicle_idle: all doors open after _assign_initial_waypoints ✓"
  PASS IF: all(d.is_open for d in scen.doors)
  FAIL SIGN: any door still closed

STEP 7: Pinned forklifts FL1 and FL2 stay in STATE_IDLE after 250 steps
  EXPECT: "[test] vehicle_idle: FL1 and FL2 remain IDLE after 250 steps ✓"
  PASS IF: fl.state == STATE_IDLE for FL1 and FL2 throughout
  FAIL SIGN: either forklift transitions to a non-idle state

STEP 8: Door events fire at the configured sim_time
  EXPECT: "[test] door_event: close_all at T=30s → 3 door_close events ✓"
           "[test] door_event: open_all  at T=50s → 3 door_open  events ✓"
  PASS IF: doors closed at T=31s, reopened at T=51s; event counts correct
  FAIL SIGN: doors never change state or events not logged

STEP 9: get_scenario_class raises KeyError for unknown name
  EXPECT: "[test] get_scenario_class('nonexistent') raises KeyError ✓"
  PASS IF: KeyError raised with message listing available names
  FAIL SIGN: no exception raised

─────────────────────────────────────────────────────────────────────────────
"""

import sys
import os

# ── Hot-reload block ──────────────────────────────────────────────────────────
_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"
_bad_paths = []
for p in list(sys.path):
    try:
        if p and p != _project_root and os.path.isdir(os.path.join(p, "warehouse_sim")):
            _bad_paths.append(p)
    except Exception:
        pass
for p in _bad_paths:
    while p in sys.path:
        sys.path.remove(p)
if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

_to_remove = [k for k in sys.modules if k.startswith("warehouse_sim")]
for k in _to_remove:
    del sys.modules[k]

for k in list(sys.modules):
    if k.startswith("warehouse_sim") and sys.modules.get(k) is None:
        sys.modules.pop(k, None)

import glob as _glob
for _pyc in _glob.glob(
        os.path.join(_project_root, "warehouse_sim", "**", "*.pyc"),
        recursive=True):
    try:
        os.remove(_pyc)
    except OSError:
        pass

import importlib
importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")
# ─────────────────────────────────────────────────────────────────────────────

import asyncio

DT = 0.1
OUTPUT_DIR = os.path.join(_project_root, "tests", "output")

# Patch LoadingDoor to work without a real USD stage
from warehouse_sim.models import loading_door as _ld_mod
_ld_mod.LoadingDoor.open  = lambda self, stage: setattr(self, "is_open", True)
_ld_mod.LoadingDoor.close = lambda self, stage: setattr(self, "is_open", False)


# ── Stubs ─────────────────────────────────────────────────────────────────────

class _StubShelfMap:
    ready = True
    aisle_xs = [-20.36, -15.41, -10.45, -5.49, -0.54]
    area_y_min = 8.11
    area_y_max = 25.73
    rects = []
    def init(self, stage): pass
    def inside_shelf(self, x, y, margin=0.0): return False
    def in_shelf_area(self, y): return y > 8.0
    def nearest_aisle(self, x):
        return min(self.aisle_xs, key=lambda ax: abs(ax - x))


class _StubFL:
    def __init__(self, fl_id, x, y, speed=0.0, state=None):
        from warehouse_sim import config as C
        self.id = fl_id; self.pos = [x, y]; self.speed = speed
        self.state = state or C.STATE_IDLE
        self.waypoints = []; self.wp_idx = 0; self.state_timer = 0.0
    def update(self, dt, stage, shelf_map, all_forklifts): pass
    def set_waypoints(self, wps, start_idx=0):
        self.waypoints = wps; self.wp_idx = 0


class _StubRE:
    def __init__(self, loading_dur): self._loading_duration = loading_dur
    def tick(self, dt): pass


def _wire_scenario(scen, num_forklifts, loading_dur):
    """Wire monitoring, areas, forklifts, and rule_engine onto a Scenario instance."""
    from warehouse_sim.areas import AreaManager
    from warehouse_sim.models.loading_door import LoadingDoor
    from warehouse_sim.monitoring import ZoneMonitor, EventLogger, MetricsWriter

    scen.shelf_map = _StubShelfMap()
    scen.area_mgr = AreaManager()
    scen.area_mgr.add("LoadingZone", -21.0, 0.0, -23.4, -19.0, capacity=1)
    scen.area_mgr.add("StagingArea", -22.0, 1.0, -12.0, -5.0, capacity=6)
    scen.area_mgr.add("ShelvesArea", -24.5, 3.7, 8.0, 26.0, capacity=None)

    scen.forklifts = [
        _StubFL(i, -10.0 + i * 2, -21.0, speed=0.0)
        for i in range(num_forklifts)
    ]
    scen._idle_secs = {fl.id: 0.0 for fl in scen.forklifts}
    scen._prox_cooldown = {}
    scen.doors = [LoadingDoor(i, is_open=False) for i in range(3)]
    scen.stage = None

    scen.evt_log = EventLogger(print_events=False)
    scen.zone_mon = ZoneMonitor(scen.area_mgr)
    scen.metrics_writer = MetricsWriter(
        scen.zone_mon, scen.evt_log,
        output_dir=OUTPUT_DIR, flush_interval=0, snapshot_interval=DT)

    scen.rule_engine = _StubRE(loading_dur)
    scen.queue_mgr = None


async def _run():
    from warehouse_sim import config as C
    from warehouse_sim.scenarios import PRESETS, get_scenario_class
    from warehouse_sim.scenarios.dock_queue import DockQueueScenario
    from warehouse_sim.scenarios.config_scenario import ConfigScenario
    from warehouse_sim.monitoring.event_logger import EVENT_DOOR_OPEN, EVENT_DOOR_CLOSE

    # ── STEP 2: CONFIG_SCENARIOS ──────────────────────────────────────────────
    assert "vehicle_idle" in C.CONFIG_SCENARIOS, \
        f"'vehicle_idle' not in CONFIG_SCENARIOS: {list(C.CONFIG_SCENARIOS.keys())}"
    print(f"[test] CONFIG_SCENARIOS keys: {' '.join(C.CONFIG_SCENARIOS.keys())} ✓")

    # ── STEP 3: PRESETS take priority ─────────────────────────────────────────
    cls = get_scenario_class("dock_queue")
    assert cls is DockQueueScenario, f"Expected DockQueueScenario, got {cls}"
    print(f"[test] get_scenario_class('dock_queue') → {cls.__name__} ✓")

    # ── STEP 4: CONFIG_SCENARIOS returns a factory ────────────────────────────
    factory = get_scenario_class("vehicle_idle")
    assert callable(factory), "Expected callable factory"
    assert factory.__name__ == "ConfigScenario[vehicle_idle]", \
        f"Wrong __name__: {factory.__name__}"
    print(f"[test] get_scenario_class('vehicle_idle') → {factory.__name__} ✓")

    # ── STEP 5: ConfigScenario init ───────────────────────────────────────────
    vi = factory(seed=42)
    assert isinstance(vi, ConfigScenario)
    assert vi.num_forklifts == 4
    assert vi.loading_duration == 6.0
    assert vi._pinned_idle_ids == {1, 2}
    print(f"[test] vehicle_idle init: {vi.num_forklifts} forklifts, "
          f"loading_dur={vi.loading_duration}, "
          f"pinned={vi._pinned_idle_ids} ✓")

    # ── STEP 6: _assign_initial_waypoints opens doors ─────────────────────────
    _wire_scenario(vi, vi.num_forklifts, vi.loading_duration)
    vi._assign_initial_waypoints()
    assert all(d.is_open for d in vi.doors), \
        f"Not all doors open after _assign_initial_waypoints: {[d.is_open for d in vi.doors]}"
    print(f"[test] vehicle_idle: all doors open after _assign_initial_waypoints ✓")

    # ── STEP 7: Pinned forklifts stay IDLE ───────────────────────────────────
    for _ in range(250):
        vi.sim_time += DT
        vi.on_step(DT)

    for fl_id in [1, 2]:
        fl = next(f for f in vi.forklifts if f.id == fl_id)
        assert fl.state == C.STATE_IDLE, \
            f"FL{fl_id} should be IDLE, got {fl.state}"
    print(f"[test] vehicle_idle: FL1 and FL2 remain IDLE after 250 steps ✓")

    # ── STEP 8: Door events fire at the right sim_time ────────────────────────
    # Build a fresh ConfigScenario with door events for this test
    door_event_cfg = {
        "num_forklifts": 4,
        "loading_duration": 6.0,
        "doors": {
            "open_all_at_start": True,
            "events": [
                {"at_sim_time": 30.0, "action": "close_all"},
                {"at_sim_time": 50.0, "action": "open_all"},
            ],
        },
        "idle_forklift_ids": [],
    }
    de = ConfigScenario(door_event_cfg, seed=42)
    _wire_scenario(de, de.num_forklifts, de.loading_duration)
    de._assign_initial_waypoints()
    assert all(d.is_open for d in de.doors), "Door-event scenario: doors should open at start"

    # Advance to T=31 — close_all should fire
    sim_time = 0.0
    for _ in range(320):   # 32 s @ 0.1 dt
        sim_time += DT
        de.sim_time = sim_time
        de.on_step(DT)

    assert all(not d.is_open for d in de.doors), \
        f"Doors should be closed at T={sim_time:.1f}s"
    closes = de.evt_log.count(EVENT_DOOR_CLOSE)
    assert closes == 3, f"Expected 3 door_close events, got {closes}"
    print(f"[test] door_event: close_all at T=30s → {closes} door_close events ✓")

    # Advance to T=51 — open_all should fire
    for _ in range(200):   # 20 more s
        sim_time += DT
        de.sim_time = sim_time
        de.on_step(DT)

    assert all(d.is_open for d in de.doors), \
        f"Doors should be open again at T={sim_time:.1f}s"
    opens = de.evt_log.count(EVENT_DOOR_OPEN)
    assert opens == 3, f"Expected 3 door_open events, got {opens}"
    print(f"[test] door_event: open_all at T=50s → {opens} door_open events ✓")

    # ── STEP 9: KeyError for unknown name ─────────────────────────────────────
    try:
        get_scenario_class("nonexistent_xyzzy")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        msg = str(e)
        assert "nonexistent_xyzzy" in msg or "Available" in msg or "available" in msg.lower()
    print(f"[test] get_scenario_class('nonexistent') raises KeyError ✓")

    print("\n[test] ✓ All ConfigScenario tests passed")


asyncio.ensure_future(_run())
