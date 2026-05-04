"""
Test: Forklift Movement — end-to-end drive cycle verification.

Verifies the three bugs fixed in this session:
  Bug 1: _tick_drive no longer sets STATE_IDLE on arrival (rule engine owns transitions)
  Bug 2: Multi-hop waypoint lists are traversed fully before stopping
  Bug 3: PICKUP_AT_SHELVES drives to the aisle before counting the pickup timer

EXPECTED VISUAL OUTCOMES
========================

STEP 1: Scene build + first physics step
  EXPECT: Warehouse loads, 4 forklifts appear near the south end of the warehouse.
  PASS IF: Console prints "[ShelfMap] decal scan complete: 6 rects, 5 aisles"
            and "[dock_queue] ShelfMap ready, waypoints assigned."
  FAIL SIGN: "[ShelfMap] prim scan..." (fallback scan used) or fewer than 6 rects.

STEP 2: t=0–15 s — initial dispatch
  EXPECT: All 4 forklifts begin moving northward toward the shelf aisles.
          Each forklift lines up with an aisle X (≈ -20.4, -15.4, -10.5, -5.5).
  PASS IF: All forklifts show spd > 0.0 in the console telemetry at t=10s.
  FAIL SIGN: Any forklift still at spawn position (y ≈ -18) with spd=0.0.

STEP 3: t=15–40 s — pickup at shelves
  EXPECT: Forklifts enter the shelf area (y > 8), slow down in the aisles,
          stop briefly at the pickup point, then reverse south toward staging.
  PASS IF: Console shows RuleEngine transitions
              pickup_at_shelves → move_to_staging
            AND forklift Y positions reach > 8.0 before t=40s.
  FAIL SIGN: Forklifts oscillate at the aisle entrance or never exceed y=8.

STEP 4: t=40–80 s — staging → loading dock cycle
  EXPECT: Loaded forklifts (pallet visible on forks) converge on the staging area
          (y ≈ -7.65), then queue for the single loading dock slot.
          The dock area (y < -18.9) should have at most 1 forklift at a time.
  PASS IF: RuleEngine logs show move_to_staging → move_to_loading → loading → returning
            AND [events] shows buildup events only when LoadingZone occupancy > 1.
  FAIL SIGN: All forklifts park in the loading zone simultaneously (occupancy=3+).

STEP 5: t=80–180 s — sustained cycling
  EXPECT: Forklifts continue the full pickup→staging→dock→return cycle.
          Positions vary; no forklift is stuck at its spawn coords for > 30s.
  PASS IF: At t=120s telemetry shows different positions than at t=10s for all forklifts.
  FAIL SIGN: Any forklift position unchanged from t=10s to t=120s.
"""

import sys
import os
import asyncio

# ── Hot-reload block ─────────────────────────────────────────────────────────
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

# ── Test knobs ────────────────────────────────────────────────────────────────
SCENARIO_NAME   = "dock_queue"   # 4 forklifts, 20s loading, 1 dock slot
RUN_SECONDS     = 180.0          # how long to let the simulation run
TELEMETRY_EVERY = 10.0           # print forklift positions every N seconds

# ── Test body ─────────────────────────────────────────────────────────────────

async def _run():
    from warehouse_sim.scenarios.dock_queue import DockQueueScenario

    print(f"\n[test] Building {SCENARIO_NAME} scenario...")
    scenario = DockQueueScenario(seed=42)
    await scenario.build()

    print(f"[test] Scene built — {len(scenario.forklifts)} forklifts, "
          f"{len(scenario.area_mgr.areas)} areas")
    print(f"[test] Aisle Xs: {scenario.shelf_map.aisle_xs}")
    print(f"[test] Starting simulation for {RUN_SECONDS}s ...")
    scenario.start()

    # Let the sim run; telemetry is printed by the scenario's own 10s timer.
    # We just wait here; the physics callback drives everything.
    print(f"[test] Simulation running — watch the viewport and console output.")
    print(f"[test] PASS criteria listed in the file's docstring.")

asyncio.ensure_future(_run())
