"""
Pallet dataset generation config.

All paths use the locally-cached asset directories so no Nucleus connection is required.
scale_factor: 1.0 for assets authored in metres, 0.01 for assets authored in cm.
"""

import os

# ── Local asset cache roots ───────────────────────────────────────────────────
LOCAL_5_1 = "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1"
LOCAL_5_0 = "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.0"

# ── Output ────────────────────────────────────────────────────────────────────
OUTPUT_DIR   = "/media/storage/pallet_dataset"
NUM_FRAMES   = 3600   # targets ~5,300 synthetic images ≈ 16% supplement to 27,948 real
RESOLUTION   = (960, 540)   # lower than 1280×720 to reduce RTX VRAM per render product
SEED         = 42
RT_SUBFRAMES = 1            # 4 subframes × 4 cameras was the main VRAM pressure

# ── Asset pool cap ───────────────────────────────────────────────────────────
# Each unique asset loaded stays in the RTX texture/mesh cache for the whole
# run.  Cycling all 60+ pallets fills VRAM.  Cap the pool to a random sample
# chosen once at startup; set to None to use the full list.
ASSET_POOL_SIZE = 20   # max unique pallet types per run

# ── Object density — unified budget ──────────────────────────────────────────
# Total objects per frame across all classes (pallets + forklifts + boxes).
MIN_OBJECTS           = 2
MAX_OBJECTS           = 5
MAX_FORKLIFTS         = 2     # VRAM guard: articulated robot meshes are large
MAX_OBJECTS_PER_IMAGE = 6     # discard filter (buffer above MAX_OBJECTS budget)
MAX_PALLETS           = 5     # pallet slot pre-allocation count (= MAX_OBJECTS)

# ── Placement geometry ────────────────────────────────────────────────────────
# Cluster centre is sampled from CLUSTER_* bounds; individual pallets scatter
# within SCATTER_RADIUS; all positions are clamped to FLOOR_* (warehouse floor).
CLUSTER_X_MIN         = -19.5   # warehouse X_min + SCATTER_RADIUS
CLUSTER_X_MAX         =   0.5   # warehouse X_max - SCATTER_RADIUS
CLUSTER_Y_MIN         = -15.5
CLUSTER_Y_MAX         =   4.5
FLOOR_X_MIN           = -22.0   # hard warehouse floor limits (for clamping)
FLOOR_X_MAX           =   3.0
FLOOR_Y_MIN           = -18.0
FLOOR_Y_MAX           =   7.0
SCATTER_RADIUS        =   2.5   # max radial spread of pallets from cluster centre (m)
MIN_PALLET_SEPARATION =   0.8   # min distance between pallet centres (m)

# ── Cameras ───────────────────────────────────────────────────────────────────
N_CAMERAS           = 2     # 4 simultaneous RTX render products consumed too much VRAM
CAM_HEIGHT_MIN      = 1.5    # metres above floor
CAM_HEIGHT_MAX      = 4.0
CAM_DIST_CLOSE_MIN  = 1.5    # close camera band: 1.5–4 m from cluster centre
CAM_DIST_CLOSE_MAX  = 4.0
CAM_DIST_FAR_MIN    = 8.0    # far camera band:   8–18 m from cluster centre
CAM_DIST_FAR_MAX    = 18.0
FOCAL_MM_MIN        = 24.0   # 35 mm-equivalent focal length
FOCAL_MM_MAX        = 50.0
CAM_SENSOR_WIDTH_MM = 36.0   # horizontal aperture (mm) — standard 35 mm equiv

# ── Annotation filtering ──────────────────────────────────────────────────────
MIN_BOX_SIZE          = 0.02  # min bbox w or h as fraction of image dimension
MAX_BOX_SIZE          = 0.90  # max bbox w or h as fraction of image dimension
MIN_VISIBLE_FRACTION  = 0.25  # reject if clipped to < 25 % of raw bbox area
BRIGHTNESS_MIN        = 20    # mean pixel value lower bound  (reject too-dark)
BRIGHTNESS_MAX        = 230   # mean pixel value upper bound  (reject too-bright)

# ── Pallet asset lists ────────────────────────────────────────────────────────

_SIMPLE_WAREHOUSE_PROPS = [
    (LOCAL_5_1 + "/Isaac/Environments/Simple_Warehouse/Props/SM_PaletteA_01.usd", 1.0),
    (LOCAL_5_1 + "/Isaac/Environments/Simple_Warehouse/Props/SM_PaletteA_02.usd", 1.0),
]

