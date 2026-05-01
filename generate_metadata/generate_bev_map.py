"""
generate_bev_map.py
-------------------
Generates a metric bird's-eye-view (BEV) map of the warehouse showing:
  - Warehouse boundary and navigable area
  - Docking doors and loading / staging zones
  - Shelf columns and aisles
  - Camera positions and FOV footprints projected onto the floor

Reads homography files from output/homography/ (produced by generate_homography.py).
All geometry comes from warehouse_sim/config.py.

Usage:
    conda run -n isaac_scenario python generate_metadata/generate_bev_map.py
    conda run -n isaac_scenario python generate_metadata/generate_bev_map.py --output /tmp/map.png

Dependencies: numpy, matplotlib
"""

import argparse
import json
import math
import os
import sys

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ── Path setup ────────────────────────────────────────────────────────────────
_project_root = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import warehouse_sim.config as WC

# ── Derived geometry (all from WC) ───────────────────────────────────────────
# Loading zones — one per door
LOADING_ZONES = [
    {
        "cx":   WC.WAREHOUSE_CX + off,
        "x0":   WC.WAREHOUSE_CX + off - WC.LOAD_W / 2,
        "x1":   WC.WAREHOUSE_CX + off + WC.LOAD_W / 2,
        "y0":   WC.WALL_Y_MIN,
        "y1":   WC.WALL_Y_MIN + WC.LOAD_D,
    }
    for off in WC.GATE_OFFSETS
]

# Staging zones — one per door
STAGING_ZONES = [
    {
        "x0": WC.WAREHOUSE_CX + off - WC.STAGING_W / 2,
        "x1": WC.WAREHOUSE_CX + off + WC.STAGING_W / 2,
        "y0": WC.STAGING_Y_NEAR,
        "y1": WC.STAGING_Y_FAR,
    }
    for off in WC.GATE_OFFSETS
]

# Shelf column / aisle edges — 12-edge list matching actual shelf detection.
# Even segment index (i%2==0) = shelf column; odd = aisle.
SHELF_COL_EDGES = [
    -24.53, -20.94,
    -19.80, -15.99,
    -14.85, -11.03,
     -9.89,  -6.07,
     -4.93,  -1.12,
      0.02,   3.66,
]
SHELF_Y_MIN = WC.ZONES["ShelvesArea"][2]   # ≈ 3.60
SHELF_Y_MAX = WC.ZONES["ShelvesArea"][3]   # ≈ 28.80

HOMOGRAPHY_DIR = os.path.join(_project_root, "output", "homography")
DEFAULT_OUTPUT = os.path.join(_project_root, "output", "bev_map.png")

_PALETTE = ["#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
            "#9B59B6", "#1ABC9C", "#E67E22", "#34495E"]


# ── Camera loading ────────────────────────────────────────────────────────────

