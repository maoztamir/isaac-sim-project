"""
utils/camera_usd.py
-------------------
Read UsdGeom.Camera prims from a live Isaac Sim stage or a USD file,
compute homography matrices, and export results.

Requires: pxr  (available inside Isaac Sim or via  pip install usd-core)

Typical usage (inside Isaac Sim Script Editor):
    import omni.usd
    from utils.camera_usd import export_cameras_from_stage

    stage = omni.usd.get_context().get_stage()
    cam_paths = export_cameras_from_stage(
        stage,
        output_dir="/path/to/homography",
        width=1920, height=1080,
    )
"""

from __future__ import annotations

import os
from pxr import Usd, UsdGeom

from .camera_homography import (
    build_K,
    extract_pose_from_matrix4,
    euler_xyz_from_R_c2w,
    build_homography,
    save_homography,
)


# ---------------------------------------------------------------------------
# Prim discovery
# ---------------------------------------------------------------------------

def list_camera_prims(stage, parent_path: str = "/World/Cameras") -> list:
    """
    Return all UsdGeom.Camera prims under *parent_path* in *stage*.

    Traverses recursively so cameras nested inside Xforms are also found.
    Returns a list of pxr.Usd.Prim objects.
    """
    parent = stage.GetPrimAtPath(parent_path)
    if not parent or not parent.IsValid():
        return []
    return [p for p in Usd.PrimRange(parent) if p.IsA(UsdGeom.Camera)]


# ---------------------------------------------------------------------------
# Single-camera processing
# ---------------------------------------------------------------------------

def process_camera_prim(prim,
                         width: int,
                         height: int) -> dict | None:
    """
    Extract pose and compute homography for one Camera prim.

    Expects the prim to have an xformOp:transform (4×4 GfMatrix4d) as
    written by isaac_helpers.spawn_camera() / spawn_cameras_from_usd().

    Returns a dict with keys:
        name, cam_path, pos, rot_xyz_deg, K, R, t, H, H_inv,
        focal_mm, aperture_mm
    or None if the required transform op is missing.
    """
    usd_cam = UsdGeom.Camera(prim)
    xf      = UsdGeom.Xformable(prim)

    mat4 = None
    for op in xf.GetOrderedXformOps():
        val = op.Get()
        if val is not None and "transform" in op.GetOpName():
            mat4 = val
            break

    if mat4 is None:
        print(f"[camera_usd] {prim.GetName()}: no xformOp:transform — skipped")
        return None

    focal_mm    = float(usd_cam.GetFocalLengthAttr().Get()        or 12.0)
    aperture_mm = float(usd_cam.GetHorizontalApertureAttr().Get() or 20.955)

    K                      = build_K(focal_mm, aperture_mm, width, height)
    pos, R, t, R_c2w       = extract_pose_from_matrix4(mat4)
    rot_xyz_deg            = euler_xyz_from_R_c2w(R_c2w)
    H, H_inv               = build_homography(K, R, t)

    return dict(
        name        = prim.GetName(),
        cam_path    = str(prim.GetPath()),
        pos         = pos,
        rot_xyz_deg = rot_xyz_deg,
        K=K, R=R, t=t, H=H, H_inv=H_inv,
        focal_mm    = focal_mm,
        aperture_mm = aperture_mm,
    )


# ---------------------------------------------------------------------------
# Bulk export — live stage
# ---------------------------------------------------------------------------

def export_cameras_from_stage(stage,
                               output_dir: str,
                               width: int  = 1920,
                               height: int = 1080,
                               parent_path: str = "/World/Cameras") -> list[str]:
    """
    Find all cameras under *parent_path* in the live *stage*, compute
    homography matrices, and write JSON + NPZ files to *output_dir*.

    Returns a list of camera prim path strings (e.g. ["/World/Cameras/cam_0"]).
    Printed summary line per camera; nothing printed for cameras without a
    valid transform.
    """
    prims = list_camera_prims(stage, parent_path)
    if not prims:
        print(f"[camera_usd] No Camera prims found under '{parent_path}'.")
        return []

    cam_paths = []
    for prim in prims:
        result = process_camera_prim(prim, width, height)
        if result is None:
            continue

        json_path, npz_path = save_homography(
            output_dir  = output_dir,
            cam_name    = result["name"],
            pos         = result["pos"],
            rot_xyz_deg = result["rot_xyz_deg"],
            K=result["K"], R=result["R"], t=result["t"],
            H=result["H"], H_inv=result["H_inv"],
            width=width, height=height,
            extra={
                "focal_length_mm":   result["focal_mm"],
                "horiz_aperture_mm": result["aperture_mm"],
            },
        )

        rx, ry, rz = result["rot_xyz_deg"]
        px, py, pz = result["pos"]
        print(f"[camera_usd] {result['name']}"
              f"  pos=({px:.1f}, {py:.1f}, {pz:.1f})"
              f"  rotXYZ=({rx:.1f}, {ry:.1f}, {rz:.1f})°"
              f"  fl={result['focal_mm']:.1f}mm")
        print(f"    → {json_path}")

        cam_paths.append(result["cam_path"])

    print(f"[camera_usd] {len(cam_paths)} camera(s) exported to {output_dir}")
    return cam_paths


# ---------------------------------------------------------------------------
# Bulk export — USD file  (no Isaac Sim required, only usd-core)
# ---------------------------------------------------------------------------

def export_cameras_from_usd(usd_path: str,
                             output_dir: str,
                             width: int  = 1920,
                             height: int = 1080) -> list[str]:
    """
    Open a USD file (read-only), find all Camera prims, compute homographies,
    write JSON + NPZ to *output_dir*.

    Drop-in replacement for generate_homography.py that uses the shared
    camera_homography math and save_homography I/O.

    Returns list of camera name strings (not prim paths, since the stage
    is temporary).
    """
    stage = Usd.Stage.Open(usd_path)
    if not stage:
        raise FileNotFoundError(f"[camera_usd] Cannot open USD: {usd_path}")

    cam_names = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Camera):
            continue

        result = process_camera_prim(prim, width, height)
        if result is None:
            continue

        json_path, npz_path = save_homography(
            output_dir  = output_dir,
            cam_name    = result["name"],
            pos         = result["pos"],
            rot_xyz_deg = result["rot_xyz_deg"],
            K=result["K"], R=result["R"], t=result["t"],
            H=result["H"], H_inv=result["H_inv"],
            width=width, height=height,
            extra={
                "focal_length_mm":   result["focal_mm"],
                "horiz_aperture_mm": result["aperture_mm"],
            },
        )

        rx, ry, rz = result["rot_xyz_deg"]
        px, py, pz = result["pos"]
        print(f"[camera_usd] {result['name']}"
              f"  pos=({px:.1f}, {py:.1f}, {pz:.1f})"
              f"  rotXYZ=({rx:.1f}, {ry:.1f}, {rz:.1f})°")
        print(f"    → {json_path}")

        cam_names.append(result["name"])

    print(f"[camera_usd] {len(cam_names)} camera(s) exported from {usd_path}")
    return cam_names
