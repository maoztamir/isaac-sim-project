"""
pallet_dataset/prepare_yolov8.py
=================================
Reorganises the raw pallet_dataset output into a YOLOv8-ready directory tree
that matches the Roboflow layout used by pallet_detection_dataset.v1i.yolov8.

Source layout (produced by generate.py):
    SRC_DIR/
      cam_south/rgb/000000.png  cam_south/labels/000000.txt
      cam_north/rgb/...         cam_north/labels/...
      cam_west/...
      cam_east/...
      classes.txt

Output layout (mirrors the reference dataset):
    OUT_DIR/
      train/images/   train/labels/
      valid/images/   valid/labels/
      test/images/    test/labels/
      data.yaml

Run with plain Python (no Isaac Sim):
    python3 pallet_dataset/prepare_yolov8.py
"""

import os
import random
import shutil

# ── Knobs ─────────────────────────────────────────────────────────────────────
SRC_DIR     = "/media/storage/pallet_dataset"
OUT_DIR     = "/media/storage/pallet_dataset_yolo"
TRAIN_RATIO = 0.70
VAL_RATIO   = 0.20
# TEST_RATIO  = remainder (1 - TRAIN_RATIO - VAL_RATIO)
SEED        = 42
# ─────────────────────────────────────────────────────────────────────────────


def _read_classes(src_dir):
    path = os.path.join(src_dir, "classes.txt")
    if not os.path.exists(path):
        return ["pallet"]
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]


def _collect_pairs(src_dir):
    """Return list of (img_src, lbl_src, unique_stem) for every camera frame."""
    pairs = []
    for cam in sorted(os.listdir(src_dir)):
        rgb_dir = os.path.join(src_dir, cam, "rgb")
        lbl_dir = os.path.join(src_dir, cam, "labels")
        if not os.path.isdir(rgb_dir):
            continue
        for fname in sorted(os.listdir(rgb_dir)):
            stem, ext = os.path.splitext(fname)
            if ext.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            img_src = os.path.join(rgb_dir, fname)
            lbl_src = os.path.join(lbl_dir, f"{stem}.txt")
            unique_stem = f"{cam}_{stem}"
            pairs.append((img_src, lbl_src, unique_stem))
    return pairs


def _split(pairs, train_ratio, val_ratio, seed):
    rng = random.Random(seed)
    shuffled = list(pairs)
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * train_ratio)
    n_val   = int(n * val_ratio)
    return (
        shuffled[:n_train],
        shuffled[n_train:n_train + n_val],
        shuffled[n_train + n_val:],
    )


def _copy_split(pairs, out_dir, split_name):
    img_out = os.path.join(out_dir, split_name, "images")
    lbl_out = os.path.join(out_dir, split_name, "labels")
    os.makedirs(img_out, exist_ok=True)
    os.makedirs(lbl_out, exist_ok=True)

    for img_src, lbl_src, stem in pairs:
        ext = os.path.splitext(img_src)[1]
        shutil.copy2(img_src, os.path.join(img_out, f"{stem}{ext}"))

        dst_lbl = os.path.join(lbl_out, f"{stem}.txt")
        if os.path.exists(lbl_src):
            shutil.copy2(lbl_src, dst_lbl)
        else:
            open(dst_lbl, "w").close()  # empty label = background frame

    return len(pairs)


def _write_yaml(out_dir, classes):
    names_list = "[" + ", ".join(f"'{c}'" for c in classes) + "]"
    content = (
        f"train: ../train/images\n"
        f"val: ../valid/images\n"
        f"test: ../test/images\n"
        f"\n"
        f"nc: {len(classes)}\n"
        f"names: {names_list}\n"
    )
    yaml_path = os.path.join(out_dir, "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(content)
    return yaml_path


def main():
    classes = _read_classes(SRC_DIR)
    pairs   = _collect_pairs(SRC_DIR)

    if not pairs:
        print(f"[prepare_yolov8] No images found in {SRC_DIR}")
        return

    train_pairs, val_pairs, test_pairs = _split(pairs, TRAIN_RATIO, VAL_RATIO, SEED)

    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)

    n_train = _copy_split(train_pairs, OUT_DIR, "train")
    n_val   = _copy_split(val_pairs,   OUT_DIR, "valid")
    n_test  = _copy_split(test_pairs,  OUT_DIR, "test")

    yaml_path = _write_yaml(OUT_DIR, classes)

    print(f"[prepare_yolov8] {n_train + n_val + n_test} frames from {SRC_DIR}")
    print(f"  train : {n_train}")
    print(f"  valid : {n_val}")
    print(f"  test  : {n_test}")
    print(f"  yaml  : {yaml_path}")
    print(f"[prepare_yolov8] Done → {OUT_DIR}")


if __name__ == "__main__":
    main()
