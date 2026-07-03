"""
generate_homography.py
----------------------
Computes homography matrices for each warehouse security camera defined in
tests/camera_position.usd and writes them to output/homography/.

Camera positions are read directly from the USD stage — edit the USD file in
Isaac Sim and re-run this script to update homographies.

No Isaac Sim required — only numpy and usd-core (pip install usd-core).

Usage:
    conda run -n isaac_scenario python generate_metadata/generate_homography.py

Output (output/homography/):
    <cam_name>.npz   -- numpy archive with keys: K, R, t, H, H_inv
    <cam_name>.json  -- same matrices as nested lists for human inspection

Coordinate conventions:
    World  : X right, Y forward, Z up (Isaac Sim / USD default)
    Camera : USD camera looks along -Z by default

Homography H maps world floor points (X, Y, Z=0) to image pixels (u, v):
    [u*w, v*w, w]^T = H @ [X, Y, 1]^T

H_inv maps image pixels back to world floor XY:
    [X*w, Y*w, w]^T = H_inv @ [u, v, 1]^T
"""

import json
import math
import os
import sys

import numpy as np

try:
    from pxr import Usd, UsdGeom
except ModuleNotFoundError:
    raise SystemExit(
        "ERROR: 'pxr' not found.\n"
        "Run inside the isaac_scenario conda environment:\n\n"
        "  conda run -n isaac_scenario python generate_metadata/generate_homography.py\n"
    )

# ── Path setup ────────────────────────────────────────────────────────────────
_project_root = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import warehouse_sim.config as WC

# ── Configuration ─────────────────────────────────────────────────────────────
CAMERAS_USD  = WC.CAMERA_POSITIONS_USD   # tests/camera_position.usd
IMAGE_WIDTH  = 1920
IMAGE_HEIGHT = 1080
OUTPUT_DIR   = os.path.join(_project_root, "output", "homography")

# Verification points: warehouse floor corners + centre (world X, Y, Z=0)
VERIFY_POINTS = [
    (WC.WALL_X_MIN, WC.WALL_Y_MIN),   # SW wall corner
    (WC.WALL_X_MAX, WC.WALL_Y_MIN),   # SE wall corner
    (WC.WALL_X_MIN, WC.WALL_Y_MAX),   # NW wall corner
    (WC.WALL_X_MAX, WC.WALL_Y_MAX),   # NE wall corner
    (WC.WAREHOUSE_CX, WC.WAREHOUSE_CY),  # warehouse centre
]

# ── Programmatic camera overrides ─────────────────────────────────────────────
# cam_north and cam_east are repositioned at runtime by
# test_scenario_pallet_occupancy_visual.py using ih.spawn_camera() with
# positions derived from the zone bounds.  camera_position.usd is NOT updated
# when the test runs, so the USD-file positions would be wrong here.
#
# These overrides replicate the exact eye/target/fov formulas from the test so
# that the homography always matches the actual recorded camera view.
#
# Keep in sync with the spawn_camera() calls in the test script.
_ZONES_CX  = WC.WAREHOUSE_CX
_ZONES_CY  = (WC.WALL_Y_MIN + WC.STAGING_Y_FAR) / 2.0   # ≈ -13.77
_TARGET_Z  = 0.5                                           # floor aim point
_APERTURE  = 20.955                                        # mm (spawn_camera default)

# cam_north — north of staging looking south over both zones
_EYE_NORTH = (_ZONES_CX, WC.STAGING_Y_FAR + 8.0, 12.0)
_TGT_NORTH = (_ZONES_CX, _ZONES_CY, _TARGET_Z)
_FOV_NORTH = 80.0

# cam_east  — near east wall looking west, elevation chosen so near/far zone
#             edges balance within the vertical FOV (same formula as the test)
_EZ_EAST   = 8.0
_EX_EAST   = WC.WALL_X_MAX - 1.0
_NEAR_X    = -0.93    # loading zone east edge
_FAR_X     = -21.43   # staging zone west edge
_ANG_NEAR  = math.degrees(math.atan2(_EZ_EAST, _EX_EAST - _NEAR_X))
_ANG_FAR   = math.degrees(math.atan2(_EZ_EAST, _EX_EAST - _FAR_X))
_CENTRE_DEP = (_ANG_NEAR + _ANG_FAR) / 2.0
_DX_EAST   = (_EZ_EAST - _TARGET_Z) / math.tan(math.radians(_CENTRE_DEP))
_EYE_EAST  = (_EX_EAST, _ZONES_CY, _EZ_EAST)
_TGT_EAST  = (_EX_EAST - _DX_EAST, _ZONES_CY, _TARGET_Z)
_FOV_EAST  = 80.0

# Map camera name → (eye, target, fov_deg).
# Any camera listed here overrides the position read from camera_position.usd.
PROGRAMMATIC_CAMERAS: dict[str, tuple] = {
    "cam_north": (_EYE_NORTH, _TGT_NORTH, _FOV_NORTH),
    "cam_east":  (_EYE_EAST,  _TGT_EAST,  _FOV_EAST),
}


