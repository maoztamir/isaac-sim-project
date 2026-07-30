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
    # Basic (sequential, veryfast preset):
    python frames_to_video.py /media/storage/replicator/_out_sdrec6 --fps 35 --out /media/storage/replicator/videos

    # Parallel — encode all cameras at once (fastest):
    python frames_to_video.py /media/storage/replicator/_out_sdrec6 --fps 35 --out /media/storage/replicator/videos --jobs 4

    # Parallel + ultrafast preset (biggest speed gain, slightly larger files):
    python frames_to_video.py /media/storage/replicator/_out_sdrec6 --fps 35 --out /media/storage/replicator/videos --jobs 4 --preset ultrafast

    # Dry run — print what would be encoded without running ffmpeg:
    python frames_to_video.py /media/storage/replicator/_out_sdrec6 --dry-run
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
    master_bar: "tqdm | None" = None,
) -> bool:
    """Encode a sorted frame list to MP4.

    Streams frame counts from ffmpeg's -progress pipe and updates *master_bar*
    (a shared tqdm instance) so the caller can show a unified ETA across all
    videos. Thread-safe: multiple workers can update the same bar in parallel.
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

        last = 0
        for line in proc.stdout:
            if line.startswith("frame="):
                try:
                    n = int(line.split("=", 1)[1].strip())
                    if master_bar is not None:
                        master_bar.update(n - last)
                    last = n
                except ValueError:
                    pass
        # Flush any remaining frames ffmpeg didn't report in the final tick
        if master_bar is not None and total > last:
            master_bar.update(total - last)

        proc.wait()
        t.join()

        if proc.returncode != 0:
            err = "".join(stderr_lines)
            tqdm.write(f"  [ERROR] ffmpeg failed for {label}:\n{err[-800:]}", file=sys.stderr)
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

    total_frames = sum(len(f) for _, f, _ in tasks)
    ok = 0

    # One master bar counting total frames across all videos.
    # tqdm derives ETA from encoding speed (fr/s), which is far more accurate
    # than counting videos (which vary in length).
    with tqdm(
        total=total_frames,
        desc="Encoding",
        unit="fr",
        unit_scale=True,
        ncols=90,
        colour="blue",
        dynamic_ncols=False,
    ) as master:

        if parallel:
            def _encode(task):
                folder, frames, output = task
                rel = os.path.relpath(folder, root)
                master.set_postfix_str(
                    f"{ok+1}/{total_vids} active", refresh=False
                )
                success = frames_to_video(
                    folder, frames, output, args.fps, args.preset,
                    label=rel, master_bar=master,
                )
                return rel, output, success

            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                futures = {pool.submit(_encode, t): t for t in tasks}
                for fut in as_completed(futures):
                    rel, output, success = fut.result()
                    if success:
                        size_mb = os.path.getsize(output) / 1e6
                        tqdm.write(f"  ✓  {rel}  ({size_mb:.1f} MB)  →  {output}")
                        ok += 1
                    else:
                        tqdm.write(f"  ✗  {rel}  failed — see errors above")
                    master.set_postfix_str(f"{ok}/{total_vids} done", refresh=True)

        else:
            for folder, frames, output in tasks:
                rel = os.path.relpath(folder, root)
                tqdm.write(f"\n→  {rel}  ({len(frames)} frames)")
                master.set_description(rel[-35:])
                success = frames_to_video(
                    folder, frames, output, args.fps, args.preset,
                    label=rel, master_bar=master,
                )
                if success:
                    size_mb = os.path.getsize(output) / 1e6
                    tqdm.write(f"   ✓  {output}  ({size_mb:.1f} MB)")
                    ok += 1
                else:
                    tqdm.write(f"   ✗  failed — see errors above")
                master.set_postfix_str(f"{ok}/{total_vids} done", refresh=True)

    print(f"\n{ok}/{total_vids} videos created.")


if __name__ == "__main__":
    main()
