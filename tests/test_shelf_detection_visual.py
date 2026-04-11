#!/usr/bin/env python3
"""
Visual test — shelf detection debug.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Builds the scene, initialises ShelfMap, then renders:
  RED   flat boxes  — detected shelf / rack bounding rects
  CYAN  thin slabs  — detected aisle centre lines (full shelf Y span)
  GREEN small cubes — pickup points (aisle entrances, south end)

Use this to verify that ShelfMap correctly identifies the rack geometry
and aisle corridors before trusting forklift navigation.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 0: Build scene
  EXPECT: Warehouse USD loads, forklifts spawned, no simulation running.
  PASS IF: Scene settles, no errors in console.
  FAIL SIGN: Black screen or import errors.

STEP 1: Init ShelfMap + render debug geometry
  EXPECT:
    - Console prints either shelf prim names (keyword scan) OR lines like
      "decal RecRed ... cx=..." / "decal Stripe4m ... cx=..."
      (decal scan path), then "N rects, M aisles detected."
    - RED boxes cover each shelf block footprint — one wide rect per shelf
      row, NOT one per individual rack unit.
    - CYAN slabs run through the centre of each open aisle corridor.
    - GREEN cubes sit at the south entrance of each aisle (~2 m inside
      the shelf Y boundary).
  PASS IF:
    - Red boxes cover shelf blocks and do NOT overlap aisle corridors.
    - Cyan slabs are in open corridors between shelf blocks.
    - Console shows "decal scan complete: N rects, M aisles" with N≥2, M≥1
      (or keyword scan found matches directly).
  FAIL SIGN:
    - No red boxes + "no SM_FloorDecal_RecRed found" → prim name mismatch;
      inspect Stage window for actual decal names.
    - "boundary gaps all map to aisles" → AISLE_TOL too large or stripe
      decals are missing; check stripe prim names in Stage.
    - Red boxes inside aisle corridors → widen AISLE_TOL in shelves.py.
    - Cyan slabs overlap shelf block → aisle X derived incorrectly.
══════════════════════════════════════════════════════════════
"""

import asyncio
import importlib
import os
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"

# ── Output log file setup ────────────────────────────────────────────────────
_output_dir = os.path.join(_project_root, "tests", "output")
os.makedirs(_output_dir, exist_ok=True)
_log_path = os.path.join(_output_dir, "test_shelf_detection.log")

class _Tee:
    """Write to both the original stdout and a log file."""
    def __init__(self, stream, path):
        self._stream = stream
        self._file = open(path, "w", buffering=1)
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
# ── End log setup ─────────────────────────────────────────────────────────────

_bad_paths = []
for p in list(sys.path):
    try:
        if not p or p == _project_root:
            continue
        if os.path.isdir(os.path.join(p, "warehouse_sim")):
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

# Debug geometry colours
SHELF_RECT_COL  = (1.0, 0.15, 0.15)   # red  — shelf bounding rects
AISLE_COL       = (0.0, 0.85, 0.85)   # cyan — aisle centre lines
PICKUP_COL      = (0.1, 0.9, 0.1)     # green — pickup / entrance points
DEBUG_Z         = 0.08                 # height of floor-level indicators


def _banner(title):
    print(f"\n{'═'*60}\n  {title}\n{'═'*60}")


def _flat_box(stage, path, cx, cy, w, d, colour, z=DEBUG_Z, h=0.05):
    """Create a flat coloured box centred at (cx, cy, z)."""
    UsdGeom.Xform.Define(stage, "/World/DEBUG")
    box = UsdGeom.Cube.Define(stage, path)
    box.AddTranslateOp().Set(Gf.Vec3d(cx, cy, z + h / 2.0))
    box.AddScaleOp().Set(Gf.Vec3d(w / 2.0, d / 2.0, h / 2.0))
    box.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
    return box


def _small_cube(stage, path, x, y, colour, size=0.25):
    box = UsdGeom.Cube.Define(stage, path)
    box.AddTranslateOp().Set(Gf.Vec3d(x, y, DEBUG_Z + size / 2.0))
    box.AddScaleOp().Set(Gf.Vec3d(size, size, size))
    box.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
    return box