# ── USD parser ────────────────────────────────────────────────────────────────

def parse_cameras_usd(usd_path):
    """Open the USD stage and return a list of camera dicts.

    Handles both:
      • xformOp:transform  — full 4×4 matrix authored by Isaac Sim's spawn_camera().
        Row 3 = camera position; upper 3×3 rows = (right, up, −fwd) in world
        → directly the world-to-camera rotation matrix.
      • xformOp:translate + xformOp:rotateXYZ  — Euler fallback for hand-authored
        cameras (Blender exports, USD UI, scenario_creation project).

    Returns dicts with keys:
        name, tx, ty, tz,
        R_w2c (3×3 ndarray),   world-to-camera rotation
        t     (3-vector),       translation in camera frame  =  −R_w2c @ eye
        focal_length_mm, horiz_aperture_mm
    """
    stage = Usd.Stage.Open(usd_path)
    if not stage:
        raise RuntimeError(f"Could not open USD: {usd_path}")

    cameras = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Camera):
            continue

        name = prim.GetName()
        xf   = UsdGeom.Xformable(prim)

        tx = ty = tz = 0.0
        rx_deg = ry_deg = rz_deg = 0.0
        R_w2c = None

        for op in xf.GetOrderedXformOps():
            op_name = op.GetOpName()
            val     = op.Get()
            if val is None:
                continue

            if "transform" in op_name:
                # xformOp:transform — full 4×4 matrix (row-major in USD Python)
                # Row layout produced by spawn_camera():
                #   row 0 = right   (camera +X in world)
                #   row 1 = up      (camera +Y in world)
                #   row 2 = -fwd    (camera +Z in world; camera looks along -Z)
                #   row 3 = eye     (camera position in world)
                mat   = np.array([[val[r][c] for c in range(4)] for r in range(4)])
                tx, ty, tz = mat[3, 0], mat[3, 1], mat[3, 2]
                # Rows of upper 3×3 are camera axes expressed in world → R_w2c
                R_w2c = mat[:3, :3].copy()
                break

            if "translate" in op_name:
                tx, ty, tz = float(val[0]), float(val[1]), float(val[2])
            elif "rotateXYZ" in op_name:
                rx_deg, ry_deg, rz_deg = float(val[0]), float(val[1]), float(val[2])

        if R_w2c is None:
            # Euler fallback: intrinsic X→Y→Z sequence gives cam-to-world rotation
            R_c2w = _rot_z(rz_deg) @ _rot_y(ry_deg) @ _rot_x(rx_deg)
            R_w2c = R_c2w.T

        cam_pos = np.array([tx, ty, tz], dtype=np.float64)
        t       = -R_w2c @ cam_pos

        cam         = UsdGeom.Camera(prim)
        focal_mm    = cam.GetFocalLengthAttr().Get()    or 12.0
        aperture_mm = cam.GetHorizontalApertureAttr().Get() or 20.955

        cameras.append(dict(
            name=name, tx=tx, ty=ty, tz=tz,
            R_w2c=R_w2c, t=t,
            focal_length_mm=float(focal_mm),
            horiz_aperture_mm=float(aperture_mm),
        ))

    return cameras


# ── Camera helpers ────────────────────────────────────────────────────────────

def eye_target_to_r_t(eye, target):
    """Compute R_w2c and t from eye/target positions.

    Replicates the look-at matrix built by ih.spawn_camera() so that
    programmatic cameras produce the same R_w2c as parse_cameras_usd() would
    read from the USD stage after spawn_camera() has been called.

    Matrix convention (same as spawn_camera):
        row 0 = right  (fwd × world_up, normalised)
        row 1 = up     (right × fwd, normalised)
        row 2 = -fwd
    R_w2c = [right; up; -fwd]
    t      = -R_w2c @ eye_world
    """
    eye    = np.array(eye,    dtype=np.float64)
    target = np.array(target, dtype=np.float64)

    fwd = target - eye
    fwd = fwd / np.linalg.norm(fwd)

    world_up = np.array([0., 0., 1.])
    right = np.cross(fwd, world_up)
    if np.linalg.norm(right) < 1e-6:
        world_up = np.array([0., 1., 0.])
        right = np.cross(fwd, world_up)
    right = right / np.linalg.norm(right)

    up = np.cross(right, fwd)
    up = up / np.linalg.norm(up)

    R_w2c = np.row_stack([right, up, -fwd])
    t     = -R_w2c @ eye
    return R_w2c, t


# ── Math helpers ──────────────────────────────────────────────────────────────

def _rot_x(deg):
    r = math.radians(deg)
    return np.array([
        [1,           0,            0],
        [0,  math.cos(r), -math.sin(r)],
        [0,  math.sin(r),  math.cos(r)],
    ])


