"""
generate_area_polygons.py
--------------------------
Produces output/area_polygons.json — a lookup table of every named floor area
(loading zones, staging zones, shelf columns, aisles) described as:

  • world_polygon  : [[X, Y], ...] floor coordinates (Z=0)
  • camera_polygons: per-camera {cam_name: [[u, v], ...]} pixel coordinates
  • visible_in     : list of cameras where the area projects inside the image

Used downstream to count / classify objects detected in camera frames:
  1. Run your object detector → get bounding-box centres (u, v) per camera.
  2. Load area_polygons.json.
  3. For each detection, check which area polygon (in that camera's space)
     contains the point → assign the detection to that area.

All geometry comes from warehouse_sim/config.py — edit config.py to adjust.

Usage:
    conda run -n isaac_scenario python generate_metadata/generate_area_polygons.py
    conda run -n isaac_scenario python generate_metadata/generate_area_polygons.py --output my_areas.json

Dependencies: numpy  (no Isaac Sim required)
"""

import argparse
import json
import os
import sys

import numpy as np

# ── Path setup ────────────────────────────────────────────────────────────────
_project_root = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import warehouse_sim.config as WC

# ── Paths ─────────────────────────────────────────────────────────────────────
HOMOGRAPHY_DIR = os.path.join(_project_root, "output", "homography")
DEFAULT_OUTPUT = os.path.join(_project_root, "output", "area_polygons.json")

# ── Shelf column and aisle edges (X coordinates) ─────────────────────────────
# Derived from shelf detection (shelves.py runtime scan — see session_apr11 memory).
# 12 edges → 11 segments alternating: shelf (even i), aisle (odd i).
#   Shelves: (-24.53,-20.94), (-19.80,-15.99), (-14.85,-11.03),
#            (-9.89,-6.07), (-4.93,-1.12), (0.02,3.66)
#   Aisles:  (-20.94,-19.80), (-15.99,-14.85), (-11.03,-9.89),
#            (-6.07,-4.93), (-1.12,0.02)
SHELF_COL_EDGES = [
    -24.53, -20.94,   # shelf 1 bounds
    -19.80, -15.99,   # aisle 1 | shelf 2
    -14.85, -11.03,   # aisle 2 | shelf 3
     -9.89,  -6.07,   # aisle 3 | shelf 4
     -4.93,  -1.12,   # aisle 4 | shelf 5
      0.02,   3.66,   # aisle 5 | shelf 6
]
SHELF_Y_MIN = WC.ZONES["ShelvesArea"][2]   # ≈ 3.60
SHELF_Y_MAX = WC.ZONES["ShelvesArea"][3]   # ≈ 28.80


# ── Area definitions ──────────────────────────────────────────────────────────

def _rect(x0, x1, y0, y1):
    """Return a clockwise rectangle as a list of [X, Y] world points."""
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _wall_rect(x0, x1, y_wall, h):
    """Return 4 corners of a wall face as [X, Y, Z] with Y fixed at y_wall, Z 0→h."""
    return [[x0, y_wall, 0], [x1, y_wall, 0],
            [x1, y_wall, h], [x0, y_wall, h]]


def build_areas():
    """Return a list of area dicts with keys: name, type, world_polygon."""
    areas = []

    # Dock doors — floor footprint + full wall-face rectangle (GATE_W × GATE_TOTAL_H)
    door_labels = ["door_west", "door_center", "door_east"]
    for label, offset in zip(door_labels, WC.GATE_OFFSETS):
        door_cx = WC.WAREHOUSE_CX + offset
        areas.append({
            "name": label,
            "type": "door",
            "world_polygon": _rect(
                door_cx - WC.GATE_W / 2, door_cx + WC.GATE_W / 2,
                WC.WALL_Y_MIN, WC.WALL_Y_MIN + WC.GATE_D,
            ),
            "world_polygon_3d": _wall_rect(
                door_cx - WC.GATE_W / 2, door_cx + WC.GATE_W / 2,
                WC.WALL_Y_MIN, WC.GATE_TOTAL_H,
            ),
        })

    # Loading zones — one per dock door
    zone_labels = ["loading_zone_west", "loading_zone_center", "loading_zone_east"]
    for label, offset in zip(zone_labels, WC.GATE_OFFSETS):
        door_cx = WC.WAREHOUSE_CX + offset
        areas.append({
            "name": label,
            "type": "loading",
            "world_polygon": _rect(
                door_cx - WC.LOAD_W / 2, door_cx + WC.LOAD_W / 2,
                WC.WALL_Y_MIN, WC.WALL_Y_MIN + WC.LOAD_D,
            ),
        })

    # Staging zones — one per dock door
    stage_labels = ["staging_zone_west", "staging_zone_center", "staging_zone_east"]
    for label, offset in zip(stage_labels, WC.GATE_OFFSETS):
        scx = WC.WAREHOUSE_CX + offset
        areas.append({
            "name": label,
            "type": "staging",
            "world_polygon": _rect(
                scx - WC.STAGING_W / 2, scx + WC.STAGING_W / 2,
                WC.STAGING_Y_NEAR, WC.STAGING_Y_FAR,
            ),
        })

    # Shelf columns and aisles (alternating even=shelf / odd=aisle by segment index)
    shelf_num = 0
    aisle_num = 0
    for i in range(len(SHELF_COL_EDGES) - 1):
        x0 = SHELF_COL_EDGES[i]
        x1 = SHELF_COL_EDGES[i + 1]
        if i % 2 == 0:
            shelf_num += 1
            areas.append({
                "name": f"shelf_column_{shelf_num}",
                "type": "shelf",
                "world_polygon": _rect(x0, x1, SHELF_Y_MIN, SHELF_Y_MAX),
            })
        else:
            aisle_num += 1
            areas.append({
                "name": f"aisle_{aisle_num}",
                "type": "aisle",
                "world_polygon": _rect(x0, x1, SHELF_Y_MIN, SHELF_Y_MAX),
            })

    return areas


