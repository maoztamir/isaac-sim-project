#!/usr/bin/env python3
"""
Visual positioning test — static forklift + adjustable pallet.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Spawns ONE static forklift at the warehouse centre.
Then spawns a pallet prim as a SIBLING (not child) so its world
position is absolute and easy to understand.

Adjust PALLET_X / PALLET_Y / PALLET_Z at the top, re-run, and compare
where the pallet lands relative to the forklift body in the viewport.
Once you find the right offsets for "pallet sitting on the forks",
report those values and we'll use them in the real test.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 0: Build scene
  EXPECT: Warehouse loads. One forklift appears at (FORKLIFT_X, FORKLIFT_Y).
          A yellow debug cube appears at the forklift origin (Z=0) to mark
          the forklift's world-space anchor point.
  PASS IF: Scene settles, no errors in console.
  FAIL SIGN: Black screen or console errors.

STEP 1: Spawn pallet at current offsets
  EXPECT: A pallet prim appears at the absolute world position:
          X = FORKLIFT_X + PALLET_X
          Y = FORKLIFT_Y + PALLET_Y
          Z = PALLET_Z
          A red debug cube marks the exact spawn point.
  PASS IF: Pallet is visible and you can see where it sits relative
           to the forklift geometry.
  FAIL SIGN: Pallet inside the forklift body, below the floor, or missing.

Iterate:
  - Adjust PALLET_X / PALLET_Y / PALLET_Z and re-run.
  - The console prints the world position so you can track changes.
══════════════════════════════════════════════════════════════
"""

# ── Scene knobs ──────────────────────────────────────────────────────────────
SEED = 42
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import importlib
import math
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

# Wipe __pycache__ so Isaac Sim's embedded Python re-reads the source
# files instead of serving stale bytecode from a previous run.
import glob as _glob
_pyc_root = os.path.join(_project_root, "warehouse_sim")
for _pyc in _glob.glob(os.path.join(_pyc_root, "**", "*.pyc"), recursive=True):
    try:
        os.remove(_pyc)
    except Exception:
        pass

importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")

from pxr import Gf, UsdGeom
from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih
from warehouse_sim.scenarios import PRESETS


def _banner(title):
    print(f"\n{'═' * 60}\n  {title}\n{'═' * 60}")


async def _run():
    # ── STEP 0: Build scene ──────────────────────────────────────────────────
    _banner("STEP 0: Build scene — one static forklift")

    scenario = PRESETS["dock_queue"](seed=SEED)
    await scenario.build()
    stage = scenario.stage
    assets_root = scenario.assets_root

    # NOTE: scenario.start() is NOT called — scene is completely static.

    # Pick the first forklift so we can read its world position.
    fl = scenario.forklifts[0]
    fl_x, fl_y = fl.pos[0], fl.pos[1]
    print(f"  forklift 0 world position: ({fl_x:.2f}, {fl_y:.2f})")
    print(f"  forklift 0 prim path:      {fl.prim_path}")
    print(f"  forklift 0 heading:        {fl.heading:.1f} deg")

    # Small yellow cube at the forklift's world anchor (Z=0) so you can
    # see the exact reference point in the viewport.
    anchor_path = "/World/DEBUG/forklift_anchor"
    UsdGeom.Xform.Define(stage, "/World/DEBUG")
    marker = UsdGeom.Cube.Define(stage, anchor_path)
    marker.AddTranslateOp().Set(Gf.Vec3d(fl_x, fl_y, 0.1))
    marker.AddScaleOp().Set(Gf.Vec3d(0.1, 0.1, 0.1))
    marker.GetDisplayColorAttr().Set([Gf.Vec3f(1.0, 1.0, 0.0)])   # yellow

    # Give the USD one update to fully load the warehouse + forklift geometry.
    for _ in range(120):
        await ih.next_update()
    print("  [PASS] scene built")

    # ── STEP 1: Spawn pallet using calibrated C.PALLET_FORK_LOCAL_* ────────────
    _banner("STEP 1: Spawn pallet using C.PALLET_FORK_LOCAL_* offsets")

    # Convert local-frame offsets to world space using the forklift's heading.
    # The forklift prim has rotateZ = heading, so local→world is:
    #   world_dx = local_x * cos(heading) - local_y * sin(heading)
    #   world_dy = local_x * sin(heading) + local_y * cos(heading)
    theta = math.radians(fl.heading)
    world_x = fl_x + C.PALLET_FORK_LOCAL_X * math.cos(theta) - C.PALLET_FORK_LOCAL_Y * math.sin(theta)
    world_y = fl_y + C.PALLET_FORK_LOCAL_X * math.sin(theta) + C.PALLET_FORK_LOCAL_Y * math.cos(theta)
    world_z = C.PALLET_FORK_LOCAL_Z

    print(f"  local  offset: X={C.PALLET_FORK_LOCAL_X:+.3f}  Y={C.PALLET_FORK_LOCAL_Y:+.3f}  Z={C.PALLET_FORK_LOCAL_Z:.3f}")
    print(f"  forklift heading: {fl.heading:.1f} deg")
    print(f"  => pallet world position: ({world_x:.3f}, {world_y:.3f}, {world_z:.3f})")

    pallet_path = "/World/DEBUG/test_pallet"
    ih.spawn_asset(stage, pallet_path,
                   C.PALLET_USD,
                   world_x, world_y, world_z, 0.0,
                   scale=C.PALLET_SCALE)

    # BLUE cube = pallet USD origin (0,0,0) in the asset — this is what
    # the code actually controls. The visible pallet mesh sits somewhere
    # OFFSET from this blue dot based on the asset's internal transforms.
    origin_path = "/World/DEBUG/pallet_origin"
    origin = UsdGeom.Cube.Define(stage, origin_path)
    origin.AddTranslateOp().Set(Gf.Vec3d(world_x, world_y, world_z))
    origin.AddScaleOp().Set(Gf.Vec3d(0.08, 0.08, 0.08))
    origin.GetDisplayColorAttr().Set([Gf.Vec3f(0.0, 0.4, 1.0)])    # blue

    # Red cube — movable reference dot (drag this to the target fork position).
    dot_path = "/World/DEBUG/pallet_dot"
    dot = UsdGeom.Cube.Define(stage, dot_path)
    dot.AddTranslateOp().Set(Gf.Vec3d(world_x, world_y, world_z))
    dot.AddScaleOp().Set(Gf.Vec3d(0.05, 0.05, 0.05))
    dot.GetDisplayColorAttr().Set([Gf.Vec3f(1.0, 0.0, 0.0)])       # red

    for _ in range(60):
        await ih.next_update()

    print()
    print("  THREE markers in the viewport:")
    print("  Yellow cube = forklift world anchor (Z=0)")
    print("  BLUE  cube  = pallet USD origin (0,0,0) — what the code controls")
    print("  Red   cube  = movable reference dot")
    print()
    print("  The pallet mesh appears offset from the BLUE cube by the")
    print("  asset's internal transforms (not under our control).")
    print()
    print("  Move the BLUE cube to where you want the pallet to sit on")
    print("  the forks. Report the offset from its current position.")
    print(f"  Current blue cube world pos: ({world_x:.3f}, {world_y:.3f}, {world_z:.3f})")
    _banner("DONE — move the BLUE cube to the correct fork position")


asyncio.ensure_future(_run())
