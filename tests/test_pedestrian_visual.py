"""
test_pedestrian_visual.py
--------------------------
Visual test: one forklift driving northward + one IRA-animated pedestrian
patrolling across the same area.

NOTE: Proximity-based emergency-stop (near-miss events) is deferred — the
pedestrian no longer has a kinematic pos attribute.  This test verifies that:
  - IRA pedestrian spawns and walks alongside active forklifts without error
  - The scenario framework handles mixed forklift+pedestrian setup correctly

STEP 1: build() completes
  EXPECT: warehouse loads, 1 forklift near south wall, 1 animated person visible
  PASS IF: "Scene built: 1 forklifts, 1 pedestrians" printed to console

STEP 2: simulation running
  EXPECT: forklift drives northward; pedestrian walks its patrol route
  PASS IF: forklift Y coordinate increases in console output;
           character figure visibly moves in viewport

FAIL SIGN: "unexpected keyword argument" error in console; figures stand still.
"""

import asyncio
import os
import sys

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

# ── Test knobs ────────────────────────────────────────────────────────────────
FORKLIFT_START_X = -10.0
FORKLIFT_START_Y =  -5.0

# Pedestrian patrol: east-west route across the open floor
PED_WAYPOINTS = [
    (-16.0,  8.0),
    ( -4.0,  8.0),
    ( -4.0, -5.0),
    (-16.0, -5.0),
]

# ── Scenario subclass ─────────────────────────────────────────────────────────
from warehouse_sim.scenarios.base import Scenario
from warehouse_sim.models.forklift import Forklift
from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih


class PedestrianTestScenario(Scenario):
    name = "test_pedestrian"
    num_forklifts = 1

    def setup_forklifts(self):
        path = "/World/Forklifts/forklift_0"
        ih.spawn_asset(self.stage, path,
                       self.assets_root + C.FORKLIFT_USD,
                       FORKLIFT_START_X, FORKLIFT_START_Y, 0.0, 90.0)
        fl = Forklift(0, path, FORKLIFT_START_X, FORKLIFT_START_Y, heading=90.0)
        fl.set_waypoints([(FORKLIFT_START_X, 15.0)])
        self.forklifts.append(fl)

    def setup_pedestrians(self):
        self.spawn_pedestrian(waypoints=PED_WAYPOINTS, loop=True)

    def _assign_initial_waypoints(self):
        self.open_all_doors()

    def on_step(self, dt: float):
        if int(self.sim_time) % 5 == 0 and self.sim_time > 0:
            fl = self.forklifts[0]
            ped = self.pedestrians[0]
            print(f"[test] t={self.sim_time:.1f}s  "
                  f"FL0=({fl.pos[0]:.1f},{fl.pos[1]:.1f}) spd={fl.speed:.2f}  "
                  f"ped={ped}")


# ── Entry point ───────────────────────────────────────────────────────────────
scenario = PedestrianTestScenario(seed=0)


async def _run():
    await scenario.build()
    if scenario.evt_log:
        scenario.evt_log.print_events = True
    print("[test] Starting simulation.")
    scenario.start()


asyncio.ensure_future(_run())
