"""
Visual test: WAREHOUSE_DOOR_IDLE_003 — Door Idle While Open.

Run in Isaac Sim Script Editor (Window > Script Editor), then Ctrl+Enter.
NOTE: IRA navmesh bake adds ~10–30 s to scene load — wait for build complete.

STEP 1: Scene build
  EXPECT: Warehouse loads (IRA bake takes 10–30 s). Centre door (label "2")
          open; left and right doors closed. Two pallets at centre door
          entrance. FL0 at left background, FL1 at right background.
          Two pedestrians begin walking east and west patrol loops.
  PASS IF: One door open; 2 pallets at entrance; 2 FLs in background;
           pedestrians visible and walking.
  FAIL SIGN: All doors open; pallets missing; any forklift at dock.

STEP 2: Ongoing — background patrol
  EXPECT: FL0 drives south (toward staging_hold left), steering naturally
          with front-wheel turning — no sideways slide. Reaches staging_hold,
          reverses direction, drives north back to far_approach. Repeats.
          FL1 mirrors this on the right side independently.
          Pedestrians continue walking their loops.
  PASS IF: Both forklifts visibly turn to face their travel direction;
           patrol loops continuously; centre loading zone stays empty.
  FAIL SIGN: Forklifts slide sideways; either forklift approaches gate 1.

STEP 3: Continuous hold — idle door
  EXPECT: Centre door stays open. Two pallets untouched. Console prints
          door_idle_duration climbing and forklift_proximity_to_door > 10 m.
  PASS IF: dock_occupied=False in every log line; proximity > 10 m always.
  FAIL SIGN: Any forklift within 10 m of centre dock; pallets move.
"""

import sys
import os

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

# ── Knobs ────────────────────────────────────────────────────────────────────
SCENARIO_NAME = "door_idle"
SEED          = 42

# ── Run ──────────────────────────────────────────────────────────────────────
import asyncio
from warehouse_sim.scenarios import get_scenario_class


async def _run():
    cls = get_scenario_class(SCENARIO_NAME)
    scenario = cls(seed=SEED)
    print(f"[test] building scenario: {SCENARIO_NAME}")
    await scenario.build()
    print("[test] build complete — do NOT call scenario.start()")
    print("[test] observe: centre door open, 2 pallets at entrance")
    print("[test] FL0 left background, FL1 right background — natural steering patrol")
    print("[test] 2 IRA pedestrians walking east/west loops")


asyncio.ensure_future(_run())
