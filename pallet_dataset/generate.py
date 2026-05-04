"""
Pallet synthetic dataset generator.

Run inside Isaac Sim Script Editor:  Window > Script Editor > Open > Ctrl+Enter

Output layout
-------------
OUTPUT_DIR/
  cam_0/  rgb/000000.png  labels/000000.txt
  cam_1/  ...
  cam_2/  ...
  cam_3/  ...
  classes.txt        ← ["pallet"] or ["pallet", "forklift"]
  dataset_info.json  ← run statistics and config snapshot

Labels use YOLO format:  class_id  cx  cy  w  h  (all values 0-1 normalised)
  class 0 = pallet
  class 1 = forklift
  class 2 = box

Per-frame quality filters applied before saving:
  - brightness check on rendered image
  - tiny / huge / heavily-clipped bounding boxes rejected
  - frames with 0 or >MAX_OBJECTS_PER_IMAGE annotations discarded
"""

import os
import sys
import math

# ── Hot-reload block ──────────────────────────────────────────────────────────
_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"
_dataset_dir  = os.path.join(_project_root, "pallet_dataset")

for _bad in list(sys.path):
    try:
        if _bad and _bad != _project_root and os.path.isdir(os.path.join(_bad, "warehouse_sim")):
            while _bad in sys.path:
                sys.path.remove(_bad)
    except Exception:
        pass

if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

for _k in [k for k in sys.modules if k.startswith("warehouse_sim") or k == "config"]:
    del sys.modules[_k]

import importlib, glob as _glob
for _pyc in _glob.glob(os.path.join(_project_root, "warehouse_sim", "**", "*.pyc"),
                       recursive=True):
    try: os.remove(_pyc)
    except OSError: pass
importlib.invalidate_caches()

# ── Imports ───────────────────────────────────────────────────────────────────
import asyncio
import json
import random
import time

import numpy as np
from PIL import Image
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics

# Load pallet_dataset/config.py by direct exec — spec_from_file_location can
# return a partially-initialised module under Isaac Sim's embedded Python when
# cv2's import hooks are active; explicit open+exec is immune to all sys.path
# interference because it never goes through the import machinery at all.
import types as _types
C = _types.ModuleType("pallet_dataset_config")
C.__file__ = os.path.join(_dataset_dir, "config.py")
with open(C.__file__) as _f:
    exec(compile(_f.read(), C.__file__, "exec"), C.__dict__)

import omni.kit.app
import omni.replicator.core as rep

from isaacsim.core.utils.stage import get_current_stage
from isaacsim.storage.native import get_assets_root_path

# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_update():
    return omni.kit.app.get_app().next_update_async()


