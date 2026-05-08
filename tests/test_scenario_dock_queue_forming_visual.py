"""
Visual test — DOCK QUEUE FORMING spec scenario.

STEP 1: Build & focus camera
  EXPECT: Warehouse loads, door 1 (centre) is open, doors 0/2 closed.
          Active viewport switches to cam_dock_queue (looking south at door 1
          from above and slightly north of staging).
  PASS IF: Frame contains door 1 + 3 pallets in its loading zone + FL0 parked
           at the dock + FL1 and FL2 standing further north.
  FAIL SIGN: Wrong camera, no pallets visible, or all forklifts stacked.

STEP 2: t = 0.0–2.0 s — FL1 arrives
  EXPECT: FL1 drives smoothly south from far_approach_1 → dock_queue_1.
          FL0 stays still at the dock; FL2 stays put far north.
  PASS IF: At t≈2 s, FL1 sits at dock_queue_1 (≈ -10.4, -16.9), FL2 has not moved.
  FAIL SIGN: FL1 doesn't move, or FL2 also moves.

STEP 3: t = 2.0–6.0 s — Micro-adjust phase
  EXPECT: FL0 oscillates ±0.3 m along Y around its dock pose (period 2 s).
          FL1 and FL2 are completely still.
  PASS IF: Visible back-and-forth of FL0; FL1 and FL2 motionless.
  FAIL SIGN: FL0 still, or FL1/FL2 drift.

STEP 4: t = 6.0–8.0 s — FL2 arrives
  EXPECT: FL2 drives south from its parked spot toward staging_hold_1.
          FL0 keeps micro-adjusting; FL1 holds in queue.
  PASS IF: At t≈8 s, FL2 has reached staging_hold_1 (≈ -10.4, -7.65).
  FAIL SIGN: FL2 does not move, or FL1 also moves.

STEP 5: After t > 8 s
  EXPECT: All three forklifts hold their final positions.
  PASS IF: No drift after t=8 s.
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

# ── Test ─────────────────────────────────────────────────────────────────────
import asyncio
from warehouse_sim.scenarios import get_scenario_class


async def _run():
    print("[test] Instantiating SpecScenario(dock_queue_forming) ...")
    cls = get_scenario_class("dock_queue_forming")
    scenario = cls(seed=42)
    await scenario.build()
    scenario.start()
    print("[test] Scenario started — observe the timeline play out over ~8 s.")


asyncio.ensure_future(_run())
