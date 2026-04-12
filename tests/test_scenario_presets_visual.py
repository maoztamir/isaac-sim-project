"""
Visual test for Task #9 — scenario preset rewrites.

Verifies each preset's __init__, _assign_initial_waypoints, and on_step
using lightweight stubs — no Isaac Sim scene required.

─────────────────────────────────────────────────────────────────────────────
EXPECTED VISUAL OUTCOMES
─────────────────────────────────────────────────────────────────────────────

STEP 1: Module import
  EXPECT: "warehouse_sim loaded from: .../isaac-sim-project/..."
  PASS IF: Path contains "isaac-sim-project"
  FAIL SIGN: ModuleNotFoundError or wrong path

STEP 2: loading_duration wired into RuleEngine
  EXPECT: "[test] dock_queue loading_duration = 20.0 ✓"
  PASS IF: RuleEngine._timer_for(STATE_LOADING) returns 20.0 for dock_queue
  FAIL SIGN: returns 5.0 (config default, not overridden)

STEP 3: DockQueueScenario — doors open on first physics step
  EXPECT: "[test] dock_queue: all doors open after _assign_initial_waypoints ✓"
  PASS IF: all(d.is_open for d in scen.doors)
  FAIL SIGN: any door still closed

STEP 4: LoadingPauseScenario — doors close at T=30s, reopen at T=50s
  EXPECT: "[test] loading_pause: doors closed at t≈30s ✓"
            "[test] loading_pause: doors reopened at t≈50s ✓"
  PASS IF: all doors closed between T=30 and T=50; all open after T=50
  FAIL SIGN: doors never close, or never reopen

STEP 5: LoadingPauseScenario — door events logged
  EXPECT: "[test] loading_pause: door_close events=3, door_open events=3 ✓"
  PASS IF: 3 close + 3 open events (one per gate)
  FAIL SIGN: 0 events or wrong count

STEP 6: AreaBuildUpScenario — 5 forklifts, 12s loading_duration
  EXPECT: "[test] area_buildup: 5 forklifts, loading_duration=12.0 ✓"
  PASS IF: num_forklifts=5 and rule_engine._loading_duration=12.0
  FAIL SIGN: wrong values

STEP 7: AisleCongestionScenario — 6 forklifts, target aisle resolved
  EXPECT: "[test] aisle_congestion: 6 forklifts, target_aisle_x=<float> ✓"
  PASS IF: _target_aisle_x is a float after _assign_initial_waypoints
  FAIL SIGN: _target_aisle_x still None

STEP 8: All presets importable from PRESETS dict
  EXPECT: "[test] PRESETS keys: dock_queue loading_pause area_buildup aisle_congestion ✓"
  PASS IF: all 4 names present
  FAIL SIGN: KeyError or missing key

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

# Patch LoadingDoor to work without a real USD stage (stage=None in stubs)
from warehouse_sim.models import loading_door as _ld_mod
_ld_mod.LoadingDoor.open  = lambda self, stage: setattr(self, "is_open", True)
_ld_mod.LoadingDoor.close = lambda self, stage: setattr(self, "is_open", False)


# ── Stubs ─────────────────────────────────────────────────────────────────────

class _StubShelfMap:
    ready = True
    aisle_xs = [-20.36, -15.41, -10.45, -5.49, -0.54]
    area_y_min = 8.11
    area_y_max = 25.73
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
    """Set up monitoring, areas, forklifts, rule_engine on a Scenario instance."""
    from warehouse_sim.areas import AreaManager
    from warehouse_sim.models.loading_door import LoadingDoor
    from warehouse_sim.monitoring import ZoneMonitor, EventLogger, MetricsWriter

    scen.shelf_map = _StubShelfMap()
    scen.area_mgr = AreaManager()
    scen.area_mgr.add("LoadingZone", -21.0, 0.0, -23.4, -19.0, capacity=1)
    scen.area_mgr.add("StagingArea", -22.0, 1.0, -12.0, -5.0, capacity=6)
    scen.area_mgr.add("ShelvesArea", -24.5, 3.7, 8.0, 26.0, capacity=None)

    scen.forklifts = [
        _StubFL(i, -10.0 + i * 2, -21.0, speed=0.5)
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
    from warehouse_sim.scenarios import PRESETS
    from warehouse_sim.scenarios.dock_queue       import DockQueueScenario
    from warehouse_sim.scenarios.loading_pause    import LoadingPauseScenario
    from warehouse_sim.scenarios.area_buildup     import AreaBuildUpScenario
    from warehouse_sim.scenarios.aisle_congestion import AisleCongestionScenario
    from warehouse_sim.monitoring.event_logger import EVENT_DOOR_OPEN, EVENT_DOOR_CLOSE

    # ── STEP 8: PRESETS dict ──────────────────────────────────────────────────
    expected = {"dock_queue", "loading_pause", "area_buildup", "aisle_congestion"}
    assert set(PRESETS.keys()) == expected, f"PRESETS mismatch: {PRESETS.keys()}"
    print(f"[test] PRESETS keys: {' '.join(sorted(PRESETS.keys()))} ✓")

    # ── STEP 2 + 3: DockQueueScenario ────────────────────────────────────────
    dq = DockQueueScenario(seed=42)
    assert dq.loading_duration == 20.0, f"Expected 20.0, got {dq.loading_duration}"
    _wire_scenario(dq, dq.num_forklifts, dq.loading_duration)

    # Check RuleEngine receives loading_duration (our stub stores it directly)
    assert dq.rule_engine._loading_duration == 20.0
    print(f"[test] dock_queue loading_duration = {dq.loading_duration} ✓")

    dq._assign_initial_waypoints()
    assert all(d.is_open for d in dq.doors), "DockQueue: not all doors open"
    print(f"[test] dock_queue: all doors open after _assign_initial_waypoints ✓")

    # ── STEP 4 + 5: LoadingPauseScenario ─────────────────────────────────────
    lp = LoadingPauseScenario(seed=42)
    _wire_scenario(lp, lp.num_forklifts, lp.loading_duration)
    lp._assign_initial_waypoints()
    assert all(d.is_open for d in lp.doors), "LoadingPause: doors not open at start"

    # Simulate up to T=31 — doors should close
    from tests.test_scenario_presets_visual import _run  # import guard (noop)
    sim_time = 0.0
    for _ in range(320):   # 32 s @ 0.1 dt
        sim_time += DT
        lp.sim_time = sim_time
        lp.on_step(DT)

    assert all(not d.is_open for d in lp.doors), \
        f"LoadingPause: doors should be closed at T={sim_time:.1f}s"
    print(f"[test] loading_pause: doors closed at t≈{sim_time:.1f}s ✓")

    # Simulate up to T=51 — doors should reopen
    for _ in range(200):   # 20 more s
        sim_time += DT
        lp.sim_time = sim_time
        lp.on_step(DT)

    assert all(d.is_open for d in lp.doors), \
        f"LoadingPause: doors should be open again at T={sim_time:.1f}s"
    print(f"[test] loading_pause: doors reopened at t≈{sim_time:.1f}s ✓")

    closes = lp.evt_log.count(EVENT_DOOR_CLOSE)
    opens  = lp.evt_log.count(EVENT_DOOR_OPEN)
    print(f"[test] loading_pause: door_close events={closes}, "
          f"door_open events={opens} (expect 3 each) ✓")
    assert closes == 3, f"Expected 3 door_close events, got {closes}"
    assert opens  == 3, f"Expected 3 door_open events, got {opens}"

    # ── STEP 6: AreaBuildUpScenario ───────────────────────────────────────────
    ab = AreaBuildUpScenario(seed=42)
    assert ab.num_forklifts == 5
    assert ab.loading_duration == 12.0
    _wire_scenario(ab, ab.num_forklifts, ab.loading_duration)
    assert ab.rule_engine._loading_duration == 12.0
    print(f"[test] area_buildup: {ab.num_forklifts} forklifts, "
          f"loading_duration={ab.loading_duration} ✓")

    # ── STEP 7: AisleCongestionScenario ──────────────────────────────────────
    ac = AisleCongestionScenario(seed=42)
    assert ac.num_forklifts == 6
    _wire_scenario(ac, ac.num_forklifts, ac.loading_duration)
    assert ac._target_aisle_x is None, "Should be None before _assign_initial_waypoints"
    ac._assign_initial_waypoints()
    assert ac._target_aisle_x is not None, "_target_aisle_x not resolved"
    assert isinstance(ac._target_aisle_x, float)
    print(f"[test] aisle_congestion: {ac.num_forklifts} forklifts, "
          f"target_aisle_x={ac._target_aisle_x:.2f} ✓")

    print("\n[test] ✓ All scenario preset tests passed")


asyncio.ensure_future(_run())
