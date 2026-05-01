"""
verify_area_polygons.py
-----------------------
For each surveillance camera produces a side-by-side PNG on the camera frame:
  LEFT  — "camera_polygons":   stored pixel polygons from area_polygons.json
  RIGHT — "re-projected":      polygons re-computed from world geometry each run
           Floor areas  → floor homography H + u-flip
           Door areas   → full 3D projection K[R|t] of the wall-face rectangle

Per-camera output:  output/area_verification/<cam_name>.png
Composite:          output/area_verification/composite.png  (N-row × 2-col grid)

Frame source layout (BasicWriter / Replicator output):
    FRAMES_DIR/<cam_name>/rgb/rgb_<NNNNN>.png

Usage:
    conda run -n isaac_scenario python generate_metadata/verify_area_polygons.py
    conda run -n isaac_scenario python generate_metadata/verify_area_polygons.py \\
        --frames-dir /media/storage/replicator/_out_sdrec_2 --frame 500

Dependencies: numpy, matplotlib, Pillow  (no Isaac Sim required)
"""

import argparse
import json
import os
import sys

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

# ── Path setup ────────────────────────────────────────────────────────────────
_project_root = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── Knobs ─────────────────────────────────────────────────────────────────────
DEFAULT_FRAMES_DIR = "/media/storage/replicator/_out_sdrec_2"
DEFAULT_FRAME_IDX  = 0
AREAS_JSON         = os.path.join(_project_root, "output", "area_polygons.json")
HOMOGRAPHY_DIR     = os.path.join(_project_root, "output", "homography")
OUTPUT_DIR         = os.path.join(_project_root, "output", "area_verification")

POLY_ALPHA = 0.25
POLY_LW    = 2.0

TYPE_STYLE = {
    "door":    {"color": "#E74C3C", "label": "Door"},
    "loading": {"color": "#E67E22", "label": "Loading"},
    "staging":  {"color": "#2980B9", "label": "Staging"},
    "shelf":    {"color": "#27AE60", "label": "Shelf column"},
    "aisle":    {"color": "#1ABC9C", "label": "Aisle"},
}


# ── Data loaders ──────────────────────────────────────────────────────────────

