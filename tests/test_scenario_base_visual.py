"""
Visual test for Task #8 — scenarios/base.py monitoring wiring.

Exercises the new physics-step order using lightweight stubs:
  rule_engine.tick → forklift movement → area occupancy →
  zone_mon.tick → metrics_writer.tick → event checks → on_step

No Isaac Sim scene is needed. Stubs replace ih.*, ShelfMap, and Forklift
so the full Scenario._on_physics_step_inner() path can be driven from
the Script Editor without playing the timeline.

─────────────────────────────────────────────────────────────────────────────
EXPECTED VISUAL OUTCOMES
─────────────────────────────────────────────────────────────────────────────

STEP 1: Module import
  EXPECT: "warehouse_sim loaded from: .../isaac-sim-project/warehouse_sim/__init__.py"
  PASS IF: Path contains "isaac-sim-project"
  FAIL SIGN: ModuleNotFoundError or wrong path

STEP 2: Scenario stub construction
  EXPECT: "[test] Scenario created: 0 forklifts, 0 areas"
  PASS IF: __init__ completes; all monitoring fields are None before build()
  FAIL SIGN: AttributeError — missing doors / zone_mon / evt_log etc.

STEP 3: Manual wiring (replaces build())
  EXPECT: "[test] Wired: 4 forklifts, 3 areas, 3 doors"
  PASS IF: forklifts, area_mgr, doors, evt_log, zone_mon, metrics_writer all set
  FAIL SIGN: AttributeError or wrong counts

STEP 4: Run 30 physics steps (dt=0.1s → 3 sim-seconds)
  EXPECT: "[test] 30 steps complete, sim_time≈3.0s"
  PASS IF: sim_time rounds to 3.0; no exception during inner step
  FAIL SIGN: traceback from _on_physics_step_inner

STEP 5: ZoneMonitor populated
  EXPECT: Three "[ZoneMonitor]" summary lines (LoadingZone, StagingArea, ShelvesArea)
  PASS IF: All three zones appear with forklift_count > 0 for at least one
  FAIL SIGN: All counts = 0

STEP 6: EventLogger — proximity alert fires
  EXPECT: "[test] proximity alerts: >=1"
  PASS IF: At least one EVENT_PROXIMITY_ALERT logged during the 30 steps
  FAIL SIGN: count = 0 (two forklifts start within NEAR_MISS_DIST=2.5m)

STEP 7: EventLogger — idle alert fires after IDLE_WARN_SECS
  EXPECT: "[test] idle alerts: >=1"
  PASS IF: At least one EVENT_IDLE_ALERT logged (forklift in STATE_IDLE for 20s)
  PASS if: extended run to 25s triggers at least one
  FAIL SIGN: count = 0

STEP 8: EventLogger — buildup/queue events fire
  EXPECT: "[test] buildup events: >=1" (staging area at capacity)
  PASS IF: EVENT_BUILDUP_THRESHOLD logged
  FAIL SIGN: count = 0 (area not at capacity in stubs)

STEP 9: MetricsWriter CSV + JSON written
  EXPECT: "[test] CSV rows > 0, JSON events > 0"
  PASS IF: Files exist and contain rows/events
  FAIL SIGN: FileNotFoundError or empty files

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

import importlib
importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import csv
import json
import math

# ── Knobs ─────────────────────────────────────────────────────────────────────
DT            = 0.1      # seconds per step
STEPS_PHASE1  = 30       # 3 sim-seconds — covers proximity check
STEPS_PHASE2  = 220      # 22 more sim-seconds — covers idle alert (IDLE_WARN_SECS=20)
OUTPUT_DIR    = os.path.join(_project_root, "tests", "output")


# ── Minimal stubs ─────────────────────────────────────────────────────────────

class _StubShelfMap:
    ready = True
    aisle_xs = [-20.36, -15.41, -10.45, -5.49, -0.54]

    def init(self, stage): pass
    def inside_shelf(self, x, y, margin=0.0): return False
    def in_shelf_area(self, y): return y > 8.0


class _StubFL:
    """Minimal forklift stub with .update() that does nothing (stationary)."""
    def __init__(self, fl_id, x, y, speed=0.0, state=None):
        from warehouse_sim import config as C
        self.id       = fl_id
        self.pos      = [x, y]
        self.speed    = speed
        self.state    = state or C.STATE_IDLE
        self.waypoints = []
        self.wp_idx   = 0
        self.state_timer = 0.0

    def update(self, dt, stage, shelf_map, all_forklifts):
        pass   # stationary stubs


class _StubRuleEngine:
    def tick(self, dt): pass


async def _run():
    from warehouse_sim import config as C
    from warehouse_sim.scenarios.base import Scenario
    from warehouse_sim.areas import AreaManager
    from warehouse_sim.models.loading_door import LoadingDoor
    from warehouse_sim.monitoring import ZoneMonitor, EventLogger, MetricsWriter
    from warehouse_sim.monitoring.event_logger import (
        EVENT_PROXIMITY_ALERT, EVENT_IDLE_ALERT,
        EVENT_BUILDUP_THRESHOLD, EVENT_QUEUE_FORMED,
    )

    # ── STEP 2: Scenario construction ─────────────────────────────────────────
    scen = Scenario.__new__(Scenario)
    Scenario.__init__(scen, seed=42)
    print(f"[test] Scenario created: {len(scen.forklifts)} forklifts, "
          f"{len(scen.area_mgr.areas)} areas")
    assert scen.evt_log is None
    assert scen.zone_mon is None

    # ── STEP 3: Manual wiring (replaces build()) ──────────────────────────────
    scen.shelf_map = _StubShelfMap()

    # Areas
    scen.area_mgr.add("LoadingZone", -21.0, 0.0, -23.4, -19.0,
                      capacity=C.LOADING_AREA_CAPACITY)
    scen.area_mgr.add("StagingArea", -22.0, 1.0, -12.0, -5.0,
                      capacity=C.STAGING_AREA_CAPACITY)
    scen.area_mgr.add("ShelvesArea", -24.5, 3.7, 8.0, 26.0, capacity=None)

    # Forklifts
    # FL0 + FL1: close together inside loading zone → proximity alert
    # FL2 + FL3: in staging, staging capacity=6 so needs 6 to trigger buildup
    #            place 6 forklifts in staging to trigger buildup threshold
    fl_specs = [
        # (id, x, y, speed, state)
        (0, -10.0, -21.0, 1.5, C.STATE_IDLE),    # loading zone — near FL1
        (1, -11.0, -21.0, 0.8, C.STATE_IDLE),    # loading zone — near FL0 (dist≈1m < 2.5)
        (2,  -8.0,  -8.0, 0.0, C.STATE_IDLE),    # staging
        (3, -10.0,  -8.0, 0.0, C.STATE_IDLE),    # staging
    ]
    scen.forklifts = [_StubFL(*s) for s in fl_specs]
    scen._idle_secs = {fl.id: 0.0 for fl in scen.forklifts}
    scen._prox_cooldown = {}

    # Doors
    scen.doors = [LoadingDoor(i, is_open=False) for i in range(3)]

    # Monitoring
    scen.evt_log        = EventLogger(print_events=False)
    scen.zone_mon       = ZoneMonitor(scen.area_mgr)
    scen.metrics_writer = MetricsWriter(
        scen.zone_mon, scen.evt_log,
        output_dir=OUTPUT_DIR,
        flush_interval=0,          # manual only
        snapshot_interval=DT,
    )

    # Stub rule engine (no real FSM needed for this wiring test)
    scen.rule_engine = _StubRuleEngine()
    scen.stage       = None  # not needed by stubs

    print(f"[test] Wired: {len(scen.forklifts)} forklifts, "
          f"{len(scen.area_mgr.areas)} areas, {len(scen.doors)} doors")
    assert len(scen.forklifts) == 4
    assert len(scen.area_mgr.areas) == 3
    assert len(scen.doors) == 3

    # ── STEP 4: Run 30 physics steps (3 sim-seconds) ──────────────────────────
    for _ in range(STEPS_PHASE1):
        scen._on_physics_step_inner(DT)

    print(f"[test] {STEPS_PHASE1} steps complete, sim_time≈{scen.sim_time:.1f}s")
    assert abs(scen.sim_time - STEPS_PHASE1 * DT) < 0.01

    # ── STEP 5: ZoneMonitor populated ─────────────────────────────────────────
    print("[test] --- ZoneMonitor summary ---")
    scen.zone_mon.print_summary()
    snaps = scen.zone_mon.all_snapshots()
    assert len(snaps) == 3, f"Expected 3 snapshots, got {len(snaps)}"
    total_fls = sum(s.forklift_count for s in snaps.values())
    assert total_fls == len(scen.forklifts), \
        f"Total forklift count across areas should be {len(scen.forklifts)}, got {total_fls}"

    # ── STEP 6: Proximity alert ───────────────────────────────────────────────
    prox = scen.evt_log.count(EVENT_PROXIMITY_ALERT)
    print(f"[test] proximity alerts: {prox} (expect >=1)")
    assert prox >= 1, "No proximity alert fired — FL0/FL1 are within 2.5m at speed>0.5"

    # ── STEP 7: Idle alert — run 220 more steps (22 s total past 3 s) ─────────
    for _ in range(STEPS_PHASE2):
        scen._on_physics_step_inner(DT)

    idle = scen.evt_log.count(EVENT_IDLE_ALERT)
    print(f"[test] idle alerts after {scen.sim_time:.1f}s: {idle} (expect >=1)")
    assert idle >= 1, f"No idle alert fired after {scen.sim_time:.1f}s idle"

    # ── STEP 8: Buildup / queue events ────────────────────────────────────────
    # Staging capacity=6 but only 2 forklifts in staging → no buildup yet.
    # Loading capacity=1 but 2 forklifts in loading → buildup should have fired.
    buildup = scen.evt_log.count(EVENT_BUILDUP_THRESHOLD)
    print(f"[test] buildup events: {buildup} (expect >=1)")
    assert buildup >= 1, "No buildup event — LoadingZone has capacity=1 but 2 forklifts"

    queue = scen.evt_log.count(EVENT_QUEUE_FORMED)
    print(f"[test] queue_formed events: {queue}")

    # ── STEP 9: MetricsWriter flush ───────────────────────────────────────────
    csv_path, json_path = scen.metrics_writer.flush()
    print(f"[test] CSV:  {csv_path}")
    print(f"[test] JSON: {json_path}")
    assert os.path.isfile(csv_path)
    assert os.path.isfile(json_path)

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    print(f"[test] CSV rows: {len(rows)} (expect > 0)")
    assert len(rows) > 0

    with open(json_path) as f:
        events_data = json.load(f)
    print(f"[test] JSON events: {len(events_data)} (expect > 0)")
    assert len(events_data) > 0

    print(f"\n[test] Event summary:")
    print(f"  proximity_alert   = {scen.evt_log.count(EVENT_PROXIMITY_ALERT)}")
    print(f"  idle_alert        = {scen.evt_log.count(EVENT_IDLE_ALERT)}")
    print(f"  buildup_threshold = {scen.evt_log.count(EVENT_BUILDUP_THRESHOLD)}")
    print(f"  queue_formed      = {scen.evt_log.count(EVENT_QUEUE_FORMED)}")
    print(f"  total             = {scen.evt_log.count()}")

    print("\n[test] ✓ All base scenario wiring tests passed")


asyncio.ensure_future(_run())