_ISAAC_PROPS = [
    (LOCAL_5_1 + "/Isaac/Props/Pallet/pallet.usd",               1.0),
    (LOCAL_5_1 + "/Isaac/Props/Pallet/pallet_holder.usd",        1.0),
    (LOCAL_5_1 + "/Isaac/Props/Pallet/pallet_holder_short.usd",  1.0),
    (LOCAL_5_1 + "/Isaac/Props/Pallet/o3dyn_pallet.usd",         1.0),
]

_ARCHVIS_PALLETS = [
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Pallets/Pallet_A1.usd", 0.01),
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Pallets/Pallet_B1.usd", 0.01),
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Pallets/Pallet_C1.usd", 0.01),
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Piles/Pallets_A1.usd",  0.01),
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Piles/Pallets_A2.usd",  0.01),
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Piles/Pallets_A3.usd",  0.01),
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Piles/Pallets_A4.usd",  0.01),
    (LOCAL_5_1 + "/NVIDIA/Assets/ArchVis/Industrial/Piles/Pallets_A5.usd",  0.01),
]

_DT_BASE = LOCAL_5_0 + "/NVIDIA/Assets/DigitalTwin/Assets/Warehouse/Shipping/Pallets"

_DIGITALTWIN_WOOD = [
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A01_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A02_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A03_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A04_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A05_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A06_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A07_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A08_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_A/BlockPallet_A09_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_B/BlockPallet_B01_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_B/BlockPallet_B02_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_B/BlockPallet_B03_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Block_C/BlockPallet_C01_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A01_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A02_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A03_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A04_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A05_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A06_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A07_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A08_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Pressed_A/PressedWoodPallet_A09_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A01_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A02_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A03_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A04_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A05_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A06_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A07_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Recycled_A/RecycledWoodPallet_A08_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A01_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A02_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A03_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A04_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A05_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A06_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A07_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Drum_A/WoodDrumPallet_A08_PR_NVD_01.usd",  0.01),
    (_DT_BASE + "/Wood/Wing_A/WingPallet_A01_PR_NVD_01.usd",      0.01),
]

_DIGITALTWIN_PLASTIC = [
    (_DT_BASE + "/Plastic/Economy_A/EconomyPlasticPallet_A01_PR_NVD_01.usd",          0.01),
    (_DT_BASE + "/Plastic/Economy_A/EconomyPlasticPallet_A02_PR_NVD_01.usd",          0.01),
    (_DT_BASE + "/Plastic/Economy_A/EconomyPlasticPallet_A03_PR_NVD_01.usd",          0.01),
    (_DT_BASE + "/Plastic/Export_A/ExportPallet_A01_PR_NVD_01.usd",                   0.01),
    (_DT_BASE + "/Plastic/Export_A/ExportPallet_A02_PR_NVD_01.usd",                   0.01),
    (_DT_BASE + "/Plastic/Export_A/ExportPallet_A03_PR_NVD_01.usd",                   0.01),
    (_DT_BASE + "/Plastic/Export_A/ExportPallet_A04_PR_NVD_01.usd",                   0.01),
    (_DT_BASE + "/Plastic/Export_A/ExportPallet_A05_PR_NVD_01.usd",                   0.01),
    (_DT_BASE + "/Plastic/Export_A/ExportPallet_A06_PR_NVD_01.usd",                   0.01),
    (_DT_BASE + "/Plastic/Export_A/ExportPallet_A07_PR_NVD_01.usd",                   0.01),
    (_DT_BASE + "/Plastic/HeavyDutyNestable_A/HeavyDutyNestablePallet_A01_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/HeavyDutyNestable_A/HeavyDutyNestablePallet_A02_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/IBCSpillContainment_A/IBCSpillContainmentPallet_A01_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/Industrial_A/IndustrialPlasticPallet_A01_PR_V_NVD_01.usd",  0.01),
    (_DT_BASE + "/Plastic/Rackable_A/RackablePallet_A01_PR_V_NVD_01.usd",             0.01),
    (_DT_BASE + "/Plastic/Rackable_A/RackablePallet_A02_PR_V_NVD_01.usd",             0.01),
    (_DT_BASE + "/Plastic/RackableExport_A/RackableExportPallet_A01_PR_NVD_01.usd",   0.01),
    (_DT_BASE + "/Plastic/SolidTopRackable_A/SolidTopRackablePallet_A01_PR_V_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/SolidTopRackable_A/SolidTopRackablePallet_A02_PR_V_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/SolidTopRackable_A/SolidTopRackablePallet_A03_PR_V_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/SolidTopRackable_A/SolidTopRackablePallet_A04_PR_V_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/ClosedDeckExport_A/ClosedDeckExportPallet_A01_PR_NVD_01.usd", 0.01),
    (_DT_BASE + "/Plastic/Drum_A/PlasticDrumPallet_A01_PR_NVD_01.usd",               0.01),
]