def _load_camera_data():
    """Return dict cam_name → {H, H_inv, K, R_w2c, t, image_width, image_height}."""
    cams = {}
    if not os.path.isdir(HOMOGRAPHY_DIR):
        return cams
    for fname in sorted(os.listdir(HOMOGRAPHY_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(HOMOGRAPHY_DIR, fname)) as f:
            d = json.load(f)
        res = d.get("image_resolution", [1920, 1080])
        cams[d["camera"]] = {
            "H":            np.array(d["H"]),
            "H_inv":        np.array(d["H_inv"]),
            "K":            np.array(d["K"]),
            "R_w2c":        np.array(d["R"]),
            "t":            np.array(d["t"]),
            "image_width":  res[0],
            "image_height": res[1],
        }
    return cams


def _frame_path(frames_dir, cam_name, frame_idx):
    rgb_dir = os.path.join(frames_dir, cam_name, "rgb")
    if not os.path.isdir(rgb_dir):
        return None
    fname = f"rgb_{frame_idx:04d}.png"
    path  = os.path.join(rgb_dir, fname)
    if os.path.isfile(path):
        return path
    pngs = sorted(f for f in os.listdir(rgb_dir) if f.endswith(".png"))
    return os.path.join(rgb_dir, pngs[0]) if pngs else None


def _load_frame(path, img_w, img_h):
    if path and os.path.isfile(path):
        return np.array(Image.open(path).convert("RGB"))
    return np.full((img_h, img_w, 3), 35, dtype=np.uint8)


# ── Polygon helpers ───────────────────────────────────────────────────────────

def _project_world_polygon(H, world_poly):
    """Project a list of [X, Y] world points through H → [[u, v], ...]."""
    pts = []
    for wx, wy in world_poly:
        p = H @ np.array([wx, wy, 1.0])
        pts.append([p[0] / p[2], p[1] / p[2]])
    return pts


def _flip_u(poly_px, img_w):
    """Apply horizontal flip:  u_corrected = img_w - u_raw."""
    return [[img_w - u, v] for u, v in poly_px]


def _poly_centroid(vertices):
    arr = np.array(vertices)
    return arr[:, 0].mean(), arr[:, 1].mean()


def _clip_poly_to_image(vertices, img_w, img_h, margin=200):
    for u, v in vertices:
        if -margin <= u <= img_w + margin and -margin <= v <= img_h + margin:
            return True
    return False


def _project_3d_polygon(K, R_w2c, t, poly_3d, img_w):
    """Project a list of [X, Y, Z] world points via full 3D camera model + u-flip.

    Returns None if any vertex is behind the camera (cam_z >= 0).
    """
    pts = []
    for xyz in poly_3d:
        cam_pt = R_w2c @ np.array(xyz) + t
        if cam_pt[2] >= 0:
            return None
        p = K @ cam_pt
        pts.append([img_w - p[0] / p[2], p[1] / p[2]])
    return pts


# ── Shared draw routine ───────────────────────────────────────────────────────

def _draw_polygons(ax, polys_by_area, img_w, img_h):
    """Draw a list of (area_dict, pixel_polygon) pairs onto *ax*.

    polys_by_area: list of (area, poly_px) where poly_px is [[u,v], ...].
    Returns the set of area types that had at least one visible polygon.
    """
    seen_types = set()
    for area, poly_px in polys_by_area:
        if not _clip_poly_to_image(poly_px, img_w, img_h):
            continue
        atype = area["type"]
        color = TYPE_STYLE.get(atype, {}).get("color", "#AAAAAA")

        alpha = 0.55 if atype == "door" else POLY_ALPHA
        lw    = POLY_LW * 2 if atype == "door" else POLY_LW

        ax.add_patch(plt.Polygon(
            np.array(poly_px), closed=True,
            facecolor=color, alpha=alpha,
            edgecolor=color, linewidth=lw, zorder=4,
        ))

        cu, cv = _poly_centroid(poly_px)
        if 0 <= cu <= img_w and 0 <= cv <= img_h:
            short = (area["name"]
                     .replace("_zone_", "\n")
                     .replace("shelf_column_", "S")
                     .replace("aisle_", "A"))
            ax.text(cu, cv, short, ha="center", va="center",
                    fontsize=7, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor=color,
                              edgecolor="none", alpha=0.75),
                    zorder=5)
        seen_types.add(atype)
    return seen_types


def _add_legend(ax, seen_types):
    handles = [
        mpatches.Patch(facecolor=TYPE_STYLE[t]["color"], alpha=0.6,
                       edgecolor=TYPE_STYLE[t]["color"],
                       label=TYPE_STYLE[t]["label"])
        for t in ("door", "loading", "staging", "shelf", "aisle")
        if t in seen_types
    ]
    if handles:
        ax.legend(handles=handles, loc="lower right", fontsize=7,
                  framealpha=0.8, edgecolor="#CCCCCC")


