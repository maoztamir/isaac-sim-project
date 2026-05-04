"""
test_pedestrian_visual.py
--------------------------
Visual test for the Pedestrian system.

Scene
-----
  1 forklift  — drives north from spawn point toward the shelves
  1 pedestrian — walks east across the forklift's path at Y = PED_Y

Expected outcome
----------------
The forklift and pedestrian converge at approximately (FORKLIFT_START_X, PED_Y).
When they reach PEDESTRIAN_WARN_DIST apart, a pedestrian_near_miss event fires
(stopped=False).  When they reach PEDESTRIAN_STOP_DIST, both halt and a second
event fires (stopped=True).

STEP 1: build() completes
  EXPECT: warehouse loads, 1 forklift visible near south wall, 1 pedestrian
          visible walking east
  PASS IF: "Scene built: 1 forklifts, 1 pedestrians" printed to console

STEP 2: simulation running (t = 0–10 s)
  EXPECT: forklift drives northward; pedestrian walks eastward
  PASS IF: forklift Y coordinate increases, pedestrian X coordinate increases

STEP 3: near-miss warning (t ≈ 5–8 s)
  EXPECT: console prints "[EventLogger] pedestrian_near_miss" with stopped=False
  PASS IF: evt_log.count("pedestrian_near_miss") >= 1

STEP 4: emergency stop (t ≈ 8–12 s)
  EXPECT: both actors stop; console prints pedestrian_near_miss with stopped=True
  PASS IF: forklift speed ≈ 0, pedestrian state == "stopped"
           evt_log.count("pedestrian_near_miss") >= 2 (warn + stop)

FAIL SIGN: actors pass through each other without stopping, or no events logged.
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
FORKLIFT_START_X = -10.0   # forklift spawns here, drives north
FORKLIFT_START_Y =  -5.0

PED_START_X = -16.0        # pedestrian starts west, walks east
PED_END_X   =  -4.0        # pedestrian destination
PED_Y       =   8.0        # Y coordinate of the crossing path

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
        # Give it a waypoint north of the crossing path
        fl.set_waypoints([(FORKLIFT_START_X, PED_Y + 10.0)])
        self.forklifts.append(fl)

    def setup_pedestrians(self):
        self.spawn_pedestrian(
            x=PED_START_X, y=PED_Y,
            waypoints=[(PED_END_X, PED_Y)],
            loop=False,
        )

    def _assign_initial_waypoints(self):
        self.open_all_doors()

    def on_step(self, dt: float):
        if int(self.sim_time) % 3 == 0 and self.sim_time > 0:
            fl  = self.forklifts[0]
            ped = self.pedestrians[0]
            dist = ped.distance_to(fl.pos[0], fl.pos[1])
            print(f"[test] t={self.sim_time:.1f}s  "
                  f"FL0=({fl.pos[0]:.1f},{fl.pos[1]:.1f}) spd={fl.speed:.2f}  "
                  f"PED=({ped.pos[0]:.1f},{ped.pos[1]:.1f}) state={ped.state}  "
                  f"dist={dist:.2f}m  "
                  f"near_miss_events="
                  f"{self.evt_log.count('pedestrian_near_miss')}")


# ── Entry point ───────────────────────────────────────────────────────────────
scenario = PedestrianTestScenario(seed=0)
scenario.evt_log_print = True   # set before build so events print


async def _run():
    await scenario.build()
    # Enable event printing after build
    if scenario.evt_log:
        scenario.evt_log.print_events = True
    print("[test] Starting simulation — watch for pedestrian_near_miss events.")
    scenario.start()


asyncio.ensure_future(_run())