# ── Homography helpers ────────────────────────────────────────────────────────

def load_cameras():
    """Return list of dicts: name, H (3×3 ndarray), H_inv, image_width, image_height."""
    if not os.path.isdir(HOMOGRAPHY_DIR):
        raise RuntimeError(
            f"Homography directory not found: {HOMOGRAPHY_DIR}\n"
            "Run generate_homography.py first."
        )
    cameras = []
    for fname in sorted(os.listdir(HOMOGRAPHY_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(HOMOGRAPHY_DIR, fname)) as f:
            d = json.load(f)
        res = d.get("image_resolution", [1920, 1080])
        cameras.append({
            "name":         d["camera"],
            "H":            np.array(d["H"]),
            "H_inv":        np.array(d["H_inv"]),
            "image_width":  res[0],
            "image_height": res[1],
            "K":            np.array(d["K"]),
            "R_w2c":        np.array(d["R"]),
            "t":            np.array(d["t"]),
        })
    return cameras


def project_world_to_pixel(H, world_xy):
    """Project a single world floor point [X, Y] to pixel [u, v]."""
    p = H @ np.array([world_xy[0], world_xy[1], 1.0])
    return (p[:2] / p[2]).tolist()


def project_3d(K, R_w2c, t, world_xyz, img_w):
    """Project a 3D world point [X, Y, Z] to pixel [u, v] with Isaac Sim u-flip.

    Returns None if the point is behind the camera (cam_z >= 0 in Isaac Sim's -Z convention).
    """
    cam_pt = R_w2c @ np.array(world_xyz) + t
    if cam_pt[2] >= 0:
        return None
    p = K @ cam_pt
    u_raw = p[0] / p[2]
    v     = p[1] / p[2]
    return [img_w - u_raw, v]


def polygon_visible(pixel_polygon, img_w, img_h, margin=50):
    """Return True only if ALL vertices project inside the image.

    Any-vertex and centroid checks both fail for large world polygons that
    straddle the camera position or whose far end barely clips the frame.
    Requiring every corner ensures the whole area is genuinely within the FOV.
    """
    return all(
        -margin <= u <= img_w + margin and -margin <= v <= img_h + margin
        for u, v in pixel_polygon
    )


def point_in_polygon(point, polygon):
    """Ray-casting test: True if point [u, v] is inside the polygon."""
    u, v = point
    n    = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > v) != (yj > v)) and (u < (xj - xi) * (v - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


# ── Main ──────────────────────────────────────────────────────────────────────

def main(output_path):
    cameras = load_cameras()
    if not cameras:
        print(f"No homography JSON files found in {HOMOGRAPHY_DIR}")
        print("Run generate_homography.py first.")
        return
    print(f"Loaded {len(cameras)} camera(s): {[c['name'] for c in cameras]}")

    areas = build_areas()
    print(f"Defined {len(areas)} areas  "
          f"({sum(1 for a in areas if a['type']=='door')} doors, "
          f"{sum(1 for a in areas if a['type']=='loading')} loading, "
          f"{sum(1 for a in areas if a['type']=='staging')} staging, "
          f"{sum(1 for a in areas if a['type']=='shelf')} shelves, "
          f"{sum(1 for a in areas if a['type']=='aisle')} aisles)")

    results = []
    for area in areas:
        world_poly    = area["world_polygon"]
        world_poly_3d = area.get("world_polygon_3d")
        cam_polys     = {}
        visible_in    = []

        for cam in cameras:
            w = cam["image_width"]

            if world_poly_3d is not None:
                # Door: project the wall-face rectangle with full 3D camera model.
                pixel_pts = [project_3d(cam["K"], cam["R_w2c"], cam["t"], pt, w)
                             for pt in world_poly_3d]
                if any(pt is None for pt in pixel_pts):
                    continue  # a vertex is behind this camera — skip
                pixel_poly = pixel_pts
            else:
                pixel_poly = [project_world_to_pixel(cam["H"], pt) for pt in world_poly]
                pixel_poly = [[w - u, v] for u, v in pixel_poly]

            cam_polys[cam["name"]] = pixel_poly
            if polygon_visible(pixel_poly, cam["image_width"], cam["image_height"]):
                visible_in.append(cam["name"])

        entry = {
            "name":            area["name"],
            "type":            area["type"],
            "world_polygon":   world_poly,
            "camera_polygons": cam_polys,
            "visible_in":      visible_in,
        }
        if world_poly_3d is not None:
            entry["world_polygon_3d"] = world_poly_3d
        results.append(entry)

        vis_str = ", ".join(visible_in) if visible_in else "none"
        print(f"  [{area['type']:8s}] {area['name']:30s}  visible in: {vis_str}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"areas": results}, f, indent=2)

    print(f"\nSaved {len(results)} area polygons → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate area polygon lookup table.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"Output JSON path (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()
    main(args.output)
