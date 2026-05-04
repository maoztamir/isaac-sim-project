"""
tests/export_cameras.py
=======================
Run in Isaac Sim Script Editor AFTER main.py has built and started the scenario.

  Phase 1 — exports homography JSON + NPZ for every camera in /World/Cameras
             to scenario_creation/output/homography/  (feeds generate_bev_map.py,
             generate_area_polygons.py without any changes to those scripts).

  Phase 2 — captures RGB frames from every camera via Replicator, saving PNGs
             to tests/output/frames/<cam_name>/.  Stops after MAX_FRAMES and
             prints ffmpeg commands to stitch MP4s.

Re-run this script at any time to stop the current capture and restart it.
"""

# ── Knobs ──────────────────────────────────────────────────────────────────────
CAMERA_PARENT_PATH    = "/World/Cameras"
IMAGE_WIDTH           = 1920
IMAGE_HEIGHT          = 1080
CAPTURE_EVERY_N_STEPS = 3      # physics steps between captures (~10 fps @ 30 Hz)
MAX_FRAMES            = 300    # frames per camera before auto-stop (~30 s)
# ──────────────────────────────────────────────────────────────────────────────

import os
import sys

_project_root  = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"
_scenario_root = "/home/ubuntu/isaac_sim_samples/scenario_creation"

# Ensure project root is first on sys.path so `utils` is importable
if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

# Reload utils modules so Script Editor re-runs pick up code changes
for _k in [k for k in sys.modules if k.startswith("utils")]:
    del sys.modules[_k]

import omni.usd
from utils.camera_usd        import export_cameras_from_stage
from utils.replicator_capture import ReplicatorCapture

# ── Paths ──────────────────────────────────────────────────────────────────────
_homography_dir = os.path.join(_scenario_root, "output", "homography")
_frames_root    = os.path.join(_project_root,  "tests",  "output", "frames")

# ── Phase 1: homography export ─────────────────────────────────────────────────
stage     = omni.usd.get_context().get_stage()
cam_paths = export_cameras_from_stage(
    stage,
    output_dir  = _homography_dir,
    width       = IMAGE_WIDTH,
    height      = IMAGE_HEIGHT,
    parent_path = CAMERA_PARENT_PATH,
)

# ── Phase 2: Replicator frame capture ──────────────────────────────────────────
if cam_paths:
    capture = ReplicatorCapture(
        cam_paths     = cam_paths,
        frames_root   = _frames_root,
        width         = IMAGE_WIDTH,
        height        = IMAGE_HEIGHT,
        every_n_steps = CAPTURE_EVERY_N_STEPS,
        max_frames    = MAX_FRAMES,
    )
    capture.start()
else:
    print("[export_cameras] No cameras found — run main.py first.")