async def _run():
    # ── STEP 0: Build scene ──────────────────────────────────────────────────
    _banner("STEP 0: Build scene")
    scenario = PRESETS[SCENARIO](seed=SEED)
    await scenario.build()
    stage = scenario.stage

    # Wait for warehouse USD to fully load
    for _ in range(120):
        await ih.next_update()
    print("  [PASS] scene built")

    # ── STEP 0b: Diagnostic — find FloorDecal prims anywhere in the stage ──────
    _banner("STEP 0b: FloorDecal prim diagnostic")
    from pxr import Usd as _Usd
    _decal_count = 0
    for _p in _Usd.PrimRange(stage.GetPseudoRoot()):
        _n = _p.GetName()
        if "FloorDecal" in _n:
            print(f"  DECAL prim: {_p.GetPath()}  name={_n!r}")
            _decal_count += 1
    if _decal_count == 0:
        print("  *** NO FloorDecal prims found anywhere in stage ***")
    else:
        print(f"  Total FloorDecal prims found: {_decal_count}")

    # ── STEP 1: Init ShelfMap + render debug geometry ────────────────────────
    _banner("STEP 1: Init ShelfMap + render debug geometry")

    shelf_map = scenario.shelf_map
    shelf_map.init(stage)

    print(f"\n  Shelf rects found : {len(shelf_map.rects)}")
    print(f"  Aisle X coords    : {[round(x, 2) for x in shelf_map.aisle_xs]}")
    if shelf_map.area_y_min is not None:
        print(f"  Shelf Y range     : {shelf_map.area_y_min:.2f} → {shelf_map.area_y_max:.2f}")

    # RED boxes — one per detected shelf rect
    for i, (x0, x1, y0, y1) in enumerate(shelf_map.rects):
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        w  = x1 - x0
        d  = y1 - y0
        _flat_box(stage, f"/World/DEBUG/shelf_rect_{i}",
                  cx, cy, w, d, SHELF_RECT_COL, h=0.06)
        print(f"  RECT {i:2d}: x=({x0:.1f},{x1:.1f}) y=({y0:.1f},{y1:.1f}) "
              f"size=({w:.1f}×{d:.1f}m)")

    # CYAN slabs — one per aisle, running the full shelf Y span
    if shelf_map.area_y_min is not None:
        aisle_depth = shelf_map.area_y_max - shelf_map.area_y_min
        aisle_cy    = (shelf_map.area_y_min + shelf_map.area_y_max) / 2.0
        for j, ax in enumerate(shelf_map.aisle_xs):
            _flat_box(stage, f"/World/DEBUG/aisle_{j}",
                      ax, aisle_cy, 0.4, aisle_depth, AISLE_COL, h=0.04)
            print(f"  AISLE {j}: x={ax:.2f}")

    # GREEN cubes — pickup / entrance points at south end of each aisle
    from warehouse_sim import waypoints as wp
    pickup_pts = wp.get_pickup_points(shelf_map)
    for k, (px, py) in enumerate(pickup_pts):
        _small_cube(stage, f"/World/DEBUG/pickup_{k}", px, py, PICKUP_COL)
        print(f"  PICKUP {k}: ({px:.2f}, {py:.2f})")

    for _ in range(60):
        await ih.next_update()

    _banner("DONE — inspect viewport for red/cyan/green debug geometry")
    if not shelf_map.rects:
        print("  *** WARNING: 0 shelf rects detected — check SHELF_KEYWORDS "
              "or prim names in the Stage window ***")
    elif not shelf_map.aisle_xs:
        print("  *** WARNING: rects found but 0 aisles detected — "
              "shelf rects may be overlapping or too close together ***")
    else:
        print(f"  [PASS] {len(shelf_map.rects)} rects, "
              f"{len(shelf_map.aisle_xs)} aisles detected")


async def _run_and_restore():
    try:
        await _run()
    finally:
        # Restore original stdout/stderr so Script Editor console works normally
        if isinstance(sys.stdout, _Tee):
            sys.stdout._file.close()
            sys.stdout = sys.stdout._stream
        if isinstance(sys.stderr, _Tee):
            sys.stderr._file.close()
            sys.stderr = sys.stderr._stream
        print(f"[test] log saved → {_log_path}")

asyncio.ensure_future(_run_and_restore())
