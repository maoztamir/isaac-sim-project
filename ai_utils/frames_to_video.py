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
    conda run -n isaac_scenario python frames_to_video.py /media/storage/replicator/_out_sdrec_2 --fps 35 --out /media/storage/replicator/_out_sdrec_10
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
DEFAULT_FPS = 30
DEFAULT_PRESET = "veryfast"


def find_frame_folders(root: str) -> list[tuple[str, list[str]]]:
    """Return (folder_path, sorted_frame_list) for every rgb/ folder containing images."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) != "rgb":
            continue
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
    preset: str,
    label: str,
    show_progress: bool = True,
) -> bool:
    """Encode a sorted frame list to MP4.

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
            "-nostats", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", "18",
            "-threads", "0",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            output,
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stderr_lines: list[str] = []
        def _drain(pipe: object, buf: list[str]) -> None:
            for line in pipe:
                buf.append(line)
        t = threading.Thread(target=_drain, args=(proc.stderr, stderr_lines), daemon=True)
        t.start()

        if show_progress:
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
                bar.update(total - last)
        else:
            proc.stdout.read()

        proc.wait()
        t.join()

        if proc.returncode != 0:
            err = "".join(stderr_lines)
            print(f"  [ERROR] ffmpeg failed for {label}:\n{err[-800:]}", file=sys.stderr)
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
    parser.add_argument("--preset", default=DEFAULT_PRESET,
                        choices=["ultrafast", "superfast", "veryfast", "faster",
                                 "fast", "medium", "slow"],
                        help=f"ffmpeg libx264 preset (default {DEFAULT_PRESET}). "
                             "Faster presets encode quicker at the cost of slightly "
                             "larger files.")
    parser.add_argument("--jobs", type=int, default=1,
                        help="Number of videos to encode in parallel (default 1). "
                             "Set to the number of camera streams for maximum speed.")
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
    parallel = args.jobs > 1 and not args.dry_run
    print(f"Found {total_vids} frame folder(s) under {root}")
    print(f"Preset: {args.preset}  |  Jobs: {args.jobs}  |  FPS: {args.fps}\n")

    tasks = [
        (folder, frames, make_output_path(folder, root, args.out))
        for folder, frames in folders
    ]

    if args.dry_run:
        for folder, frames, output in tasks:
            rel = os.path.relpath(folder, root)
            print(f"  {rel}  ({len(frames)} frames)  →  {output}")
        print(f"\n{total_vids} video(s) would be created.")
        return

    ok = 0

    if parallel:
        # Parallel mode: one overall bar, per-video progress suppressed to avoid
        # interleaved output from concurrent ffmpeg processes.
        def _encode(task):
            folder, frames, output = task
            rel = os.path.relpath(folder, root)
            success = frames_to_video(
                folder, frames, output, args.fps, args.preset,
                label=rel, show_progress=False,
            )
            return rel, output, success

        with tqdm(total=total_vids, desc="Encoding", unit="video",
                  ncols=80, colour="blue") as bar:
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                futures = {pool.submit(_encode, t): t for t in tasks}
                for fut in as_completed(futures):
                    rel, output, success = fut.result()
                    if success:
                        size_mb = os.path.getsize(output) / 1e6
                        tqdm.write(f"  ✓  {rel}  →  {output}  ({size_mb:.1f} MB)")
                        ok += 1
                    else:
                        tqdm.write(f"  ✗  {rel}  failed — see errors above")
                    bar.update(1)
    else:
        # Sequential mode: per-video progress bar.
        outer = tqdm(tasks, desc="Overall", unit="video",
                     ncols=80, colour="blue", position=0, leave=True)
        for folder, frames, output in outer:
            rel = os.path.relpath(folder, root)
            outer.set_postfix_str(rel[:40])
            tqdm.write(f"\n→  {rel}  ({len(frames)} frames)  →  {os.path.basename(output)}")
            success = frames_to_video(
                folder, frames, output, args.fps, args.preset,
                label=rel, show_progress=True,
            )
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