def _rot_y(deg):
    r = math.radians(deg)
    return np.array([
        [ math.cos(r), 0, math.sin(r)],
        [           0, 1,           0],
        [-math.sin(r), 0, math.cos(r)],
    ])


def _rot_z(deg):
    r = math.radians(deg)
    return np.array([
        [math.cos(r), -math.sin(r), 0],
        [math.sin(r),  math.cos(r), 0],
        [          0,            0, 1],
    ])


def build_intrinsics(focal_mm, aperture_mm, width_px, height_px):
    """Pinhole intrinsic matrix K from USD lens parameters."""
    fx = (focal_mm / aperture_mm) * width_px
    fy = fx
    cx = width_px  / 2.0
    cy = height_px / 2.0
    return np.array([
        [fx,  0, cx],
        [ 0, fy, cy],
        [ 0,  0,  1],
    ], dtype=np.float64)


def build_homography(K, R_w2c, t):
    """H maps floor points (X, Y, Z=0) to homogeneous image coords.

    For Z=0 the projection P = K[R|t] simplifies:
        H = K @ [r0 | r1 | t]
    where r0, r1 are the first two columns of R_w2c.
    """
    H     = K @ np.column_stack([R_w2c[:, 0], R_w2c[:, 1], t])
    H_inv = np.linalg.inv(H)
    return H, H_inv


def project_floor_to_image(H, world_xy):
    p = H @ np.array([world_xy[0], world_xy[1], 1.0])
    return p[:2] / p[2]


def project_image_to_floor(H_inv, pixel_uv):
    p = H_inv @ np.array([pixel_uv[0], pixel_uv[1], 1.0])
    return p[:2] / p[2]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    cameras = parse_cameras_usd(CAMERAS_USD)
    if not cameras:
        print(f"No cameras found in {CAMERAS_USD}")
        return
    print(f"Loaded {len(cameras)} camera(s) from {CAMERAS_USD}")

    # Apply programmatic overrides for cameras repositioned by the test script.
    for cam in cameras:
        if cam["name"] not in PROGRAMMATIC_CAMERAS:
            continue
        eye, target, fov_deg = PROGRAMMATIC_CAMERAS[cam["name"]]
        R_w2c, t = eye_target_to_r_t(eye, target)
        focal_mm = _APERTURE / (2.0 * math.tan(math.radians(fov_deg / 2.0)))
        cam["R_w2c"]          = R_w2c
        cam["t"]              = t
        cam["tx"], cam["ty"], cam["tz"] = eye
        cam["focal_length_mm"]  = focal_mm
        cam["horiz_aperture_mm"] = _APERTURE
        print(f"  [{cam['name']}] position overridden from PROGRAMMATIC_CAMERAS"
              f" eye=({eye[0]:.2f},{eye[1]:.2f},{eye[2]:.2f})")
    print()

    for cam in cameras:
        name        = cam["name"]
        tx, ty, tz  = cam["tx"], cam["ty"], cam["tz"]
        R_w2c       = cam["R_w2c"]
        t           = cam["t"]
        focal_mm    = cam["focal_length_mm"]
        aperture_mm = cam["horiz_aperture_mm"]

        K        = build_intrinsics(focal_mm, aperture_mm, IMAGE_WIDTH, IMAGE_HEIGHT)
        H, H_inv = build_homography(K, R_w2c, t)

        # Save numpy archive
        npz_path = os.path.join(OUTPUT_DIR, f"{name}.npz")
        np.savez(npz_path, K=K, R=R_w2c, t=t, H=H, H_inv=H_inv)

        # Save JSON for human inspection
        json_path = os.path.join(OUTPUT_DIR, f"{name}.json")
        data = {
            "camera":           name,
            "position_world":   [tx, ty, tz],
            "image_resolution": [IMAGE_WIDTH, IMAGE_HEIGHT],
            "focal_length_mm":  focal_mm,
            "horiz_aperture_mm": aperture_mm,
            "K":     K.tolist(),
            "R":     R_w2c.tolist(),
            "t":     t.tolist(),
            "H":     H.tolist(),
            "H_inv": H_inv.tolist(),
        }
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        # Round-trip verification
        max_err = 0.0
        for wx, wy in VERIFY_POINTS:
            uv   = project_floor_to_image(H, (wx, wy))
            back = project_image_to_floor(H_inv, uv)
            err  = math.hypot(back[0] - wx, back[1] - wy)
            max_err = max(max_err, err)

        status = "OK" if max_err < 1e-6 else f"WARN max_err={max_err:.2e}"
        print(f"[{name}]  pos=({tx:.2f},{ty:.2f},{tz:.2f})"
              f"  fl={focal_mm:.1f}mm  ap={aperture_mm:.2f}mm"
              f"  round-trip {status}")
        print(f"         → {npz_path}")
        print(f"         → {json_path}")

    print(f"\nDone. {len(cameras)} homography files written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
