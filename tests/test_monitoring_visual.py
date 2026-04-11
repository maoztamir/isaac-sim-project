"""
Visual test for warehouse_sim/monitoring/ package.

Tests ZoneMonitor, EventLogger, and MetricsWriter with a lightweight
in-memory simulation — no Isaac Sim scene required.

─────────────────────────────────────────────────────────────────────────────
EXPECTED VISUAL OUTCOMES
─────────────────────────────────────────────────────────────────────────────

STEP 1: Module import
  EXPECT: "warehouse_sim loaded from: .../isaac-sim-project/warehouse_sim/__init__.py"
  PASS IF: Path contains "isaac-sim-project"
  FAIL SIGN: ModuleNotFoundError or path points to isaac_sim_samples/ root

STEP 2: ZoneManager setup — 3 zones (loading, staging, shelves)
  EXPECT: "[test] ZoneManager: 3 zones: loading staging shelves"
  PASS IF: Exactly those 3 zone names printed
  FAIL SIGN: KeyError or fewer zones

STEP 3: Simulate 5 forklifts ticking through zones for 20 steps
  EXPECT: "[test] tick 20 complete"
  PASS IF: No exception; forklift positions update each step
  FAIL SIGN: AttributeError on ZoneMonitor.tick() or ZoneSnapshot

STEP 4: ZoneMonitor summary
  EXPECT: Three "[ZoneMonitor] <zone> cnt=..." lines
  PASS IF: All three zones appear; forklift_count values sum to <= 5
  FAIL SIGN: All counts = 0 (zone.update_occupant never called)

STEP 5: EventLogger — log one of each event type
  EXPECT: 8 lines printed (one per EVENT_* type if print_events=True)
  PASS IF: event_logger.count() == 8
  FAIL SIGN: count() < 8, or AttributeError on any log_* method

STEP 6: EventLogger queries
  EXPECT: "[test] proximity alerts: 1", "[test] events since t=15: ..."
  PASS IF: proximity alert count == 1, get_since returns subset
  FAIL SIGN: wrong counts or empty lists

STEP 7: MetricsWriter flush
  EXPECT: "[test] CSV: .../metrics_*.csv  JSON: .../events_*.json"
  PASS IF: Both files exist on disk; CSV has header row; JSON parses as list
  FAIL SIGN: FileNotFoundError, empty file, or JSON parse error

STEP 8: CSV contents
  EXPECT: "[test] CSV rows: <n> (should be > 0)"
  PASS IF: n > 0; 'sim_time' and 'zone' columns present
  FAIL SIGN: n == 0 (snapshot never captured)

STEP 9: JSON event contents
  EXPECT: "[test] JSON events: 8"
  PASS IF: 8 event dicts in the JSON array, each with 'type'/'sim_time'/'payload'
  FAIL SIGN: fewer than 8, or missing keys

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
NUM_FORKLIFTS   = 5
SIM_STEPS       = 20
DT              = 0.1          # seconds per step
OUTPUT_DIR      = os.path.join(_project_root, "tests", "output")

# ── Stub forklift — no Isaac Sim dependency ──────────────────────────────────
class _FL:
    def __init__(self, fl_id, x, y, speed=1.0):
        self.id = fl_id
        self.pos = [x, y]
        self.speed = speed


async def _run():
    from warehouse_sim.zones import ZoneManager
    from warehouse_sim.monitoring import ZoneMonitor, EventLogger, MetricsWriter
    from warehouse_sim.monitoring.event_logger import (
        EVENT_DOOR_OPEN, EVENT_DOOR_CLOSE, EVENT_QUEUE_FORMED,
        EVENT_BUILDUP_THRESHOLD, EVENT_STATE_HOLD, EVENT_PALLET_TRANSFER,
        EVENT_PROXIMITY_ALERT, EVENT_IDLE_ALERT,
    )

    # ── STEP 2: ZoneManager setup ─────────────────────────────────────────────
    zm = ZoneManager()
    zm.add("loading",  -17.0, -3.0, -23.4, -19.0)
    zm.add("staging",  -18.5, -1.5, -12.0,  -5.0)
    zm.add("shelves",  -24.5,  3.7,   8.0,  26.0)
    print(f"[test] ZoneManager: {len(zm.zones)} zones: {' '.join(zm.zones.keys())}")

    # ── Build monitoring stack ────────────────────────────────────────────────
    zone_mon = ZoneMonitor(zm)
    evt_log  = EventLogger(print_events=True)
    writer   = MetricsWriter(zone_mon, evt_log, output_dir=OUTPUT_DIR,
                             flush_interval=0,        # manual only
                             snapshot_interval=DT)

    # ── STEP 3: Simulate 20 ticks ─────────────────────────────────────────────
    forklifts = [
        _FL(0,  -8.0, -21.0, speed=0.5),   # inside loading
        _FL(1, -10.0, -21.0, speed=1.2),   # inside loading
        _FL(2,  -9.0,  -8.5, speed=0.8),   # inside staging
        _FL(3,  -5.0,  15.0, speed=2.0),   # inside shelves
        _FL(4, -15.0,  18.0, speed=1.5),   # inside shelves
    ]

    sim_time = 0.0
    for step in range(SIM_STEPS):
        sim_time += DT
        # Move forklifts slightly each step
        for fl in forklifts:
            fl.pos[1] += fl.speed * DT * 0.1

        # Update zone occupancy first
        for fl in forklifts:
            zm.update(fl.id, fl.pos[0], fl.pos[1], sim_time)

        # Tick monitoring
        zone_mon.tick(forklifts, sim_time, DT)
        writer.tick(sim_time, DT)

    print(f"[test] tick {SIM_STEPS} complete")

    # ── STEP 4: ZoneMonitor summary ───────────────────────────────────────────
    print("[test] --- ZoneMonitor summary ---")
    zone_mon.print_summary()

    # ── STEP 5: EventLogger — one of each type ────────────────────────────────
    print("[test] --- Logging one event of each type ---")
    t = sim_time
    evt_log.log_door_open(t, gate_idx=0)
    evt_log.log_door_close(t + 1, gate_idx=0)
    evt_log.log_queue_formed(t + 2, zone_name="loading", depth=3, threshold=2)
    evt_log.log_buildup_threshold(t + 3, zone_name="staging", occupancy=6, capacity=6)
    evt_log.log_state_hold(t + 4, fl_id=1, state="STATE_WAIT_IN_STAGING",
                           held_secs=25.0, threshold=20.0)
    evt_log.log_pallet_transfer(t + 5, fl_id=2, action="pickup", pallet_id=7,
                                location=(-9.0, 15.0))
    evt_log.log_proximity_alert(t + 6, fl_id_a=0, fl_id_b=1,
                                distance=1.8, speed_a=0.5, speed_b=1.2)
    evt_log.log_idle_alert(t + 7, fl_id=3, idle_secs=22.0, zone_name="shelves")

    total = evt_log.count()
    print(f"[test] total events logged: {total} (expect 8)")
    assert total == 8, f"Expected 8 events, got {total}"

    # ── STEP 6: Queries ───────────────────────────────────────────────────────
    prox = evt_log.get_by_type(EVENT_PROXIMITY_ALERT)
    print(f"[test] proximity alerts: {len(prox)} (expect 1)")
    assert len(prox) == 1

    since = evt_log.get_since(t + 5)
    print(f"[test] events since t={t+5:.1f}: {len(since)} (expect 3)")
    assert len(since) == 3, f"Expected 3 events since t+5, got {len(since)}"

    recent = evt_log.get_recent(2)
    print(f"[test] get_recent(2): {[e.type for e in recent]}")
    assert len(recent) == 2

    # ── STEP 7: MetricsWriter flush ───────────────────────────────────────────
    csv_path, json_path = writer.flush()
    print(f"[test] CSV:  {csv_path}")
    print(f"[test] JSON: {json_path}")
    assert os.path.isfile(csv_path),  f"CSV not found: {csv_path}"
    assert os.path.isfile(json_path), f"JSON not found: {json_path}"

    # ── STEP 8: CSV contents ──────────────────────────────────────────────────
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    print(f"[test] CSV rows: {len(rows)} (expect > 0)")
    assert len(rows) > 0, "CSV has no data rows"
    assert "sim_time" in rows[0], "CSV missing 'sim_time' column"
    assert "zone"     in rows[0], "CSV missing 'zone' column"

    # ── STEP 9: JSON event contents ───────────────────────────────────────────
    with open(json_path) as f:
        events_data = json.load(f)
    print(f"[test] JSON events: {len(events_data)} (expect 8)")
    assert len(events_data) == 8, f"Expected 8 events in JSON, got {len(events_data)}"
    for e in events_data:
        assert "type" in e and "sim_time" in e and "payload" in e, \
            f"Event missing required keys: {e}"

    print("[test] ✓ All monitoring tests passed")


asyncio.ensure_future(_run())
