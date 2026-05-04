"""
utils/replicator_capture.py
---------------------------
Isaac Sim Replicator frame-capture loop.

Attaches one render product + BasicWriter per camera prim and triggers
captures from a physics-step subscription.  Automatically stops after
MAX_FRAMES frames and prints ffmpeg commands to stitch MP4s.

Requires: omni.replicator.core, omni.physx  (Isaac Sim only)

Typical usage (inside Isaac Sim Script Editor):
    from utils.replicator_capture import ReplicatorCapture

    capture = ReplicatorCapture(
        cam_paths   = ["/World/Cameras/cam_0", "/World/Cameras/cam_1"],
        frames_root = "/path/to/frames",
        width=1920, height=1080,
    )
    capture.start()
    # ... simulation runs ...
    # capture stops automatically after MAX_FRAMES, or call:
    capture.stop()
"""

from __future__ import annotations

import asyncio
import os
import sys
import types

import omni.physx
import omni.replicator.core as rep


class ReplicatorCapture:
    """
    Manages Replicator render products and a physics-step capture callback.

    Parameters
    ----------
    cam_paths : list[str]
        USD prim paths of Camera prims to capture from.
    frames_root : str
        Parent directory.  Each camera writes to frames_root/<cam_name>/.
    width, height : int
        Render resolution in pixels.
    every_n_steps : int
        Capture one frame every N physics steps.
        At 30 Hz physics: every_n_steps=3 → ~10 fps output.
    max_frames : int
        Stop automatically after this many frames per camera.
    """

    # Persist across Script Editor re-runs so old subscriptions are released.
    _STATE_KEY = "_replicator_capture_state"

    def __init__(self,
                 cam_paths:     list[str],
                 frames_root:   str,
                 width:         int = 1920,
                 height:        int = 1080,
                 every_n_steps: int = 3,
                 max_frames:    int = 300):
        self.cam_paths     = cam_paths
        self.frames_root   = frames_root
        self.width         = width
        self.height        = height
        self.every_n_steps = every_n_steps
        self.max_frames    = max_frames

        self._render_products: list = []
        self._step_count  = 0
        self._frame_count = 0
        self._sub         = None

        # Release any leftover subscription from a previous run
        if self._STATE_KEY not in sys.modules:
            sys.modules[self._STATE_KEY] = types.SimpleNamespace(instance=None)
        _state = sys.modules[self._STATE_KEY]
        if _state.instance is not None:
            _state.instance.stop()
        _state.instance = self

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create render products + writers and begin capturing."""
        self._setup_render_products()
        self._sub = omni.physx.get_physx_interface().subscribe_physics_step_events(
            self._on_physics_step
        )
        fps = round(30 / self.every_n_steps)
        dur = self.max_frames / fps
        print(f"[ReplicatorCapture] Started: {len(self.cam_paths)} camera(s)"
              f"  ~{fps} fps  max {self.max_frames} frames (~{dur:.0f} s)")
        print(f"[ReplicatorCapture] Output → {self.frames_root}")

    def stop(self) -> None:
        """Release the physics subscription (capture stops immediately)."""
        if self._sub is not None:
            self._sub = None
            print(f"[ReplicatorCapture] Stopped after {self._frame_count} frame(s).")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_render_products(self) -> None:
        self._render_products.clear()
        for cam_path in self.cam_paths:
            cam_name   = cam_path.rsplit("/", 1)[-1]
            output_dir = os.path.join(self.frames_root, cam_name)
            os.makedirs(output_dir, exist_ok=True)

            rp     = rep.create.render_product(cam_path, (self.width, self.height))
            writer = rep.WriterRegistry.get("BasicWriter")
            writer.initialize(output_dir=output_dir, rgb=True)
            writer.attach([rp])

            self._render_products.append(rp)
            print(f"[ReplicatorCapture] {cam_name} → {output_dir}")

    def _on_physics_step(self, dt: float) -> None:
        self._step_count += 1
        if self._step_count % self.every_n_steps != 0:
            return

        if self._frame_count >= self.max_frames:
            self.stop()
            self._print_ffmpeg_commands()
            return

        self._frame_count += 1
        if self._frame_count % 30 == 0:
            print(f"[ReplicatorCapture] Frame {self._frame_count}/{self.max_frames}")

        asyncio.ensure_future(self._capture())

    async def _capture(self) -> None:
        await rep.orchestrator.step_async(pause_timeline=False)

    def _print_ffmpeg_commands(self) -> None:
        fps = round(30 / self.every_n_steps)
        print("\n── ffmpeg stitch commands ──────────────────────────────────")
        for cam_path in self.cam_paths:
            cam_name = cam_path.rsplit("/", 1)[-1]
            src_dir  = os.path.join(self.frames_root, cam_name)
            out_mp4  = os.path.join(self.frames_root, f"{cam_name}.mp4")
            print(f"  ffmpeg -r {fps} -i {src_dir}/rgb_%04d.png"
                  f" -c:v libx264 -pix_fmt yuv420p {out_mp4}")
        print("─────────────────────────────────────────────────────────────\n")