def load_all_cameras():
    """Read every *.json from HOMOGRAPHY_DIR."""
    if not os.path.isdir(HOMOGRAPHY_DIR):
        return []
    cameras = []
    for fname in sorted(os.listdir(HOMOGRAPHY_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(HOMOGRAPHY_DIR, fname)) as f:
            d = json.load(f)
        pos = d["position_world"]
        res = d.get("image_resolution", [1920, 1080])
        cameras.append(dict(
            name=d["camera"],
            tx=pos[0], ty=pos[1], tz=pos[2],
            image_width=res[0], image_height=res[1],
            H_inv=np.array(d["H_inv"]),
        ))
    return cameras


def _cam_color(cameras, name):
    idx = next((i for i, c in enumerate(cameras) if c["name"] == name), 0)
    return _PALETTE[idx % len(_PALETTE)]


def fov_footprint(H_inv, img_w, img_h):
    """Project image corners through H_inv to floor-plane FOV polygon."""
    corners = [[0, 0], [img_w, 0], [img_w, img_h], [0, img_h]]
    pts = []
    for u, v in corners:
        p = H_inv @ np.array([u, v, 1.0])
        pts.append(p[:2] / p[2])
    pts = np.array(pts)
    # Clip to warehouse bounds so far-field extrapolation stays on canvas
    pts[:, 0] = np.clip(pts[:, 0], WC.WALL_X_MIN - 2, WC.WALL_X_MAX + 2)
    pts[:, 1] = np.clip(pts[:, 1], WC.WALL_Y_MIN - 2, WC.WALL_Y_MAX + 2)
    return pts


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _add_rect(ax, x0, x1, y0, y1, facecolor, edgecolor, lw=1.5,
              linestyle="-", alpha=1.0, zorder=3, label=None):
    patch = plt.Polygon(
        [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        closed=True, fill=True,
        facecolor=facecolor, edgecolor=edgecolor,
        linewidth=lw, linestyle=linestyle, alpha=alpha, zorder=zorder,
        label=label,
    )
    ax.add_patch(patch)
    return patch


# ── Main ──────────────────────────────────────────────────────────────────────

def main(output_path):
    cameras = load_all_cameras()
    if not cameras:
        print(f"No homography JSON files found in {HOMOGRAPHY_DIR}")
        print("Run generate_homography.py first.")
        return
    print(f"Loaded {len(cameras)} camera(s) from {HOMOGRAPHY_DIR}")

    fig, ax = plt.subplots(figsize=(14, 18))
    ax.set_aspect("equal")

    # Warehouse boundary
    _add_rect(ax, WC.WALL_X_MIN, WC.WALL_X_MAX, WC.WALL_Y_MIN, WC.WALL_Y_MAX,
              "#F5F5F0", "#333333", lw=2.5, zorder=1)

    # Navigable area (inside wall margin)
    nav_rect = plt.Polygon(
        [[WC.NAV_X_MIN, WC.NAV_Y_MIN], [WC.NAV_X_MAX, WC.NAV_Y_MIN],
         [WC.NAV_X_MAX, WC.NAV_Y_MAX], [WC.NAV_X_MIN, WC.NAV_Y_MAX]],
        closed=True, fill=False,
        edgecolor="#AAAAAA", linewidth=0.8, linestyle=":", zorder=2
    )
    ax.add_patch(nav_rect)

    # Loading zones
    for i, lz in enumerate(LOADING_ZONES):
        _add_rect(ax, lz["x0"], lz["x1"], lz["y0"], lz["y1"],
                  "#FFF3CD", "#E67E22", lw=2.0, zorder=3)
        label = "LOADING" if i == 1 else f"L{i+1}"
        ax.text((lz["x0"] + lz["x1"]) / 2, (lz["y0"] + lz["y1"]) / 2,
                label, ha="center", va="center",
                fontsize=8, fontweight="bold", color="#E67E22", zorder=6)

    # Staging zones
    for i, sz in enumerate(STAGING_ZONES):
        _add_rect(ax, sz["x0"], sz["x1"], sz["y0"], sz["y1"],
                  "#EAF4FB", "#2980B9", lw=2.0, linestyle="--", zorder=3)
        label = "STAGING" if i == 1 else f"S{i+1}"
        ax.text((sz["x0"] + sz["x1"]) / 2, (sz["y0"] + sz["y1"]) / 2,
                label, ha="center", va="center",
                fontsize=8, fontweight="bold", color="#2980B9", zorder=6)

    # Shelving area outline
    shelving_rect = plt.Polygon(
        [[SHELF_COL_EDGES[0],  SHELF_Y_MIN], [SHELF_COL_EDGES[-1], SHELF_Y_MIN],
         [SHELF_COL_EDGES[-1], SHELF_Y_MAX], [SHELF_COL_EDGES[0],  SHELF_Y_MAX]],
        closed=True, fill=False,
        edgecolor="#27AE60", linewidth=2.5, linestyle="-", zorder=4
    )
    ax.add_patch(shelving_rect)
    ax.text((SHELF_COL_EDGES[0] + SHELF_COL_EDGES[-1]) / 2, SHELF_Y_MAX + 0.5,
            "SHELVING", ha="center", va="bottom",
            fontsize=9, fontweight="bold", color="#27AE60", zorder=6)

    # Shelf columns (even segment index) — shaded; aisles left blank
    for i in range(len(SHELF_COL_EDGES) - 1):
        x0 = SHELF_COL_EDGES[i]
        x1 = SHELF_COL_EDGES[i + 1]
        if i % 2 == 0:
            _add_rect(ax, x0, x1, SHELF_Y_MIN, SHELF_Y_MAX,
                      "#C8D8C8", "#7A9A7A", lw=0.8, zorder=3,
                      label="Shelving" if i == 0 else None)

    # Docking doors (thin strip on south wall)
    for i, off in enumerate(WC.GATE_OFFSETS):
        door_cx = WC.WAREHOUSE_CX + off
        _add_rect(ax, door_cx - 1.0, door_cx + 1.0,
                  WC.WALL_Y_MIN, WC.WALL_Y_MIN + 0.3,
                  "#F1C40F", "#B7950B", lw=1.0, zorder=4,
                  label="Docking door" if i == 0 else None)

    # Camera FOV footprints and positions
    for cam in cameras:
        name  = cam["name"]
        cx, cy = cam["tx"], cam["ty"]
        color = _cam_color(cameras, name)
        footprint = fov_footprint(cam["H_inv"], cam["image_width"], cam["image_height"])

        fov_poly = plt.Polygon(
            footprint, closed=True, fill=True,
            facecolor=color, alpha=0.15,
            edgecolor=color, linewidth=1.5, zorder=5
        )
        ax.add_patch(fov_poly)
        for wx, wy in footprint:
            ax.plot([cx, wx], [cy, wy], color=color, linewidth=0.6, alpha=0.4, zorder=5)

        ax.plot(cx, cy, marker="^", markersize=12, color=color,
                markeredgecolor="white", markeredgewidth=1.2, zorder=10)
        label_dx = 0.6 if cx > WC.WAREHOUSE_CX else -0.6
        label_dy = 0.8 if cy > WC.WAREHOUSE_CY else -1.2
        ax.annotate(
            name,
            xy=(cx, cy), xytext=(cx + label_dx, cy + label_dy),
            fontsize=8, fontweight="bold", color=color,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor=color, alpha=0.85),
            zorder=11
        )

    # Metric grid (5 m spacing)
    for xt in range(math.ceil(WC.WALL_X_MIN / 5) * 5, int(WC.WALL_X_MAX) + 1, 5):
        ax.axvline(xt, color="#DDDDDD", linewidth=0.5, zorder=0)
    for yt in range(math.ceil(WC.WALL_Y_MIN / 5) * 5, int(WC.WALL_Y_MAX) + 1, 5):
        ax.axhline(yt, color="#DDDDDD", linewidth=0.5, zorder=0)

    pad = 3.0
    ax.set_xlim(WC.WALL_X_MIN - pad, WC.WALL_X_MAX + pad)
    ax.set_ylim(WC.WALL_Y_MIN - pad, WC.WALL_Y_MAX + pad)
    ax.set_xlabel("X  (metres)", fontsize=11)
    ax.set_ylabel("Y  (metres)", fontsize=11)
    ax.set_title("Warehouse Bird's-Eye Map — Camera FOV Footprints", fontsize=13, pad=12)

    legend_handles = [
        mpatches.Patch(facecolor="#F5F5F0", edgecolor="#333333", label="Warehouse boundary"),
        mpatches.Patch(facecolor="#FFF3CD", edgecolor="#E67E22", label="Loading zones (×3)"),
        mpatches.Patch(facecolor="#EAF4FB", edgecolor="#2980B9", label="Staging zones (×3)"),
        mpatches.Patch(facecolor="#C8D8C8", edgecolor="#27AE60", label="Shelf columns (×6)"),
        mpatches.Patch(facecolor="#F1C40F", edgecolor="#B7950B", label="Docking doors"),
    ]
    for cam in cameras:
        color = _cam_color(cameras, cam["name"])
        legend_handles.append(
            mpatches.Patch(facecolor=color, alpha=0.4, edgecolor=color,
                           label=f"{cam['name']} FOV  z={cam['tz']:.1f}m")
        )
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8,
              framealpha=0.9, edgecolor="#CCCCCC")

    # 10 m scale bar
    sb_x0 = WC.WALL_X_MIN + 1.0
    sb_y  = WC.WALL_Y_MIN - 1.8
    ax.annotate("", xy=(sb_x0 + 10, sb_y), xytext=(sb_x0, sb_y),
                arrowprops=dict(arrowstyle="<->", color="#555555", lw=1.5))
    ax.text(sb_x0 + 5, sb_y + 0.4, "10 m", ha="center", va="bottom",
            fontsize=8, color="#555555")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Bird's-eye map saved → {output_path}")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate metric BEV warehouse map.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"Output PNG path (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()
    main(args.output)
