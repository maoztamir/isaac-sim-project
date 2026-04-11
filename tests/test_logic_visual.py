#!/usr/bin/env python3
"""
Visual test — logic/ package with live simulation.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Builds the dock_queue scene, wires the RuleEngine into the physics step,
then starts the simulation so forklifts move under FSM control.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 0: Build scene + slot markers
  EXPECT:
    - Warehouse loads, 4 forklifts spawned.
    - BLUE flat cubes at dock queue positions (south wall area).
    - YELLOW flat cubes at staging hold positions.
  PASS IF: Blue + yellow cubes visible, no import errors.
  FAIL SIGN: No cubes → QueueManager slot setup failed.

STEP 1: Simulation running — FSM drives forklifts
  EXPECT:
    - Forklifts start moving toward shelf area (pickup).
    - After a few seconds each forklift gets a pallet (orange cube
      appears above it) and heads toward staging / loading dock.
    - Console prints each FSM state transition as it fires.
    - Blue dock cube turns RED when a forklift claims that slot.
  PASS IF:
    - Forklifts visibly move and change direction over time.
    - Console shows "FL0: idle → pickup_at_shelves" then
      "FL0: pickup_at_shelves → move_to_staging" etc.
  FAIL SIGN:
    - Forklifts frozen → rule engine tick not connected to physics.
    - No state transitions printed → FSM conditions never true.
══════════════════════════════════════════════════════════════
"""

import asyncio
import importlib
import os
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"

# ── Output log ───────────────────────────────────────────────────────────────
_output_dir = os.path.join(_project_root, "tests", "output")
os.makedirs(_output_dir, exist_ok=True)
_log_path = os.path.join(_output_dir, "test_logic.log")

class _Tee:
    def __init__(self, stream, path):
        self._stream = stream
        self._file   = open(path, "w", buffering=1)
    def write(self, data):
        self._stream.write(data)
        self._file.write(data)
    def flush(self):
        self._stream.flush()
        self._file.flush()
    def __getattr__(self, name):
        return getattr(self._stream, name)

sys.stdout = _Tee(sys.stdout, _log_path)
sys.stderr = _Tee(sys.stderr, _log_path)
print(f"[test] logging to {_log_path}")

# ── sys.path / hot-reload ─────────────────────────────────────────────────────
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

SCENARIO = "dock_queue"
SEED     = 42

COL_DOCK_FREE    = (0.1, 0.3, 1.0)
COL_DOCK_CLAIMED = (1.0, 0.1, 0.1)
COL_STAGING      = (1.0, 0.85, 0.1)
COL_PALLET       = (1.0, 0.55, 0.0)


def _banner(title):
    print(f"\n{'═'*60}\n  {title}\n{'═'*60}")


def _flat_cube(stage, path, x, y, colour, w=0.8, h=0.12):
    UsdGeom.Xform.Define(stage, "/World/DEBUG")
    box = UsdGeom.Cube.Define(stage, path)
    box.AddTranslateOp().Set(Gf.Vec3d(x, y, h / 2.0 + 0.02))
    box.AddScaleOp().Set(Gf.Vec3d(w / 2, w / 2, h / 2))
    box.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
    return box


def _recolour(stage, path, colour):
    prim = stage.GetPrimAtPath(path)
    if prim.IsValid():
        UsdGeom.Gprim(prim).GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])


def _tall_marker(stage, path, x, y, colour):
    """1 m tall pole — visible above forklift cab."""
    UsdGeom.Xform.Define(stage, "/World/DEBUG")
    box = UsdGeom.Cube.Define(stage, path)
    box.AddTranslateOp().Set(Gf.Vec3d(x, y, 1.5))
    box.AddScaleOp().Set(Gf.Vec3d(0.3, 0.3, 0.5))
    box.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
    return box