def _ensure_dirs(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _set_prim_pose(prim, x, y, yaw_deg, scale):
    """Set translate, rotateZ, and uniform scale on an Xform prim."""
    xf  = UsdGeom.Xformable(prim)
    ops = {op.GetOpName(): op for op in xf.GetOrderedXformOps()}

    def _get_or_add(name, add_fn):
        return ops[name] if name in ops else add_fn()

    t_op = _get_or_add("xformOp:translate", lambda: xf.AddTranslateOp())
    r_op = _get_or_add("xformOp:rotateZ",   lambda: xf.AddRotateZOp())
    s_op = _get_or_add("xformOp:scale",     lambda: xf.AddScaleOp())

    t_op.Set(Gf.Vec3d(x, y, 0.0))
    r_op.Set(float(yaw_deg))
    s_op.Set(Gf.Vec3d(scale, scale, scale))


def _set_visibility(prim, visible):
    img = UsdGeom.Imageable(prim)
    if visible:
        img.MakeVisible()
    else:
        img.MakeInvisible()


def _set_semantic(prim, label):
    try:
        from isaacsim.core.utils.semantics import add_update_semantics
        add_update_semantics(prim, label, "class")
    except Exception:
        if not prim.HasAttribute("semanticLabel"):
            prim.CreateAttribute("semanticLabel", Sdf.ValueTypeNames.String)
        prim.GetAttribute("semanticLabel").Set(label)


def _update_camera(cam_prim, eye_xyz, target_xyz, focal_mm):
    """Update an existing camera prim's look-at transform and focal length.

    Uses the same look-at math as spawn_camera() but writes to the existing
    xformOp:transform attribute rather than calling AddTransformOp again.
    """
    eye    = Gf.Vec3d(*eye_xyz)
    target = Gf.Vec3d(*target_xyz)
    fwd    = target - eye
    fwd_len = fwd.GetLength()
    if fwd_len < 1e-10:
        return
    fwd = fwd / fwd_len

    world_up = Gf.Vec3d(0, 0, 1)
    right = Gf.Vec3d(
        fwd[1]*world_up[2] - fwd[2]*world_up[1],
        fwd[2]*world_up[0] - fwd[0]*world_up[2],
        fwd[0]*world_up[1] - fwd[1]*world_up[0],
    )
    if right.GetLength() < 1e-6:
        world_up = Gf.Vec3d(0, 1, 0)
        right = Gf.Vec3d(
            fwd[1]*world_up[2] - fwd[2]*world_up[1],
            fwd[2]*world_up[0] - fwd[0]*world_up[2],
            fwd[0]*world_up[1] - fwd[1]*world_up[0],
        )
    right = right / right.GetLength()
    up = Gf.Vec3d(
        right[1]*fwd[2] - right[2]*fwd[1],
        right[2]*fwd[0] - right[0]*fwd[2],
        right[0]*fwd[1] - right[1]*fwd[0],
    )

    mat = Gf.Matrix4d(
        (right[0],  right[1],  right[2],  0.0),
        (up[0],     up[1],     up[2],     0.0),
        (-fwd[0],  -fwd[1],  -fwd[2],     0.0),
        (eye[0],    eye[1],    eye[2],    1.0),
    )

    xf = UsdGeom.Xformable(cam_prim)
    for op in xf.GetOrderedXformOps():
        if "transform" in op.GetOpName():
            op.Set(mat)
            break

    fl_attr = cam_prim.GetAttribute("focalLength")
    if fl_attr:
        fl_attr.Set(float(focal_mm))


def _random_camera_pose(rng, cx, cy):
    """Return (eye, target, focal_mm) for a realistic CCTV-style viewpoint.

    The camera is placed at a random height (1.5–4 m), horizontal distance
    (3–10 m) and azimuth around the pallet cluster centre (cx, cy).
    focal_mm is a 35 mm-equivalent focal length (24–50 mm).
    """
    height   = rng.uniform(C.CAM_HEIGHT_MIN, C.CAM_HEIGHT_MAX)
    distance = rng.uniform(C.CAM_DIST_MIN,   C.CAM_DIST_MAX)
    azimuth  = rng.uniform(0.0, 2.0 * math.pi)
    focal_mm = rng.uniform(C.FOCAL_MM_MIN,   C.FOCAL_MM_MAX)

    ex = cx + distance * math.cos(azimuth)
    ey = cy + distance * math.sin(azimuth)
    return (ex, ey, height), (cx, cy, 0.1), focal_mm


def _place_with_spacing(rng, n, cx, cy, radius, min_sep):
    """Return up to *n* (x, y, yaw_deg) poses within *radius* of (cx, cy).

    Uses a simple rejection sampler (up to 20 attempts per slot).  Positions
    are clamped to the warehouse floor bounds.  Fewer than *n* poses may be
    returned if spacing cannot be satisfied.
    """
    placed = []
    for _ in range(n):
        for _ in range(20):
            r     = radius * math.sqrt(rng.random())
            theta = rng.uniform(0.0, 2.0 * math.pi)
            x = max(C.FLOOR_X_MIN, min(C.FLOOR_X_MAX, cx + r * math.cos(theta)))
            y = max(C.FLOOR_Y_MIN, min(C.FLOOR_Y_MAX, cy + r * math.sin(theta)))
            if all(math.hypot(x - px, y - py) >= min_sep for px, py, _ in placed):
                placed.append((x, y, rng.uniform(0.0, 360.0)))
                break
    return placed


def _check_brightness(arr):
    """Return True if the image mean pixel value is within the configured range."""
    if arr is None or arr.size == 0:
        return False
    mean = float(arr[:, :, :3].mean())
    return C.BRIGHTNESS_MIN <= mean <= C.BRIGHTNESS_MAX


def _save_rgb(arr, path):
    if arr is None or arr.size == 0:
        return
    Image.fromarray(arr[:, :, :3], "RGB").save(path)


def _save_yolo(bbox_data, img_w, img_h, path):
    """Write a YOLO label file after applying all quality filters.

    Returns the number of annotations written.
    Returns 0 (without writing) if the frame should be discarded entirely
    (zero valid annotations, or annotation count exceeds MAX_OBJECTS_PER_IMAGE).
    """
    if not isinstance(bbox_data, dict):
        return 0
    data   = bbox_data.get("data")
    labels = (bbox_data.get("info") or {}).get("idToLabels", {})

    lines = []
    if data is not None and len(data) > 0:
        for row in data:
            sem_id  = int(row["semanticId"])
            sem_lbl = labels.get(str(sem_id), {}).get("class", "")
            if sem_lbl == "pallet":
                class_id = 0
            elif sem_lbl == "forklift":
                class_id = 1
            elif sem_lbl == "box":
                class_id = 2
            else:
                continue

            x_min = float(row["x_min"])
            y_min = float(row["y_min"])
            x_max = float(row["x_max"])
            y_max = float(row["y_max"])

            if x_max <= x_min or y_max <= y_min:
                continue
            if x_max < 0 or y_max < 0 or x_min >= img_w or y_min >= img_h:
                continue

            # Reject heavily clipped boxes (visible area < MIN_VISIBLE_FRACTION)
            raw_area = (x_max - x_min) * (y_max - y_min)
            cx_min   = max(0.0, x_min)
            cy_min   = max(0.0, y_min)
            cx_max   = min(float(img_w), x_max)
            cy_max   = min(float(img_h), y_max)
            vis_area = max(0.0, cx_max - cx_min) * max(0.0, cy_max - cy_min)
            if raw_area > 0 and vis_area / raw_area < C.MIN_VISIBLE_FRACTION:
                continue

            # Normalise using the clamped (visible) box
            cx_n = ((cx_min + cx_max) / 2.0) / img_w
            cy_n = ((cy_min + cy_max) / 2.0) / img_h
            bw   = (cx_max - cx_min) / img_w
            bh   = (cy_max - cy_min) / img_h

            if bw < C.MIN_BOX_SIZE or bh < C.MIN_BOX_SIZE:
                continue
            if bw > C.MAX_BOX_SIZE or bh > C.MAX_BOX_SIZE:
                continue

            lines.append(f"{class_id} {cx_n:.6f} {cy_n:.6f} {bw:.6f} {bh:.6f}")

    count = len(lines)
    if count == 0 or count > C.MAX_OBJECTS_PER_IMAGE:
        return 0

    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    return count


# ── Main generation coroutine ─────────────────────────────────────────────────

async def _run():
    rng   = random.Random(C.SEED)
    stage = get_current_stage()
    await _next_update()

    assets_root = get_assets_root_path()
    print(f"[pallet_dataset] assets_root     = {assets_root}")
    print(f"[pallet_dataset] pallet pool     = {len(C.ALL_PALLET_ASSETS)}")
    print(f"[pallet_dataset] forklift pool   = {len(C.FORKLIFT_ASSETS)}")
    print(f"[pallet_dataset] box pool        = {len(C.ALL_BOX_ASSETS)}")

    if not C.ALL_PALLET_ASSETS:
        raise RuntimeError(
            "[pallet_dataset] No pallet assets found — "
            "check LOCAL_5_1 / LOCAL_5_0 paths in config.py"
        )

    # Cap each asset pool to ASSET_POOL_SIZE unique entries chosen once at
    # startup.  Every unique asset loaded stays resident in the RTX mesh/texture
    # cache for the whole run; cycling all 60+ pallets exhausts VRAM.
    _pool_cap = C.ASSET_POOL_SIZE
    if _pool_cap and len(C.ALL_PALLET_ASSETS) > _pool_cap:
        pallet_pool = rng.sample(C.ALL_PALLET_ASSETS, _pool_cap)
        print(f"[pallet_dataset] pallet pool capped to {_pool_cap} / {len(C.ALL_PALLET_ASSETS)}")
    else:
        pallet_pool = list(C.ALL_PALLET_ASSETS)
    forklift_pool = list(C.FORKLIFT_ASSETS)
    box_pool      = list(C.ALL_BOX_ASSETS)

    # ── Clear stage and load warehouse background ─────────────────────────────
    import omni.kit.commands
    omni.kit.commands.execute("DeletePrimsCommand", paths=["/World"])
    await _next_update()

    UsdGeom.Xform.Define(stage, "/World")

    # Physics scene with inflated GPU broadphase capacity.
    # Defaults are 1024 each; swapping many collision-enabled USD assets every
    # frame (60+ pallet types + forklifts) overflows them and fills the log.
    _ps = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    _ps.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
    _ps.CreateGravityMagnitudeAttr(9.81)
    _pa = PhysxSchema.PhysxSceneAPI.Apply(_ps.GetPrim())
    _pa.CreateGpuFoundLostAggregatePairsCapacityAttr(8192)
    _pa.CreateGpuTotalAggregatePairsCapacityAttr(8192)

    warehouse_url = assets_root + "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd"
    wh = UsdGeom.Xform.Define(stage, "/World/Warehouse")
    wh.GetPrim().GetReferences().AddReference(warehouse_url)
    await _next_update()
    await _next_update()

    # ── Loading / staging zone markings (zebra tape, same as live scenarios) ────
    from warehouse_sim import config as WC
    from warehouse_sim.isaac_helpers import (
        spawn_zebra_rect, spawn_camera, spawn_gate, open_gate, close_gate,
    )
    UsdGeom.Xform.Define(stage, "/World/LoadingAreas")
    for _i, _off in enumerate(WC.GATE_OFFSETS):
        spawn_zebra_rect(
            stage, f"/World/LoadingAreas/zone_{_i}",
            WC.WAREHOUSE_CX + _off,
            WC.WALL_Y_MIN + WC.LOAD_D / 2.0,
            WC.LOAD_W, WC.LOAD_D, WC,
        )
    UsdGeom.Xform.Define(stage, "/World/StagingAreas")
    for _i, _off in enumerate(WC.GATE_OFFSETS):
        spawn_zebra_rect(
            stage, f"/World/StagingAreas/zone_{_i}",
            WC.WAREHOUSE_CX + _off,
            WC.STAGING_CENTER_Y,
            WC.STAGING_W, WC.STAGING_D, WC,
        )
    print("[pallet_dataset] Zone markings spawned (loading + staging).")

    # ── Dock gates (3 on south wall, same as live scenarios) ─────────────────
    UsdGeom.Xform.Define(stage, "/World/DockingDoors")
    for _i, _off in enumerate(WC.GATE_OFFSETS):
        spawn_gate(stage, _i, WC.WAREHOUSE_CX + _off, WC)
    print("[pallet_dataset] 3 dock gates spawned.")
    await _next_update()

    # ── Create N_CAMERAS cameras at realistic heights ─────────────────────────
    # spawn_camera() builds look-at matrix and sets xformOp:transform once.
    # Per-frame updates go via _update_camera(), which overwrites that value
    # without calling AddTransformOp again.
    UsdGeom.Xform.Define(stage, "/World/DatasetCameras")
    cam_paths = []
    cam_prims = []
    for i in range(C.N_CAMERAS):
        path = f"/World/DatasetCameras/cam_{i}"
        cam  = spawn_camera(
            stage, path,
            eye    = (0.0, -5.0 * (i + 1), 3.0),
            target = (0.0, 0.0, 0.0),
            fov_deg = 60.0,
        )
        # Override to standard 35 mm sensor width so focal_mm is interpretable
        cam.GetPrim().GetAttribute("horizontalAperture").Set(C.CAM_SENSOR_WIDTH_MM)
        cam_paths.append(path)
        cam_prims.append(cam.GetPrim())

    # Give RTX renderer time to register the new Camera prims
    for _ in range(5):
        await _next_update()

    # ── Replicator render products and annotators ─────────────────────────────
    W, H = C.RESOLUTION
    rps, rgb_anns, bbox_anns = [], [], []
    for path in cam_paths:
        rp       = rep.create.render_product(path, (W, H))
        rgb_ann  = rep.AnnotatorRegistry.get_annotator("rgb")
        bbox_ann = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
        rgb_ann.attach([rp])
        bbox_ann.attach([rp])
        rps.append(rp)
        rgb_anns.append(rgb_ann)
        bbox_anns.append(bbox_ann)

    await _next_update()

    # ── Pre-allocate pallet slots (reference swapped each frame) ──────────────
    UsdGeom.Xform.Define(stage, "/World/DatasetPallets")
    slot_prims = []
    for i in range(C.MAX_PALLETS):
        xf = UsdGeom.Xform.Define(stage, f"/World/DatasetPallets/slot_{i}")
        UsdGeom.Imageable(xf.GetPrim()).MakeInvisible()
        slot_prims.append(xf.GetPrim())

    # ── Pre-allocate forklift slots — reference assigned ONCE at startup ────────
    # Per-frame we only update pose + visibility; no SetReferences() per frame.
    # This prevents the GPU from having to reload articulated robot meshes every
    # frame, which was the primary cause of "can't free GPU space" errors.
    UsdGeom.Xform.Define(stage, "/World/DatasetForklifts")
    fl_prims  = []
    fl_scales = []
    for _i in range(C.N_FORKLIFT_SLOTS):
        _fl_xf = UsdGeom.Xform.Define(stage, f"/World/DatasetForklifts/forklift_{_i}")
        _fl_p  = _fl_xf.GetPrim()
        if forklift_pool:
            _fl_asset, _fl_scale = forklift_pool[_i % len(forklift_pool)]
            _fl_p.GetReferences().SetReferences([Sdf.Reference(_fl_asset)])
            _set_semantic(_fl_p, "forklift")
        else:
            _fl_scale = 1.0
        UsdGeom.Imageable(_fl_p).MakeInvisible()
        fl_prims.append(_fl_p)
        fl_scales.append(_fl_scale)

    # ── Pre-allocate box slots — reference assigned ONCE at startup ───────────
    UsdGeom.Xform.Define(stage, "/World/DatasetBoxes")
    box_prims  = []
    box_scales = []
    for _i in range(C.N_BOX_SLOTS):
        _bx_xf = UsdGeom.Xform.Define(stage, f"/World/DatasetBoxes/box_{_i}")
        _bx_p  = _bx_xf.GetPrim()
        if box_pool:
            _bx_asset, _bx_scale = box_pool[_i % len(box_pool)]
            _bx_p.GetReferences().SetReferences([Sdf.Reference(_bx_asset)])
            _set_semantic(_bx_p, "box")
        else:
            _bx_scale = 1.0
        UsdGeom.Imageable(_bx_p).MakeInvisible()
        box_prims.append(_bx_p)
        box_scales.append(_bx_scale)

    await _next_update()

    # ── Output directories ────────────────────────────────────────────────────
    cam_names = [f"cam_{i}" for i in range(C.N_CAMERAS)]
    for name in cam_names:
        _ensure_dirs(
            os.path.join(C.OUTPUT_DIR, name, "rgb"),
            os.path.join(C.OUTPUT_DIR, name, "labels"),
        )

    classes = ["pallet"]
    if C.FORKLIFT_ASSETS:
        classes.append("forklift")
    if C.ALL_BOX_ASSETS:
        classes.append("box")
    with open(os.path.join(C.OUTPUT_DIR, "classes.txt"), "w") as fh:
        fh.write("\n".join(classes) + "\n")

    info = {
        "num_frames":         C.NUM_FRAMES,
        "resolution":         list(C.RESOLUTION),
        "min_pallets":        C.MIN_PALLETS,
        "max_pallets":        C.MAX_PALLETS,
        "forklift_scene_prob": C.FORKLIFT_SCENE_PROB,
        "gate_open_prob":     C.GATE_OPEN_PROB,
        "num_pallet_types":   len(C.ALL_PALLET_ASSETS),
        "num_forklift_types": len(C.FORKLIFT_ASSETS),
        "num_box_types":      len(C.ALL_BOX_ASSETS),
        "classes":            classes,
        "cameras":            cam_names,
        "seed":               C.SEED,
    }

    # ── Generation loop ───────────────────────────────────────────────────────
    print(f"[pallet_dataset] Starting: {C.NUM_FRAMES} frames × {C.N_CAMERAS} cameras")
    t0              = time.time()
    images_saved    = 0
    frames_with_any = 0

    for frame_idx in range(C.NUM_FRAMES):

        # Cluster centre — all pallets and cameras reference this point
        cx = rng.uniform(C.CLUSTER_X_MIN, C.CLUSTER_X_MAX)
        cy = rng.uniform(C.CLUSTER_Y_MIN, C.CLUSTER_Y_MAX)

        # Reposition each camera to a new random viewpoint of this cluster
        for cam_prim in cam_prims:
            eye, target, focal_mm = _random_camera_pose(rng, cx, cy)
            _update_camera(cam_prim, eye, target, focal_mm)

        # Place 2–5 pallets with minimum separation enforced
        n_active = rng.randint(C.MIN_PALLETS, C.MAX_PALLETS)
        poses    = _place_with_spacing(
            rng, n_active, cx, cy, C.SCATTER_RADIUS, C.MIN_PALLET_SEPARATION
        )

        for i, slot_prim in enumerate(slot_prims):
            if i < len(poses):
                asset_path, scale = rng.choice(pallet_pool)
                x, y, yaw = poses[i]
                slot_prim.GetReferences().SetReferences([Sdf.Reference(asset_path)])
                _set_prim_pose(slot_prim, x, y, yaw, scale)
                _set_semantic(slot_prim, "pallet")
                _set_visibility(slot_prim, True)
            else:
                slot_prim.GetReferences().ClearReferences()
                _set_visibility(slot_prim, False)

        # Randomise dock gate states (open / closed)
        for _gi in range(len(WC.GATE_OFFSETS)):
            if rng.random() < C.GATE_OPEN_PROB:
                open_gate(stage, _gi, WC.PANEL_N)
            else:
                close_gate(stage, _gi, WC.PANEL_N)

        # Place 0–N_FORKLIFT_SLOTS forklifts (pose + visibility only; ref fixed at startup)
        n_forklifts = 0
        if forklift_pool and rng.random() < C.FORKLIFT_SCENE_PROB:
            n_forklifts = rng.randint(1, C.N_FORKLIFT_SLOTS)
        for _fi, (fl_prim, fl_scale) in enumerate(zip(fl_prims, fl_scales)):
            if _fi < n_forklifts:
                fl_x = rng.uniform(WC.NAV_X_MIN, WC.NAV_X_MAX)
                fl_y = rng.uniform(WC.NAV_Y_MIN, WC.NAV_Y_MAX)
                _set_prim_pose(fl_prim, fl_x, fl_y, rng.uniform(0.0, 360.0), fl_scale)
                _set_visibility(fl_prim, True)
            else:
                _set_visibility(fl_prim, False)

        # Place 0–MAX_BOXES cardboard boxes (pose + visibility only; ref fixed at startup)
        n_boxes = rng.randint(C.MIN_BOXES, C.MAX_BOXES) if box_pool else 0
        for _bi, (box_prim, bx_scale) in enumerate(zip(box_prims, box_scales)):
            if _bi < n_boxes:
                bx_x = rng.uniform(C.BOX_X_MIN, C.BOX_X_MAX)
                bx_y = rng.uniform(C.BOX_Y_MIN, C.BOX_Y_MAX)
                _set_prim_pose(box_prim, bx_x, bx_y, rng.uniform(0.0, 360.0), bx_scale)
                _set_visibility(box_prim, True)
            else:
                _set_visibility(box_prim, False)

        # Let RTX flush pallet reference-swap changes before rendering
        await _next_update()

        # Render
        await rep.orchestrator.step_async(rt_subframes=C.RT_SUBFRAMES)

        # Capture → filter → save per camera
        fname        = f"{frame_idx:06d}"
        frame_saved  = 0

        for cam_name, rgb_ann, bbox_ann in zip(cam_names, rgb_anns, bbox_anns):
            rgb_data  = rgb_ann.get_data()
            bbox_data = bbox_ann.get_data()

            # Extract numpy array regardless of Replicator API version
            arr = (rgb_data
                   if isinstance(rgb_data, np.ndarray)
                   else (rgb_data.get("data") if isinstance(rgb_data, dict) else None))

            if not _check_brightness(arr):
                continue

            lbl_path = os.path.join(C.OUTPUT_DIR, cam_name, "labels", f"{fname}.txt")
            count    = _save_yolo(bbox_data, W, H, lbl_path)
            if count == 0:
                if os.path.exists(lbl_path):
                    os.remove(lbl_path)
                continue

            _save_rgb(arr, os.path.join(C.OUTPUT_DIR, cam_name, "rgb", f"{fname}.png"))
            frame_saved  += 1
            images_saved += 1

        if frame_saved > 0:
            frames_with_any += 1

        if (frame_idx + 1) % 50 == 0 or frame_idx == 0:
            elapsed = time.time() - t0
            fps     = (frame_idx + 1) / elapsed
            remain  = (C.NUM_FRAMES - frame_idx - 1) / max(fps, 1e-6)
            print(
                f"[pallet_dataset] frame {frame_idx+1:4d}/{C.NUM_FRAMES}"
                f"  pallets={len(poses)}"
                f"  forklifts={n_forklifts}"
                f"  boxes={n_boxes}"
                f"  saved={frame_saved}/{C.N_CAMERAS}"
                f"  {fps:.1f} fps  ETA {remain/60:.1f} min"
            )

    # ── Finalise ──────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    info.update({
        "total_seconds":      round(elapsed, 1),
        "frames_attempted":   C.NUM_FRAMES,
        "frames_with_images": frames_with_any,
        "images_saved":       images_saved,
    })
    with open(os.path.join(C.OUTPUT_DIR, "dataset_info.json"), "w") as fh:
        json.dump(info, fh, indent=2)

    print(
        f"[pallet_dataset] Done — {images_saved} images saved"
        f" ({frames_with_any}/{C.NUM_FRAMES} frames had ≥1 valid camera)"
        f"  →  {C.OUTPUT_DIR}"
    )


asyncio.ensure_future(_run())
