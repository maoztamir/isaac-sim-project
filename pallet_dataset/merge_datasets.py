"""
pallet_dataset/merge_datasets.py
==================================
Merges the real Roboflow dataset with the synthetic Isaac Sim dataset into one
combined YOLOv8 dataset, preserving the same folder layout.

Sources
-------
  REAL_DIR  : pallet_detection_dataset.v1i.yolov8  (real photos, Roboflow)
  SYNTH_DIR : pallet_dataset_yolo                  (synthetic, generate.py)

Output
------
  OUT_DIR/
    train/images/  train/labels/
    valid/images/  valid/labels/
    test/images/   test/labels/
    data.yaml

Images are prefixed with "real_" or "synth_" to make the source traceable and
guarantee no filename collisions.  Both datasets use class 0 = pallet so label
files are copied without modification.

Run with plain Python (no Isaac Sim):
    python3 pallet_dataset/merge_datasets.py
"""

import os
import shutil

# ── Knobs ─────────────────────────────────────────────────────────────────────
REAL_DIR  = "/media/storage/datasets/pallet_detection_dataset.v1i.yolov8"
SYNTH_DIR = "/media/storage/pallet_dataset_yolo"
OUT_DIR   = "/media/storage/datasets/pallet_dataset_merged"
# ─────────────────────────────────────────────────────────────────────────────

SPLITS = ["train", "valid", "test"]


def _copy_split_from(src_root, split, prefix, out_root):
    img_src = os.path.join(src_root, split, "images")
    lbl_src = os.path.join(src_root, split, "labels")
    img_dst = os.path.join(out_root, split, "images")
    lbl_dst = os.path.join(out_root, split, "labels")
    os.makedirs(img_dst, exist_ok=True)
    os.makedirs(lbl_dst, exist_ok=True)

    if not os.path.isdir(img_src):
        return 0

    count = 0
    for fname in sorted(os.listdir(img_src)):
        stem, ext = os.path.splitext(fname)
        if ext.lower() not in (".png", ".jpg", ".jpeg"):
            continue

        new_stem = f"{prefix}{stem}"
        shutil.copy2(
            os.path.join(img_src, fname),
            os.path.join(img_dst, f"{new_stem}{ext}"),
        )

        src_lbl = os.path.join(lbl_src, f"{stem}.txt")
        dst_lbl = os.path.join(lbl_dst, f"{new_stem}.txt")
        if os.path.exists(src_lbl):
            shutil.copy2(src_lbl, dst_lbl)
        else:
            open(dst_lbl, "w").close()

        count += 1

    return count


def _write_yaml(out_dir):
    # The real dataset has pallet only (class 0).
    # The synthetic dataset adds forklift (1) and box (2).
    # The merged yaml declares all three so a model can learn all classes.
    content = (
        "train: ../train/images\n"
        "val: ../valid/images\n"
        "test: ../test/images\n"
        "\n"
        "nc: 3\n"
        "names: ['pallet', 'forklift', 'box']\n"
    )
    path = os.path.join(out_dir, "data.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


def main():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)

    totals = {}
    for split in SPLITS:
        n_real  = _copy_split_from(REAL_DIR,  split, "real_",  OUT_DIR)
        n_synth = _copy_split_from(SYNTH_DIR, split, "synth_", OUT_DIR)
        totals[split] = (n_real, n_synth)

    yaml_path = _write_yaml(OUT_DIR)

    print(f"[merge_datasets] Output → {OUT_DIR}")
    print(f"  {'split':<8}  {'real':>6}  {'synth':>6}  {'total':>6}")
    print(f"  {'-'*34}")
    grand = 0
    for split in SPLITS:
        r, s = totals[split]
        print(f"  {split:<8}  {r:>6}  {s:>6}  {r+s:>6}")
        grand += r + s
    print(f"  {'-'*34}")
    print(f"  {'total':<8}  "
          f"{sum(r for r,_ in totals.values()):>6}  "
          f"{sum(s for _,s in totals.values()):>6}  "
          f"{grand:>6}")
    print(f"  yaml  → {yaml_path}")


if __name__ == "__main__":
    main()