async def _run():
    _banner("STEP 0: Build scene + slot markers")
    scenario = PRESETS[SCENARIO](seed=SEED)
    await scenario.build()
    stage = scenario.stage

    for _ in range(60):
        await ih.next_update()

    # ── Init logic stack ─────────────────────────────────────────────────────
    from warehouse_sim.models.loading_door import LoadingDoor
    from warehouse_sim.models.pallet       import Pallet, LOC_SHELVES
    from warehouse_sim.logic.queue_manager import QueueManager
    from warehouse_sim.logic.rule_engine   import RuleEngine
    from warehouse_sim.models.queue_slot   import SLOT_DOCK, SLOT_STAGING_HOLD

    scenario.shelf_map.init(stage)

    doors = [LoadingDoor(i, is_open=True) for i in range(len(C.GATE_OFFSETS))]
    pallets = [
        Pallet(pallet_id=i, prim_path=f"/World/TestPallets/pallet_{i}",
               location=LOC_SHELVES)
        for i in range(len(scenario.forklifts))
    ]

    queue_mgr  = QueueManager(scenario.shelf_map)
    rule_engine = RuleEngine(
        forklifts   = scenario.forklifts,
        doors       = doors,
        pallets     = pallets,
        area_mgr    = scenario.area_mgr,
        queue_mgr   = queue_mgr,
        shelf_map   = scenario.shelf_map,
        stage       = stage,
        assets_root = scenario.assets_root,
    )

    # Draw slot markers
    _dock_paths = {}
    for s in queue_mgr.slots_of_type(SLOT_DOCK):
        px, py = s.position
        path = f"/World/DEBUG/dock_{s.slot_id}"
        _flat_cube(stage, path, px, py, COL_DOCK_FREE)
        _dock_paths[s.slot_id] = path

    for s in queue_mgr.slots_of_type(SLOT_STAGING_HOLD):
        px, py = s.position
        _flat_cube(stage, f"/World/DEBUG/staging_{s.slot_id}", px, py, COL_STAGING)

    _pallet_markers = {}  # fl_id → prim path

    print("  [PASS] scene built, logic stack ready")
    print("  Starting simulation...")

    # ── Physics step callback ────────────────────────────────────────────────
    def _on_step(dt):
        # 1. Rule engine drives FSM transitions + waypoint assignment
        rule_engine.tick(dt)

        # 2. Forklifts execute movement
        for fl in scenario.forklifts:
            fl.update(dt, stage, scenario.shelf_map, scenario.forklifts)

        # 3. Area occupancy
        for fl in scenario.forklifts:
            scenario.area_mgr.update(fl.id, fl.pos[0], fl.pos[1], 0.0)

        # 4. Update pallet marker positions
        for fl in scenario.forklifts:
            if fl.load == C.LOAD_LOADED:
                mp = f"/World/DEBUG/pallet_fl{fl.id}"
                if mp not in _pallet_markers:
                    _tall_marker(stage, mp, fl.pos[0], fl.pos[1], COL_PALLET)
                    _pallet_markers[mp] = True
                else:
                    prim = stage.GetPrimAtPath(mp)
                    if prim.IsValid():
                        xf = UsdGeom.Xformable(prim)
                        ops = xf.GetOrderedXformOps()
                        if ops:
                            ops[0].Set(Gf.Vec3d(fl.pos[0], fl.pos[1], 1.5))
            else:
                mp = f"/World/DEBUG/pallet_fl{fl.id}"
                if mp in _pallet_markers:
                    prim = stage.GetPrimAtPath(mp)
                    if prim.IsValid():
                        UsdGeom.Imageable(prim).MakeInvisible()
                    del _pallet_markers[mp]

        # 5. Update dock slot colours
        for s in queue_mgr.slots_of_type(SLOT_DOCK):
            p = _dock_paths.get(s.slot_id)
            if p:
                _recolour(stage, p,
                          COL_DOCK_CLAIMED if not s.is_free else COL_DOCK_FREE)

    _banner("STEP 1: Simulation running")
    sub = ih.subscribe_physics_step(_on_step)
    ih.play_timeline()


async def _run_and_restore():
    try:
        await _run()
    finally:
        if isinstance(sys.stdout, _Tee):
            sys.stdout._file.close()
            sys.stdout = sys.stdout._stream
        if isinstance(sys.stderr, _Tee):
            sys.stderr._file.close()
            sys.stderr = sys.stderr._stream
        print(f"[test] log saved → {_log_path}")


asyncio.ensure_future(_run_and_restore())
