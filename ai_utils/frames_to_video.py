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
    conda run -n isaac_scenario python frames_to_video.py /media/storage/replicator/_out_sdrec_2 --fps 35 --out /media/storage/replicator/_out_sdrec_2
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading

from tqdm import tqdm

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
    """Derive the MP4 path from the frame folder's position under root.

    Default (no --out): MP4 is written next to the frame folder, in its
    parent directory, named after the frame folder itself.
    Custom --out: MP4 is written into out_dir using a slug of the relative path.
    """
    if out_dir:
        rel  = os.path.relpath(frame_folder, root)
        slug = rel.replace(os.sep, "_")
        return os.path.join(out_dir, slug + ".mp4")
    else:
        parent      = os.path.dirname(frame_folder)
        folder_name = os.path.basename(frame_folder)
        return os.path.join(parent, folder_name + ".mp4")


def frames_to_video(
    frame_folder: str,
    frames: list[str],
    output: str,
    fps: int,
    label: str,
) -> bool:
    """Encode a sorted frame list to MP4 with a tqdm progress bar.

    Uses ffmpeg's -progress pipe:1 to stream frame counts to stdout so
    the bar updates in real time without polling.
    Returns True on success.
    """
    list_path = os.path.join(frame_folder, "_ffmpeg_input.txt")
    total = len(frames)
    try:
        with open(list_path, "w") as fh:
            for f in frames:
                fh.write(f"file '{os.path.join(frame_folder, f)}'\n")
                fh.write(f"duration {1/fps:.6f}\n")

        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        cmd = [
            "ffmpeg", "-y",
            "-nostats", "-loglevel", "error",   # keep stderr quiet; errors only
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-progress", "pipe:1",              # stream key=value progress to stdout
            output,
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Drain stderr on a background thread to prevent pipe buffer deadlock.
        stderr_lines: list[str] = []
        def _drain(pipe: object, buf: list[str]) -> None:
            for line in pipe:
                buf.append(line)
        t = threading.Thread(target=_drain, args=(proc.stderr, stderr_lines), daemon=True)
        t.start()

        with tqdm(
            total=total,
            desc=f"  {label}",
            unit="fr",
            ncols=80,
            colour="green",
            leave=True,
        ) as bar:
            last = 0
            for line in proc.stdout:
                if line.startswith("frame="):
                    try:
                        n = int(line.split("=", 1)[1].strip())
                        bar.update(n - last)
                        last = n
                    except ValueError:
                        pass
            # Ensure bar reaches 100 % even if ffmpeg omits the final progress line
            bar.update(total - last)

        proc.wait()
        t.join()

        if proc.returncode != 0:
            err = "".join(stderr_lines)
            print(f"  [ERROR] ffmpeg failed:\n{err[-800:]}", file=sys.stderr)
            return False
        return True

    finally:
        if os.path.exists(list_path):
            os.remove(list_path)


def main():
    parser = argparse.ArgumentParser(description="Convert Replicator frame folders to MP4.")
    parser.add_argument("root", help="Root folder containing Replicator output folders.")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS,
                        help=f"Frames per second (default {DEFAULT_FPS}).")
    parser.add_argument("--out", default=None,
                        help="Output directory for MP4 files "
                             "(default: same directory as each frame folder).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without running ffmpeg.")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.exit(f"ERROR: {root} is not a directory.")

    folders = find_frame_folders(root)
    if not folders:
        sys.exit("No image files found under the given root.")

    total_vids = len(folders)
    print(f"Found {total_vids} frame folder(s) under {root}\n")

    ok = 0
    outer = tqdm(
        folders,
        desc="Overall",
        unit="video",
        ncols=80,
        colour="blue",
        position=0,
        leave=True,
    )
    for folder, frames in outer:
        output = make_output_path(folder, root, args.out)
        rel    = os.path.relpath(folder, root)
        outer.set_postfix_str(rel[:40])
        tqdm.write(f"\n→  {rel}  ({len(frames)} frames)  →  {os.path.basename(output)}")

        if args.dry_run:
            ok += 1
            continue

        success = frames_to_video(folder, frames, output, args.fps, label=rel)
        if success:
            size_mb = os.path.getsize(output) / 1e6
            tqdm.write(f"   ✓  {output}  ({size_mb:.1f} MB)")
            ok += 1
        else:
            tqdm.write(f"   ✗  failed — see errors above")

    outer.close()
    print(f"\n{ok}/{total_vids} videos created.")


if __name__ == "__main__":
    main()
