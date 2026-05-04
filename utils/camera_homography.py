"""
utils/camera_homography.py
--------------------------
Pure-math camera utilities: intrinsics, extrinsics, and floor homography.

No Isaac Sim dependency — works in any Python environment with numpy.

Coordinate conventions (match generate_homography.py exactly):
    World  : X right, Y forward, Z up  (Isaac Sim / USD default)
    Camera : looks along -Z, right=X, up=Y  (USD/OpenGL convention)
    Euler  : intrinsic XYZ — R_cam_to_world = Rz(rz) @ Ry(ry) @ Rx(rx)

Homography H maps world floor points (X, Y, Z=0) to image pixels (u, v):
    [u*w, v*w, w]^T = H @ [X, Y, 1]^T

H_inv maps image pixels back to world floor XY:
    [X*w, Y*w, w]^T = H_inv @ [u, v, 1]^T
"""

from __future__ import annotations

import json
import math
import os

import numpy as np


# ---------------------------------------------------------------------------
# Intrinsics
# ---------------------------------------------------------------------------

def build_K(focal_mm: float,
            aperture_mm: float,
            width: int,
            height: int) -> np.ndarray:
    """
    Pinhole intrinsic matrix from USD lens parameters.

    fx = (focal_mm / aperture_mm) * width   (square pixels assumed)
    cx = width  / 2
    cy = height / 2
    """
    fx = (focal_mm / aperture_mm) * width
    return np.array([
        [fx,  0,  width  / 2.0],
        [ 0, fx,  height / 2.0],
        [ 0,  0,  1.0         ],
    ], dtype=np.float64)


# ---------------------------------------------------------------------------
# Extrinsics from a USD GfMatrix4d
# ---------------------------------------------------------------------------

def extract_pose_from_matrix4(m) -> tuple:
    """
    Extract world-to-camera R and t from a GfMatrix4d camera-to-world matrix.

    spawn_camera() (isaac_helpers.py) stores the camera-to-world transform
    in row-major USD convention (v_world = v_local @ M) where:
        row 0 = camera X (right)  in world space
        row 1 = camera Y (up)     in world space
        row 2 = camera Z (-fwd)   in world space
        row 3 = camera position   in world space

    In column-vector notation (numpy), R_cam_to_world columns = camera axes:
        R_c2w[:, j] = row j of M   for j = 0, 1, 2

    Returns
    -------
    pos : (tx, ty, tz)  —  camera position in world space
    R   : (3, 3) ndarray  —  world-to-camera rotation
    t   : (3,)   ndarray  —  world-to-camera translation  (= -R @ pos)
    R_c2w : (3, 3) ndarray  —  camera-to-world rotation (kept for Euler decomposition)
    """
    tx, ty, tz = float(m[3][0]), float(m[3][1]), float(m[3][2])

    R_c2w = np.array([
        [m[0][0], m[1][0], m[2][0]],
        [m[0][1], m[1][1], m[2][1]],
        [m[0][2], m[1][2], m[2][2]],
    ], dtype=np.float64)

    R = R_c2w.T
    t = -R @ np.array([tx, ty, tz], dtype=np.float64)
    return (tx, ty, tz), R, t, R_c2w


def euler_xyz_from_R_c2w(R_c2w: np.ndarray) -> tuple[float, float, float]:
    """
    Decompose R_c2w = Rz(rz) @ Ry(ry) @ Rx(rx) into XYZ Euler angles in degrees.
    Handles gimbal lock (|ry| ≈ 90°) gracefully.
    """
    ry_rad = math.asin(max(-1.0, min(1.0, -R_c2w[2, 0])))
    cos_ry = math.cos(ry_rad)
    if abs(cos_ry) > 1e-6:
        rx_rad = math.atan2(R_c2w[2, 1], R_c2w[2, 2])
        rz_rad = math.atan2(R_c2w[1, 0], R_c2w[0, 0])
    else:
        rx_rad = math.atan2(-R_c2w[1, 2], R_c2w[1, 1])
        rz_rad = 0.0
    return (math.degrees(rx_rad),
            math.degrees(ry_rad),
            math.degrees(rz_rad))


# ---------------------------------------------------------------------------
# Homography
# ---------------------------------------------------------------------------

def build_homography(K: np.ndarray,
                     R: np.ndarray,
                     t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Floor-plane (Z=0) homography H and its inverse H_inv.

    For Z=0 the projection P = K[R|t] reduces to:
        H = K @ [r0 | r1 | t]
    where r0, r1 are columns 0 and 1 of R (world-to-camera).
    """
    H     = K @ np.column_stack([R[:, 0], R[:, 1], t])
    H_inv = np.linalg.inv(H)
    return H, H_inv


def project_floor_to_image(H: np.ndarray,
                            world_xy: tuple[float, float]) -> tuple[float, float]:
    """Map a world floor point (X, Y) → pixel (u, v)."""
    p = H @ np.array([world_xy[0], world_xy[1], 1.0])
    uv = p[:2] / p[2]
    return (float(uv[0]), float(uv[1]))


def project_image_to_floor(H_inv: np.ndarray,
                            pixel_uv: tuple[float, float]) -> tuple[float, float]:
    """Map a pixel (u, v) → world floor (X, Y)."""
    p = H_inv @ np.array([pixel_uv[0], pixel_uv[1], 1.0])
    xy = p[:2] / p[2]
    return (float(xy[0]), float(xy[1]))


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_homography(output_dir: str,
                    cam_name: str,
                    pos: tuple,
                    rot_xyz_deg: tuple,
                    K: np.ndarray,
                    R: np.ndarray,
                    t: np.ndarray,
                    H: np.ndarray,
                    H_inv: np.ndarray,
                    width: int,
                    height: int,
                    extra: dict | None = None) -> tuple[str, str]:
    """
    Write cam_<name>.json and cam_<name>.npz to output_dir.

    JSON schema matches generate_homography.py so generate_bev_map.py and
    generate_area_polygons.py consume these files without modification.

    Returns (json_path, npz_path).
    """
    os.makedirs(output_dir, exist_ok=True)

    npz_path  = os.path.join(output_dir, f"{cam_name}.npz")
    json_path = os.path.join(output_dir, f"{cam_name}.json")

    np.savez(npz_path, K=K, R=R, t=t, H=H, H_inv=H_inv)

    data: dict = {
        "camera":           cam_name,
        "position_world":   list(pos),
        "rotation_xyz_deg": list(rot_xyz_deg),
        "image_resolution": [width, height],
        "K":     K.tolist(),
        "R":     R.tolist(),
        "t":     t.tolist(),
        "H":     H.tolist(),
        "H_inv": H_inv.tolist(),
    }
    if extra:
        data.update(extra)

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    return json_path, npz_path


def load_homography(json_path: str) -> dict:
    """
    Load a homography JSON written by save_homography().

    Returns a dict with keys: camera, position_world, rotation_xyz_deg,
    image_resolution, K, R, t, H, H_inv  (matrices as np.ndarray).
    """
    with open(json_path) as f:
        d = json.load(f)

    for key in ("K", "R", "t", "H", "H_inv"):
        if key in d:
            d[key] = np.array(d[key], dtype=np.float64)

    return d
