"""
Visual test — door number labels (1, 2, 3) above loading dock gates.

STEP 1: Scene build
  EXPECT: Warehouse loads with 3 yellow 7-segment digits above the dock gates.
  PASS IF: Gate 0 (left) shows "1", gate 1 (centre) shows "2", gate 2 (right) shows "3".
           Each digit is ~1 m tall, yellow, centred over its gate opening,
           floating ~0.6 m above the drum housing (approx 5.1 m from floor).
  FAIL SIGN: No yellow cubes above the gates, or all three show the same digit shape.

STEP 2: Digit shapes
  EXPECT:
    Label 1 (left gate):   two vertical bars on the right side only (no horizontals).
    Label 2 (centre gate): top + top-right + middle + bottom-left + bottom bars.
    Label 3 (right gate):  top + top-right + middle + bottom-right + bottom bars.
  PASS IF: Shapes are visually distinct and match the standard 7-segment patterns.
  FAIL SIGN: All three labels look identical.

STEP 3: Prim paths
  EXPECT: Console prints the prim paths for all label segments without errors.
  PASS IF: Paths like /World/DockLabels/label_0/tr, /World/DockLabels/label_1/top … exist.
  FAIL SIGN: "prim not found" or Python traceback in console.
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
SCENARIO = "dock_queue"   # any scenario works; labels come from base build()

# ── Test ─────────────────────────────────────────────────────────────────────
import asyncio
from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih
from pxr import UsdGeom


async def _run():
    print("[test] STEP 1 — building scene...")
    from warehouse_sim.scenarios.dock_queue import DockQueueScenario
    scenario = DockQueueScenario()
    await scenario.build()
    print("[test] STEP 1 DONE — check viewport for 3 yellow digits above gates.")

    print("[test] STEP 2 — verifying prim paths...")
    stage = ih.get_stage()
    expected = {
        0: {"tr", "br"},
        1: {"top", "tr", "mid", "bl", "bot"},
        2: {"top", "tr", "mid", "br", "bot"},
    }
    all_ok = True
    for gate_idx, segs in expected.items():
        for seg in segs:
            path = f"/World/DockLabels/label_{gate_idx}/{seg}"
            prim = stage.GetPrimAtPath(path)
            if prim.IsValid():
                print(f"  [OK]  {path}")
            else:
                print(f"  [FAIL] missing: {path}")
                all_ok = False

    if all_ok:
        print("[test] STEP 3 PASS — all expected segment prims found.")
    else:
        print("[test] STEP 3 FAIL — one or more segment prims are missing.")


asyncio.ensure_future(_run())
