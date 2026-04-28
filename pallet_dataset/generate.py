"""
Pallet synthetic dataset generator.

Run inside Isaac Sim Script Editor:  Window > Script Editor > Open > Ctrl+Enter

Output layout
-------------
OUTPUT_DIR/
  cam_south/  rgb/000000.png  labels/000000.txt
  cam_north/  rgb/...         labels/...
  cam_west/   ...
  cam_east/   ...
  classes.txt                           ← ["pallet"]
  dataset_info.json                     ← frame count, asset count, config snapshot

Labels use YOLO format:  class_id  cx  cy  w  h  (all values 0-1 normalised)

Asset pool
----------
~80 pallet variants from three Isaac Sim asset families:
  - Simple Warehouse props  (scale 1.0 m)
  - Isaac Props / ArchVis   (scale 1.0 m / 0.01 cm)
  - NVIDIA DigitalTwin      (scale 0.01 cm) — Wood, Plastic, Metal
Missing files are silently skipped so the script works if only a subset is cached.
"""

import os
import sys

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

if _dataset_dir not in sys.path:
    sys.path.insert(1, _dataset_dir)

for _k in [k for k in sys.modules if k.startswith("warehouse_sim") or k == "config"]:
    del sys.modules[_k]

import importlib, glob as _glob
for _pyc in _glob.glob(os.path.join(_project_root, "warehouse_sim", "**", "*.pyc"), recursive=True):
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
from pxr import Gf, Sdf, Usd, UsdGeom

import omni.kit.app
import omni.replicator.core as rep

from isaacsim.core.utils.stage import get_current_stage
from isaacsim.storage.native import get_assets_root_path

import config as C

# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_update():
    return omni.kit.app.get_app().next_update_async()


