#!/usr/bin/env python3
"""
frames_to_video.py — Convert Isaac Sim Replicator frame folders to MP4 videos.

For each subfolder under ROOT that directly contains image files (PNG/JPG),
an MP4 is written alongside that folder named after its parent hierarchy.

Expected layout:
    ROOT/
        Replicator/rgb/rgb_0000.png ...
        Replicator_01/rgb/rgb_0000.png ...
        Replicator_02/rgb/rgb_0000.png ...

Usage:
    python frames_to_video.py /media/storage/replicator/_out_sdrec
    python frames_to_video.py /media/storage/replicator/_out_sdrec --fps 24 --out /tmp/videos
    python frames_to_video.py /media/storage/replicator/_out_sdrec --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
DEFAULT_FPS = 30


def find_frame_folders(root: str) -> list[tuple[str, list[str]]]:
    """Return (folder_path, sorted_frame_list) for every folder containing images."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        frames = sorted(
            [f for f in filenames if os.path.splitext(f)[1].lower() in IMAGE_EXTS],
            key=lambda n: [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", n)],
        )
        if frames:
            results.append((dirpath, frames))
    return results


def make_output_path(frame_folder: str, root: str, out_dir: str | None) -> str:
    """Derive the MP4 path from the frame folder's position under root."""
    rel = os.path.relpath(frame_folder, root)
    # e.g. "Replicator_03/rgb" → "Replicator_03_rgb"
    slug = rel.replace(os.sep, "_")
    filename = slug + ".mp4"
    base = out_dir if out_dir else root
    return os.path.join(base, filename)


def frames_to_video(frame_folder: str, frames: list[str], output: str, fps: int) -> bool:
    """Call ffmpeg to encode a sorted frame list into an MP4. Returns True on success."""
    # Write a temporary concat list so ffmpeg gets frames in exact sorted order
    # regardless of filesystem ordering.
    list_path = os.path.join(frame_folder, "_ffmpeg_input.txt")
    try:
        with open(list_path, "w") as fh:
            for f in frames:
                fh.write(f"file '{os.path.join(frame_folder, f)}'\n")
                fh.write(f"duration {1/fps:.6f}\n")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # ensure even dimensions
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [ERROR] ffmpeg failed:\n{result.stderr[-800:]}", file=sys.stderr)
            return False
        return True
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)


def main():
    parser = argparse.ArgumentParser(description="Convert Replicator frame folders to MP4.")
    parser.add_argument("root", help="Root folder containing Replicator output folders.")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help=f"Frames per second (default {DEFAULT_FPS}).")
    parser.add_argument("--out", default=None, help="Output directory for MP4 files (default: alongside each frame folder's parent).")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without running ffmpeg.")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.exit(f"ERROR: {root} is not a directory.")

    folders = find_frame_folders(root)
    if not folders:
        sys.exit("No image files found under the given root.")

    print(f"Found {len(folders)} frame folder(s) under {root}\n")

    ok = 0
    for folder, frames in folders:
        output = make_output_path(folder, root, args.out)
        rel = os.path.relpath(folder, root)
        print(f"  {rel}  ({len(frames)} frames)  →  {os.path.basename(output)}")

        if args.dry_run:
            continue

        success = frames_to_video(folder, frames, output, args.fps)
        if success:
            size_mb = os.path.getsize(output) / 1e6
            print(f"    ✓  {output}  ({size_mb:.1f} MB)")
            ok += 1
        else:
            print(f"    ✗  failed — see errors above")

    if not args.dry_run:
        print(f"\n{ok}/{len(folders)} videos created.")


if __name__ == "__main__":
    main()