def _setup_image_ax(ax, frame_arr, img_w, img_h, title):
    ax.imshow(frame_arr, origin="upper", extent=[0, img_w, img_h, 0])
    ax.set_xlim(0, img_w)
    ax.set_ylim(img_h, 0)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10, fontweight="bold", pad=6)
    ax.axis("off")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(frames_dir, frame_idx, areas_path, output_dir):
    if not os.path.isfile(areas_path):
        raise SystemExit(
            f"area_polygons.json not found: {areas_path}\n"
            "Run generate_area_polygons.py first."
        )

    with open(areas_path) as f:
        areas = json.load(f)["areas"]

    cam_data = _load_camera_data()
    if not cam_data:
        raise SystemExit(f"No homography JSON files found in {HOMOGRAPHY_DIR}")

    all_cam_names = sorted(cam_data.keys())
    os.makedirs(output_dir, exist_ok=True)

    # ── Per-camera side-by-side output ────────────────────────────────────────
    n_cams = len(all_cam_names)
    for cam_name in all_cam_names:
        cd    = cam_data[cam_name]
        img_w = cd["image_width"]
        img_h = cd["image_height"]
        H     = cd["H"]

        fpath = _frame_path(frames_dir, cam_name, frame_idx)
        if fpath:
            print(f"[{cam_name}] frame: {fpath}")
        else:
            print(f"[{cam_name}] no frame found — using dark background")
        frame_arr = _load_frame(fpath, img_w, img_h)

        # LEFT  — stored camera_polygons from area_polygons.json
        # RIGHT — re-projected: 3D wall-face for doors, H+u-flip for floor areas
        stored_polys = []
        reprojected_polys = []
        for area in areas:
            if cam_name not in area.get("visible_in", []):
                continue
            stored_px = area["camera_polygons"].get(cam_name)
            if stored_px:
                stored_polys.append((area, stored_px))
            if area.get("world_polygon_3d"):
                proj_px = _project_3d_polygon(cd["K"], cd["R_w2c"], cd["t"],
                                              area["world_polygon_3d"], img_w)
                if proj_px is not None:
                    reprojected_polys.append((area, proj_px))
            else:
                corr_px = _flip_u(_project_world_polygon(H, area["world_polygon"]), img_w)
                reprojected_polys.append((area, corr_px))

        fig, (ax_raw, ax_corr) = plt.subplots(
            1, 2, figsize=(img_w / 75, img_h / 150),
        )

        _setup_image_ax(ax_raw,  frame_arr, img_w, img_h,
                        f"{cam_name} — camera_polygons (stored)")
        seen_raw  = _draw_polygons(ax_raw,  stored_polys,  img_w, img_h)
        _add_legend(ax_raw, seen_raw)

        _setup_image_ax(ax_corr, frame_arr, img_w, img_h,
                        f"{cam_name} — re-projected (3D doors / H floor)")
        seen_corr = _draw_polygons(ax_corr, reprojected_polys, img_w, img_h)
        _add_legend(ax_corr, seen_corr)

        plt.tight_layout(pad=0.4)
        out_path = os.path.join(output_dir, f"{cam_name}.png")
        fig.savefig(out_path, dpi=100, bbox_inches="tight")
        plt.close(fig)
        print(f"[{cam_name}] saved → {out_path}")

    # ── Composite: N rows × 2 cols ────────────────────────────────────────────
    fig, axes = plt.subplots(n_cams, 2, figsize=(9.6 * 2, n_cams * 5.4))

    for row, cam_name in enumerate(all_cam_names):
        cd    = cam_data[cam_name]
        img_w = cd["image_width"]
        img_h = cd["image_height"]
        H     = cd["H"]

        fpath     = _frame_path(frames_dir, cam_name, frame_idx)
        frame_arr = _load_frame(fpath, img_w, img_h)

        stored_polys      = []
        reprojected_polys = []
        for area in areas:
            if cam_name not in area.get("visible_in", []):
                continue
            stored_px = area["camera_polygons"].get(cam_name)
            if stored_px:
                stored_polys.append((area, stored_px))
            if area.get("world_polygon_3d"):
                proj_px = _project_3d_polygon(cd["K"], cd["R_w2c"], cd["t"],
                                              area["world_polygon_3d"], img_w)
                if proj_px is not None:
                    reprojected_polys.append((area, proj_px))
            else:
                corr_px = _flip_u(_project_world_polygon(H, area["world_polygon"]), img_w)
                reprojected_polys.append((area, corr_px))

        _setup_image_ax(axes[row, 0], frame_arr, img_w, img_h,
                        f"{cam_name} — camera_polygons (stored)")
        _add_legend(axes[row, 0],
                    _draw_polygons(axes[row, 0], stored_polys, img_w, img_h))

        _setup_image_ax(axes[row, 1], frame_arr, img_w, img_h,
                        f"{cam_name} — re-projected (3D doors / H floor)")
        _add_legend(axes[row, 1],
                    _draw_polygons(axes[row, 1], reprojected_polys, img_w, img_h))

    plt.suptitle(
        f"Area polygon verification — frame {frame_idx:04d}",
        fontsize=13, fontweight="bold", y=1.002,
    )
    plt.tight_layout(pad=0.5)
    composite_path = os.path.join(output_dir, "composite.png")
    fig.savefig(composite_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    print(f"\nComposite saved → {composite_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare raw vs corrected area polygon projections per camera."
    )
    parser.add_argument("--frames-dir", default=DEFAULT_FRAMES_DIR)
    parser.add_argument("--frame", type=int, default=DEFAULT_FRAME_IDX)
    parser.add_argument("--areas", default=AREAS_JSON)
    parser.add_argument("--output", default=OUTPUT_DIR)
    args = parser.parse_args()
    main(args.frames_dir, args.frame, args.areas, args.output)
