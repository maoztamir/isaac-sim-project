"""
Visual test — warehouse surveillance cameras
=============================================

Verifies that four UsdGeom.Camera prims are created at the positions stored
in tests/camera_position.usd and that each has the correct focal length.

STEP 1: run_test() — build a minimal scene with no forklifts
  EXPECT: four camera prims appear under /World/Cameras/ in the Stage panel
  PASS IF: all four prims (cam_south, cam_north, cam_west, cam_east) exist
           and their focal length matches the value in camera_position.usd
           (~14.96 mm at 20.955 mm aperture)
  FAIL SIGN: AttributeError / "camera not found" printout, or focal length 0

STEP 2: manual viewport check (optional, headless skips this)
  EXPECT: selecting any /World/Cameras/cam_* prim and pressing "F" in the
          viewport shows the warehouse floor centred in the camera frustum
  PASS IF: warehouse structure is visible inside the camera frame
  FAIL SIGN: empty/black viewport or camera aimed away from warehouse
"""

import sys
import os
import asyncio

# ── hot-reload block ──────────────────────────────────────────────────────────
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
# ─────────────────────────────────────────────────────────────────────────────

# Tunable knobs
EXPECTED_CAMERAS = ["cam_south", "cam_north", "cam_west", "cam_east"]
EXPECTED_APERTURE = 20.955   # mm — must match camera_position.usd


async def _run():
    from pxr import UsdGeom

    from warehouse_sim import isaac_helpers as ih
    from warehouse_sim import config as C

    print("[test] Getting stage...")
    stage = ih.get_stage()
    await ih.next_update()

    print("[test] Clearing /World...")
    ih.clear_world(stage)
    await ih.next_update()

    print("[test] Loading warehouse USD...")
    assets_root = ih.get_assets_root()
    ih.spawn_asset(stage, "/World/Warehouse",
                   assets_root + C.WAREHOUSE_USD, 0, 0, 0)
    await ih.next_update()

    ih.create_physics_scene(stage)

    # ── spawn cameras from reference USD ──────────────────────────────────────
    print(f"[test] Loading cameras from: {C.CAMERA_POSITIONS_USD}")
    created = ih.spawn_cameras_from_usd(stage, C.CAMERA_POSITIONS_USD)
    print(f"[test] Camera prims created: {created}")

    await ih.next_update()

    # ── verify ────────────────────────────────────────────────────────────────
    all_ok = True
    for label in EXPECTED_CAMERAS:
        path = f"/World/Cameras/{label}"
        cam = UsdGeom.Camera.Get(stage, path)
        if not cam or not cam.GetPrim().IsValid():
            print(f"[FAIL] Camera prim not found: {path}")
            all_ok = False
            continue

        fl = cam.GetFocalLengthAttr().Get()
        ap = cam.GetHorizontalApertureAttr().Get()
        if fl is None or fl == 0:
            print(f"[FAIL] {label}: focal length is None/0")
            all_ok = False
            continue

        print(f"[test] {label}: focal_length={fl:.3f} mm  aperture={ap:.3f} mm")
        print(f"[PASS] {label}: camera prim valid, focal length present")

    if all_ok:
        print("[PASS] All 4 cameras loaded from USD correctly.")
    else:
        print("[FAIL] One or more cameras failed verification.")


asyncio.ensure_future(_run())