_DIGITALTWIN_METAL = [
    (_DT_BASE + "/Metal/Aluminum_A/AluminumPallet_A01_PR_NVD_01.usd",               0.01),
    (_DT_BASE + "/Metal/Aluminum_A/AluminumPallet_A02_PR_NVD_01.usd",               0.01),
    (_DT_BASE + "/Metal/GalvanizedSteel_A/GalvanizedSteelPallet_A01_PR_NVD_01.usd", 0.01),
]

# ── Remote pallet assets (S3 URLs — no local-file check possible) ─────────────
_REMOTE_PALLETS = [
    (
        "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
        "/Assets/DigitalTwin/Assets/Warehouse/Shipping"
        "/Cardboard_Boxes_on_Pallet/Pallet_Asm_A"
        "/Pallet_Asm_A06_112x112x109cm_PR_V_NVD_01.usd",
        0.01,
    ),
    (
        "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
        "/Assets/DigitalTwin/Assets/Warehouse/Shipping"
        "/Wood_Crate_on_Pallet/Plywood_A"
        "/PlywoodCrateAssembly_A05_PR_NVD_01.usd",
        0.01,
    ),
]

# ── Forklift asset list ───────────────────────────────────────────────────────
# Yellow prop forklift only — matches the target class in the real dataset.
_FORKLIFT_CANDIDATES = [
    (LOCAL_5_1 + "/Isaac/Props/Forklift/forklift.usd", 1.0),
]

# ── Master asset lists (missing files auto-filtered) ─────────────────────────
def _available(entries):
    return [(p, s) for p, s in entries if os.path.exists(p)]

ALL_PALLET_ASSETS = (
    _available(_SIMPLE_WAREHOUSE_PROPS) +
    _available(_ISAAC_PROPS) +
    _available(_ARCHVIS_PALLETS) +
    _available(_DIGITALTWIN_WOOD) +
    _available(_DIGITALTWIN_PLASTIC) +
    _available(_DIGITALTWIN_METAL) +
    _REMOTE_PALLETS                    # remote URLs — always included
)

FORKLIFT_ASSETS = _available(_FORKLIFT_CANDIDATES)

# ── Scenario forklift slots ───────────────────────────────────────────────────
N_FORKLIFT_SLOTS  = 2      # pre-allocated USD slots (budget caps at MAX_FORKLIFTS=2)

# ── Gate state randomisation ──────────────────────────────────────────────────
GATE_OPEN_PROB = 0.35  # per-gate probability of being open each frame

# ── Box / cardboard-crate assets (warehouse props, authored in metres) ─────────
_SW_PROPS = LOCAL_5_1 + "/Isaac/Environments/Simple_Warehouse/Props"
_BOX_CANDIDATES = [
    (_SW_PROPS + "/SM_CardBoxA_01.usd", 1.0),
    (_SW_PROPS + "/SM_CardBoxB_01.usd", 1.0),
    (_SW_PROPS + "/SM_CardBoxC_01.usd", 1.0),
    (_SW_PROPS + "/SM_CardBoxD_01.usd", 1.0),
]
ALL_BOX_ASSETS = _available(_BOX_CANDIDATES)

# ── Box placement ─────────────────────────────────────────────────────────────
# Boxes are scattered in the loading + staging zone corridor
N_BOX_SLOTS      = 4    # pre-allocated USD slots (max = MAX_OBJECTS − 1 pallet)
# Bounding rectangle for box scatter (loading dock + staging corridor)
BOX_X_MIN        = -21.0
BOX_X_MAX        =  -1.0
BOX_Y_MIN        = -23.0  # just inside the south wall (loading zone)
BOX_Y_MAX        =  -4.0  # northern edge of staging zone

# ── Lighting randomisation ────────────────────────────────────────────────────
DOME_INTENSITY_MIN   =   50.0   # ambient dome dim (overcast indoor feel)
DOME_INTENSITY_MAX   = 1500.0   # ambient dome bright (open-sky feel)
LIGHT_INTENSITY_MIN  =  300.0   # directional light dim (overcast)
LIGHT_INTENSITY_MAX  = 8000.0   # directional light bright (noon sun)
LIGHT_COLOR_TEMP_MIN = 3000.0   # K — warm incandescent
LIGHT_COLOR_TEMP_MAX = 7500.0   # K — cool daylight
LIGHT_ELEV_MIN       =   15.0   # sun elevation above horizon (degrees)
LIGHT_ELEV_MAX       =   75.0   # sun elevation above horizon (degrees)

# ── Real dataset reference (seeteria_ds — snapshot for proportional summary) ──
REAL_DATASET_IMAGES     = 27948
REAL_DATASET_PALLETS    = 43755
REAL_DATASET_FORKLIFTS  = 22013
REAL_DATASET_BOXES      = 0
