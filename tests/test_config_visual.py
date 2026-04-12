#!/usr/bin/env python3
"""
Visual test for Task #2: config.py extensions.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

No viewport changes — all output goes to the Script Editor console.
Read the printed tables and check every PASS/FAIL line.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 1: Import config
  EXPECT: No errors printed. Module loads cleanly.
  PASS IF: "[PASS] config imported" appears in console.
  FAIL SIGN: ImportError or AttributeError traceback.

STEP 2: FSM states table
  EXPECT: 8 rows, one per state, each showing the string value
          and the expected load property for that state.
  PASS IF: All 8 states present, load column shows "loaded" or
           "unloaded" as described in the plan.
  FAIL SIGN: Missing row, wrong load assignment, or KeyError.

STEP 3: Load property constants
  EXPECT: LOAD_LOADED = "loaded", LOAD_UNLOADED = "unloaded"
  PASS IF: Both lines printed with correct string values.
  FAIL SIGN: AttributeError or wrong value.

STEP 4: Area capacities
  EXPECT: LOADING_AREA_CAPACITY = 1, STAGING_AREA_CAPACITY = 6
  PASS IF: Both values match exactly.
  FAIL SIGN: Wrong number or missing attribute.

STEP 5: Detection thresholds
  EXPECT: 5 thresholds printed with values in realistic ranges
          (seconds > 0, distances > 0, ratio between 0 and 1).
  PASS IF: All 5 present and in range.
  FAIL SIGN: Value <= 0, ratio >= 1, or missing attribute.

STEP 6: Scenario presets
  EXPECT: 6 scenario entries printed, each with at least one lever key.
  PASS IF: All 6 scenario names present, no empty dicts.
  FAIL SIGN: Missing scenario, empty dict, or wrong key name.

STEP 7: STATE_EXPECTED_LOAD consistency
  EXPECT: Every FSM state has an entry in STATE_EXPECTED_LOAD.
  PASS IF: "[PASS] all 8 states covered in STATE_EXPECTED_LOAD"
  FAIL SIGN: "[FAIL] missing states: ..."
══════════════════════════════════════════════════════════════
"""

import asyncio
import os
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"

_bad_paths = []
for p in list(sys.path):
    try:
        if not p or p == _project_root:
            continue
        if os.path.isdir(os.path.join(p, "warehouse_sim")):
            _bad_paths.append(p)
        elif os.path.isfile(os.path.join(p, "warehouse_sim.py")):
            _bad_paths.append(p)
    except Exception:
        pass
for p in _bad_paths:
    while p in sys.path:
        sys.path.remove(p)
    print(f"[test] evicted conflicting sys.path entry: {p}")

if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

_to_remove = [k for k in sys.modules if k.startswith("warehouse_sim")]
for k in _to_remove:
    del sys.modules[k]

for k in list(sys.modules):
    if k.startswith("warehouse_sim") and sys.modules.get(k) is None:
        sys.modules.pop(k, None)

# Delete stale .pyc files so Isaac Sim's persistent interpreter picks up
# source changes rather than cached bytecode from a previous run.
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


def _banner(title):
    print(f"\n{'═' * 60}\n  {title}\n{'═' * 60}")


def _row(label, value, width=30):
    print(f"  {label:<{width}} {value}")


