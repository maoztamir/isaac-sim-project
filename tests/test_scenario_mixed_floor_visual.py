"""
Visual test: MixedFloorScenario — 3 forklifts + 3 IRA pedestrians via main.py path.

Runs the full scenario stack (Scenario.build() → scenario.start()) so every
layer is exercised: IRA scene loading, ShelfMap, RuleEngine, AreaManager,
ZoneMonitor, EventLogger.

Expected visual outcomes
------------------------
STEP 1: IRA setup (~30-60 s, console activity)
  EXPECT: warehouse opens as root stage, navmesh bakes, three male
          construction-worker figures appear on the open floor
  PASS IF: console prints "IRA scene open — 3 pedestrian(s) spawned and wired"
  FAIL SIGN: timeout; "NavMesh baking failed"; orange capsules instead of people

STEP 2: Scene construction (immediate after STEP 1)
  EXPECT: dock gates, zebra markings, staging zones appear; three yellow
          forklifts spawn near the south wall at staggered X positions
  PASS IF: console prints "Scene built: 3 forklifts, 3 pedestrians, 3 areas, 3 doors"
  FAIL SIGN: missing dock gates or forklifts; Python exception in console

STEP 3: Simulation running
  EXPECT: forklifts drive FSM cycle (shelves → staging → dock → return),
          departing 6 s apart; pedestrians walk east/centre/west rectangular
          patrol routes, all six actors sharing the floor simultaneously
  PASS IF: telemetry every 10 s shows changing forklift positions + states;
           character figures visibly move in viewport; no "invalid command" errors
  FAIL SIGN: forklifts pinned at spawn; pedestrians motionless;
             "GoTo ... invalid command" in console
"""

import sys
import os
import asyncio

# ── Module hot-reload ─────────────────────────────────────────────────────────
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

# ── Run scenario ──────────────────────────────────────────────────────────────
from warehouse_sim.scenarios.mixed_floor import MixedFloorScenario

scenario = MixedFloorScenario(seed=0)


async def _run():
    await scenario.build()
    scenario.evt_log.print_events = True
    scenario.start()
    print("[test] MixedFloorScenario running — "
          "3 forklifts + 3 pedestrians active")


asyncio.ensure_future(_run())