def _ensure_dirs(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _set_prim_pose(prim, x, y, yaw_deg, scale):
    """Set translate, rotateZ, and uniform scale on an Xform prim."""
    xf = UsdGeom.Xformable(prim)
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


def _set_semantic(prim, label="pallet"):
    """Apply a class semantic label so the bbox annotator can identify pallets."""
    try:
        from isaacsim.core.utils.semantics import add_update_semantics
        add_update_semantics(prim, label, "class")
    except Exception:
        # Fallback: set via USD custom attribute (older Isaac Sim versions)
        if not prim.HasAttribute("semanticLabel"):
            prim.CreateAttribute("semanticLabel", Sdf.ValueTypeNames.String)
        prim.GetAttribute("semanticLabel").Set(label)


def _save_rgb(rgb_data, path):
    arr = rgb_data.get("data")
    if arr is None:
        return
    # RGBA uint8 (H, W, 4) → RGB PNG
    img = Image.fromarray(arr[:, :, :3], "RGB")
    img.save(path)


def _save_yolo(bbox_data, img_w, img_h, path, class_id=0):
    """Write YOLO label file from bounding_box_2d_tight annotator data."""
    data   = bbox_data.get("data")
    labels = (bbox_data.get("info") or {}).get("idToLabels", {})

    lines = []
    if data is not None and len(data) > 0:
        for row in data:
            # Check semantic label matches "pallet"
            sem_id  = int(row["semanticId"])
            sem_lbl = labels.get(str(sem_id), {}).get("class", "")
            if sem_lbl != "pallet":
                continue

            x_min = float(row["x_min"])
            y_min = float(row["y_min"])
            x_max = float(row["x_max"])
            y_max = float(row["y_max"])

            # Skip degenerate boxes
            if x_max <= x_min or y_max <= y_min:
                continue
            # Skip fully off-screen
            if x_max < 0 or y_max < 0 or x_min >= img_w or y_min >= img_h:
                continue

            cx = ((x_min + x_max) / 2.0) / img_w
            cy = ((y_min + y_max) / 2.0) / img_h
            bw = (x_max - x_min) / img_w
            bh = (y_max - y_min) / img_h

            lines.append(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

    with open(path, "w") as fh:
        fh.write("\n".join(lines))


# ── Main generation coroutine ─────────────────────────────────────────────────

async def _run():
    rng   = random.Random(C.SEED)
    stage = get_current_stage()
    await _next_update()

    assets_root = get_assets_root_path()
    print(f"[pallet_dataset] assets_root = {assets_root}")
    print(f"[pallet_dataset] asset pool  = {len(C.ALL_PALLET_ASSETS)} pallets")

    # ── Clear and load warehouse background ──────────────────────────────────
    import omni.kit.commands
    omni.kit.commands.execute("DeletePrimsCommand", paths=["/World"])
    await _next_update()

    from pxr import UsdPhysics
    UsdGeom.Xform.Define(stage, "/World")
    from isaacsim.core.utils.stage import open_stage
    warehouse_url = assets_root + "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd"
    wh = UsdGeom.Xform.Define(stage, "/World/Warehouse")
    wh.GetPrim().GetReferences().AddReference(warehouse_url)
    await _next_update()
    await _next_update()

    # ── Load cameras from reference USD ──────────────────────────────────────
    from warehouse_sim import config as WC
    cam_usd = WC.CAMERA_POSITIONS_USD
    cam_holder = UsdGeom.Xform.Define(stage, "/World/Cameras")
    cam_holder.GetPrim().GetReferences().AddReference(cam_usd)
    await _next_update()

    CAM_PATHS = [
        "/World/Cameras/cam_south",
        "/World/Cameras/cam_north",
        "/World/Cameras/cam_west",
        "/World/Cameras/cam_east",
    ]
    CAM_NAMES = ["cam_south", "cam_north", "cam_west", "cam_east"]

    # ── Create pallet slot prims ──────────────────────────────────────────────
    # One Xform slot per potential pallet (MAX_PALLETS total).
    # Each frame we swap the reference and pose of active slots,
    # and hide inactive ones.
    pallet_root = UsdGeom.Xform.Define(stage, "/World/DatasetPallets")
    slot_prims = []
    for i in range(C.MAX_PALLETS):
        slot_path = f"/World/DatasetPallets/slot_{i}"
        xf = UsdGeom.Xform.Define(stage, slot_path)
        # Start hidden — will be shown and positioned per frame
        UsdGeom.Imageable(xf.GetPrim()).MakeInvisible()
        slot_prims.append(xf.GetPrim())
    await _next_update()

    # ── Replicator render products and annotators ─────────────────────────────
    W, H = C.RESOLUTION
    rps, rgb_anns, bbox_anns = [], [], []
    for cam_path in CAM_PATHS:
        rp = rep.create.render_product(cam_path, (W, H))
        rgb_ann  = rep.AnnotatorRegistry.get_annotator("rgb")
        bbox_ann = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
        rgb_ann.attach([rp])
        bbox_ann.attach([rp])
        rps.append(rp)
        rgb_anns.append(rgb_ann)
        bbox_anns.append(bbox_ann)

    await _next_update()

    # ── Output directories ────────────────────────────────────────────────────
    for name in CAM_NAMES:
        _ensure_dirs(
            os.path.join(C.OUTPUT_DIR, name, "rgb"),
            os.path.join(C.OUTPUT_DIR, name, "labels"),
        )

    with open(os.path.join(C.OUTPUT_DIR, "classes.txt"), "w") as fh:
        fh.write("pallet\n")

    # ── Dataset info (written at end) ─────────────────────────────────────────
    info = {
        "num_frames":       C.NUM_FRAMES,
        "resolution":       list(C.RESOLUTION),
        "min_pallets":      C.MIN_PALLETS,
        "max_pallets":      C.MAX_PALLETS,
        "num_asset_types":  len(C.ALL_PALLET_ASSETS),
        "cameras":          CAM_NAMES,
        "seed":             C.SEED,
        "asset_paths":      [p for p, _ in C.ALL_PALLET_ASSETS],
    }

    # ── Generation loop ───────────────────────────────────────────────────────
    print(f"[pallet_dataset] Starting generation: {C.NUM_FRAMES} frames × {len(CAM_NAMES)} cameras")
    t0 = time.time()

    for frame_idx in range(C.NUM_FRAMES):
        # --- Randomise active pallets ----------------------------------------
        n_active = rng.randint(C.MIN_PALLETS, C.MAX_PALLETS)
        chosen   = rng.choices(C.ALL_PALLET_ASSETS, k=n_active)

        for i, slot_prim in enumerate(slot_prims):
            if i < n_active:
                asset_path, scale = chosen[i]
                x   = rng.uniform(C.SCATTER_X_MIN, C.SCATTER_X_MAX)
                y   = rng.uniform(C.SCATTER_Y_MIN, C.SCATTER_Y_MAX)
                yaw = rng.uniform(0.0, 360.0)

                # Swap reference to chosen asset
                slot_prim.GetReferences().SetReferences(
                    [Sdf.Reference(asset_path)]
                )
                _set_prim_pose(slot_prim, x, y, yaw, scale)
                _set_semantic(slot_prim, "pallet")
                _set_visibility(slot_prim, True)
            else:
                slot_prim.GetReferences().ClearReferences()
                _set_visibility(slot_prim, False)

        # --- Render ----------------------------------------------------------
        await rep.orchestrator.step_async(rt_subframes=C.RT_SUBFRAMES)

        # --- Capture and save ------------------------------------------------
        fname = f"{frame_idx:06d}"
        for cam_name, rgb_ann, bbox_ann in zip(CAM_NAMES, rgb_anns, bbox_anns):
            rgb_data  = rgb_ann.get_data()
            bbox_data = bbox_ann.get_data()

            _save_rgb(
                rgb_data,
                os.path.join(C.OUTPUT_DIR, cam_name, "rgb", f"{fname}.png"),
            )
            _save_yolo(
                bbox_data, W, H,
                os.path.join(C.OUTPUT_DIR, cam_name, "labels", f"{fname}.txt"),
            )

        if (frame_idx + 1) % 50 == 0 or frame_idx == 0:
            elapsed = time.time() - t0
            fps     = (frame_idx + 1) / elapsed
            remain  = (C.NUM_FRAMES - frame_idx - 1) / max(fps, 1e-6)
            print(f"[pallet_dataset] frame {frame_idx+1:4d}/{C.NUM_FRAMES}"
                  f"  pallets={n_active}"
                  f"  {fps:.1f} fps"
                  f"  ETA {remain/60:.1f} min")

    # ── Finalise ──────────────────────────────────────────────────────────────
    info["total_seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(C.OUTPUT_DIR, "dataset_info.json"), "w") as fh:
        json.dump(info, fh, indent=2)

    total_images = C.NUM_FRAMES * len(CAM_NAMES)
    print(f"[pallet_dataset] Done — {total_images} images in {info['total_seconds']:.0f} s"
          f"  →  {C.OUTPUT_DIR}")


asyncio.ensure_future(_run())