async def _run():
    # ── STEP 1: Import ───────────────────────────────────────────────────────
    _banner("STEP 1: Import config")
    try:
        from warehouse_sim import config as C
        print("  [PASS] config imported")
    except Exception as e:
        print(f"  [FAIL] import error: {e}")
        return

    # ── STEP 2: FSM states table ─────────────────────────────────────────────
    _banner("STEP 2: FSM states + expected load property")
    states = [
        C.STATE_IDLE,
        C.STATE_PICKUP_AT_SHELVES,
        C.STATE_MOVE_TO_STAGING,
        C.STATE_WAIT_IN_STAGING,
        C.STATE_MOVE_TO_LOADING,
        C.STATE_WAIT_AT_DOCK_QUEUE,
        C.STATE_LOADING,
        C.STATE_RETURNING,
    ]
    print(f"  {'State constant':<30} {'Value':<25} {'Expected load'}")
    print(f"  {'-'*30} {'-'*25} {'-'*15}")
    for s in states:
        load = C.STATE_EXPECTED_LOAD.get(s, "MISSING")
        flag = "" if load in (C.LOAD_LOADED, C.LOAD_UNLOADED) else "  ← [FAIL]"
        print(f"  {s:<30} {C.__dict__[next(k for k,v in C.__dict__.items() if v == s and k.startswith('STATE'))]:<25} {load}{flag}")
    print(f"\n  Total states: {len(states)}")
    if len(states) == 8:
        print("  [PASS] 8 states defined")
    else:
        print(f"  [FAIL] expected 8, got {len(states)}")

    # ── STEP 3: Load property constants ─────────────────────────────────────
    _banner("STEP 3: Load property constants")
    _row("LOAD_LOADED",   repr(C.LOAD_LOADED))
    _row("LOAD_UNLOADED", repr(C.LOAD_UNLOADED))
    if C.LOAD_LOADED == "loaded" and C.LOAD_UNLOADED == "unloaded":
        print("  [PASS] load property constants correct")
    else:
        print("  [FAIL] unexpected values")

    # ── STEP 4: Area capacities ───────────────────────────────────────────────
    _banner("STEP 4: Area capacities")
    _row("LOADING_AREA_CAPACITY",  C.LOADING_AREA_CAPACITY)
    _row("STAGING_AREA_CAPACITY",  C.STAGING_AREA_CAPACITY)
    ok = C.LOADING_AREA_CAPACITY == 1 and C.STAGING_AREA_CAPACITY == 6
    print(f"  {'[PASS]' if ok else '[FAIL]'} capacity values {'correct' if ok else 'wrong'}")

    # ── STEP 5: Detection thresholds ─────────────────────────────────────────
    _banner("STEP 5: Detection thresholds")
    thresholds = {
        "QUEUE_SUSTAINED_SECS":   (C.QUEUE_SUSTAINED_SECS,   lambda v: v > 0),
        "IDLE_WARN_SECS":         (C.IDLE_WARN_SECS,         lambda v: v > 0),
        "NEAR_MISS_DIST":         (C.NEAR_MISS_DIST,         lambda v: v > 0),
        "NEAR_MISS_SPEED_MIN":    (C.NEAR_MISS_SPEED_MIN,    lambda v: v > 0),
        "CONGESTION_SPEED_RATIO": (C.CONGESTION_SPEED_RATIO, lambda v: 0 < v < 1),
    }
    all_ok = True
    for name, (val, check) in thresholds.items():
        ok = check(val)
        all_ok = all_ok and ok
        _row(name, f"{val}  {'[PASS]' if ok else '[FAIL] out of range'}")
    print(f"\n  {'[PASS] all thresholds in range' if all_ok else '[FAIL] check values above'}")

    # ── STEP 6: Scenario presets ──────────────────────────────────────────────
    _banner("STEP 6: Scenario presets")
    expected_scenarios = {
        "dock_queue", "loading_pause", "area_buildup",
        "aisle_congestion", "vehicle_idle", "safety_proximity",
    }
    for name, levers in C.SCENARIO_PRESETS.items():
        status = "[PASS]" if levers else "[FAIL] empty"
        print(f"  {status}  {name}")
        for k, v in levers.items():
            print(f"           {k} = {v}")
    missing = expected_scenarios - set(C.SCENARIO_PRESETS.keys())
    if missing:
        print(f"\n  [FAIL] missing scenarios: {missing}")
    else:
        print(f"\n  [PASS] all 6 scenarios present")

    # ── STEP 7: STATE_EXPECTED_LOAD coverage ─────────────────────────────────
    _banner("STEP 7: STATE_EXPECTED_LOAD coverage")
    all_states = set(states)
    covered = set(C.STATE_EXPECTED_LOAD.keys())
    missing_states = all_states - covered
    if missing_states:
        print(f"  [FAIL] missing states: {missing_states}")
    else:
        print(f"  [PASS] all 8 states covered in STATE_EXPECTED_LOAD")

    _banner("ALL STEPS COMPLETE — review [PASS]/[FAIL] lines above")


asyncio.ensure_future(_run())
