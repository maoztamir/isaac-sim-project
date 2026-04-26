"""
Visual test — DoorCycleScenario
================================

STEP 1: Scene build
  EXPECT: Warehouse loads. 3 loading dock gates and 3 forklifts appear.
          Gate 0 and gate 2 start OPEN (shutters up, crate visible).
          Gate 1 starts CLOSED (shutter down, no crate).
  PASS IF: Correct initial states printed in Script Editor output:
             door 0 → OPEN   (next toggle in 20.0 s)
             door 1 → CLOSED (next toggle in 5.0 s)
             door 2 → OPEN   (next toggle in 14.0 s)
  FAIL SIGN: All doors in the same state, or no doors spawned.

STEP 2: First toggle (~5 s)
  EXPECT: Gate 1 opens. Crate becomes visible at gate 1 service position.
  PASS IF: Log prints  "door 1  CLOSED → OPEN  (stays open 20.0 s)"
  FAIL SIGN: No toggle line after 5 s, or wrong gate toggles.

STEP 3: Second toggle (~14 s)
  EXPECT: Gate 2 closes. Shutter descends.
  PASS IF: Log prints  "door 2  OPEN → CLOSED"
  FAIL SIGN: Gate 2 stays open past 14 s.

STEP 4: Third toggle (~20 s)
  EXPECT: Gate 0 closes.
  PASS IF: Log prints  "door 0  OPEN → CLOSED"

STEP 5: Forklifts react to closed doors
  EXPECT: Any forklift that was en-route to a closed dock stops in the
          staging area (state=wait_in_staging) rather than driving into
          a closed gate.
  PASS IF: Status log shows at least one FL in wait_in_staging while
           the target gate is CLOSED.
  FAIL SIGN: Forklift drives through a closed gate.

STEP 6: Door re-opens, forklift proceeds
  EXPECT: When a closed gate re-opens, a waiting forklift transitions
          to move_to_loading and approaches the dock.
  PASS IF: Status log shows FL state change from wait_in_staging to
           move_to_loading shortly after a CLOSED → OPEN toggle.

STEP 7: Empty-open gate (40% chance each open transition)
  EXPECT: Log prints "CLOSED → OPEN (EMPTY — dock slot blocked ...)".
          The gate shutter rises but NO forklift approaches that dock.
          Status log shows door_N=OPEN(E) while all FLs avoid that gate.
  PASS IF: Over several door cycles, at least one "EMPTY" open is logged
           and no forklift enters the corresponding loading zone.
  FAIL SIGN: A forklift docks at a gate whose slot is blocked (EMPTY).
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

# ── Knobs ─────────────────────────────────────────────────────────────────────
SCENARIO = "door_cycle"
SEED     = 42

import asyncio

async def _run():
    from warehouse_sim.scenarios import get_scenario_class
    cls = get_scenario_class(SCENARIO)
    print(f"[test] Instantiating {cls.__name__} ...")
    scenario = cls(seed=SEED)
    await scenario.build()
    scenario.start()
    print("[test] Running — watch the viewport. See module docstring for expected steps.")

asyncio.ensure_future(_run())
