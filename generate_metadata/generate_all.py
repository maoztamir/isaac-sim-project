"""
generate_all.py
---------------
Runs all four metadata generation steps in order:

  1. generate_homography.py    → output/homography/<cam>.json + .npz
  2. generate_area_polygons.py → output/area_polygons.json
  3. generate_bev_map.py       → output/bev_map.png
  4. verify_area_polygons.py   → output/area_verification/<cam>.png + composite.png

Camera positions are read from tests/camera_position.usd (set manually in Isaac Sim).
All warehouse geometry comes from warehouse_sim/config.py.
Verification frames are read from FRAMES_DIR (Replicator BasicWriter output).

Usage:
    conda run -n isaac_scenario python generate_metadata/generate_all.py
    conda run -n isaac_scenario python generate_metadata/generate_all.py \\
        --frames-dir /media/storage/replicator/_out_sdrec_2 --frame 500

Pass --help for all output path overrides.
"""

import argparse
import os
import sys
import time

# ── Path setup ────────────────────────────────────────────────────────────────
_project_root = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Import each module's main() directly to avoid subprocess overhead and share
# the same Python process / import cache.
import generate_metadata.generate_homography    as _hom
import generate_metadata.generate_area_polygons as _area
import generate_metadata.generate_bev_map       as _bev
import generate_metadata.verify_area_polygons   as _ver


def main():
    parser = argparse.ArgumentParser(
        description="Run all warehouse metadata generators in sequence."
    )
    parser.add_argument(
        "--areas-output", default=_area.DEFAULT_OUTPUT,
        help=f"Path for area_polygons.json (default: {_area.DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--bev-output", default=_bev.DEFAULT_OUTPUT,
        help=f"Path for bev_map.png (default: {_bev.DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--frames-dir", default=_ver.DEFAULT_FRAMES_DIR,
        help=f"Replicator frames root (default: {_ver.DEFAULT_FRAMES_DIR})",
    )
    parser.add_argument(
        "--frame", type=int, default=_ver.DEFAULT_FRAME_IDX,
        help=f"Frame index for verification images (default: {_ver.DEFAULT_FRAME_IDX})",
    )
    args = parser.parse_args()

    t0 = time.time()

    # ── Step 1: homography ────────────────────────────────────────────────────
    print("=" * 60)
    print("STEP 1 — Homography")
    print(f"  Source : {_hom.CAMERAS_USD}")
    print(f"  Output : {_hom.OUTPUT_DIR}/")
    print("=" * 60)
    _hom.main()

    # ── Step 2: area polygons ─────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("STEP 2 — Area polygons")
    print(f"  Homography: {_area.HOMOGRAPHY_DIR}/")
    print(f"  Output    : {args.areas_output}")
    print("=" * 60)
    _area.main(args.areas_output)

    # ── Step 3: BEV map ───────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("STEP 3 — Bird's-eye-view map")
    print(f"  Homography: {_bev.HOMOGRAPHY_DIR}/")
    print(f"  Output    : {args.bev_output}")
    print("=" * 60)
    _bev.main(args.bev_output)

    # ── Step 4: visual verification ───────────────────────────────────────────
    print()
    print("=" * 60)
    print("STEP 4 — Visual area verification")
    print(f"  Frames : {args.frames_dir}  (frame {args.frame:04d})")
    print(f"  Output : {_ver.OUTPUT_DIR}/")
    print("=" * 60)
    _ver.main(args.frames_dir, args.frame, args.areas_output, _ver.OUTPUT_DIR)

    elapsed = time.time() - t0
    print()
    print(f"All done in {elapsed:.1f}s")
    print(f"  Homography   : {_hom.OUTPUT_DIR}/")
    print(f"  Areas        : {args.areas_output}")
    print(f"  BEV map      : {args.bev_output}")
    print(f"  Verification : {_ver.OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
