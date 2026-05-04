"""
Visual test — Showcase scenario (LinkedIn demo).

Paste into Isaac Sim Script Editor and press Ctrl+Enter.
Do NOT call scenario.start() — scene stays still for inspection.

────────────────────────────────────────────────────────────────────────────────
EXPECTED VISUAL OUTCOMES
────────────────────────────────────────────────────────────────────────────────

STEP 1: build()
  EXPECT: Warehouse USD loads. Three dock gates spawn on the south wall.
          All three gate doors are CLOSED (shutters down, no crates visible at dock).
  PASS IF: No crate box is visible in any of the three loading bays.
  FAIL SIGN: Any crate prim is visible at the dock before simulation starts.

STEP 2: Staging area scenery props
  EXPECT: Four pallet assemblies are visible in the staging zone (the yellow-
          striped floor area between loading bays and the shelf aisles). They are
          spread across the full width of the staging zone with some depth
          variation — two near left/right extremes, two near the centre columns.
  PASS IF: Four distinct pallet USD meshes appear on the floor inside the
           staging stripe boundary, not on top of forklifts or walls.
  FAIL SIGN: Staging area is empty / pallets appear outside the zone / error
             in console about PALLET_USD fetch failing.

STEP 3: Tracked pallets (hidden)
  EXPECT: Console prints "[showcase] 4 tracked pallets spawned (hidden)".
          No pallet prims are visible in the shelf area (they are hidden).
          Pallets are spawned during build() (inside setup_forklifts), so they
          exist before the first physics step.
  PASS IF: Console message appears; no floating pallets visible near the shelves.
  FAIL SIGN: Pallets visible in shelf area / console shows exception in spawn.

STEP 4: Forklift fork pallets (requires start())
  NOTE: This step requires running main.py (SCENARIO = "showcase") to see movement.
  EXPECT: After ~10–20 s sim time, forklifts that have completed a pickup cycle
          show a pallet mesh on their forks while in STATE_MOVE_TO_STAGING,
          STATE_WAIT_IN_STAGING, STATE_MOVE_TO_LOADING, or STATE_LOADING.
          The pallet disappears from forks when the forklift enters STATE_RETURNING.
  PASS IF: Console prints "[pallet_flow] Pallet N → FL M (pickup)" as forklifts
           leave shelves; forklift mesh shows a pallet riding on the fork arms.
  FAIL SIGN: "[RuleEngine] FL*: pickup_at_shelves → move_to_staging" fires but
             no pallet appears on forks (means assets_root was None or pallet list
             was empty at transition time).

STEP 5: Gate schedule (requires start())
  EXPECT: At T≈3 s gate 0 (left bay) rolls up with animation, crate appears.
          At T≈8 s gate 2 (right bay) rolls up, crate appears.
          Gate 1 (middle) stays permanently closed; its crate stays hidden.
  PASS IF: Console "[showcase] t=3.Xs — gate 0 opening" then "[showcase] t=8.Xs
           — gate 2 opening". Crate prims visible only at bays 0 and 2.
  FAIL SIGN: All three gates open, or gate 0/2 crates not visible after opening.

────────────────────────────────────────────────────────────────────────────────
"""

import os
import sys

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

import asyncio
from warehouse_sim.scenarios import get_scenario_class
from warehouse_sim import config as C

SEED = 42

print(f"[test] STAGING_CENTER_Y = {C.STAGING_CENTER_Y:.2f}")
print(f"[test] STAGING_Y_NEAR   = {C.STAGING_Y_NEAR:.2f}")
print(f"[test] STAGING_Y_FAR    = {C.STAGING_Y_FAR:.2f}")
print(f"[test] WAREHOUSE_CX     = {C.WAREHOUSE_CX:.2f}")


async def _run():
    cls = get_scenario_class("showcase")
    scenario = cls(seed=SEED)
    await scenario.build()
    # Do NOT call scenario.start() — static inspection only

    print(f"[test] Forklifts in scene: {len(scenario.forklifts)}")
    print(f"[test] Tracked pallets:    {len(scenario.pallets)}")
    print(f"[test] Doors state:        "
          f"{['open' if d.is_open else 'closed' for d in scenario.doors]}")

    # Verify all doors are closed
    assert all(not d.is_open for d in scenario.doors), \
        "FAIL: some door is open at scene build time — should all start closed"

    # Verify tracked pallets were added
    assert len(scenario.pallets) == scenario.num_forklifts, \
        f"FAIL: expected {scenario.num_forklifts} pallets, got {len(scenario.pallets)}"

    # Verify pallets are all hidden (none assigned to forklifts)
    for p in scenario.pallets:
        assert p.assigned_forklift_id is None, \
            f"FAIL: Pallet {p.id} already assigned at scene build time"

    print("[test] PASS — all assertions OK")
    print("[test] Visually confirm:")
    print("  • 4 pallet props visible in staging zone (yellow stripe area)")
    print("  • 0 crates visible at loading bays (all doors closed)")
    print("  • No pallets visible near shelves (tracked pallets hidden)")
    print("  • 4 forklifts present near south wall")


asyncio.ensure_future(_run())
