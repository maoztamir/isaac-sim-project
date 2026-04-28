"""
Pallet dataset generation config.

ASSETS_5_1 / ASSETS_5_0
    Tuples of (relative_path, scale_factor).
    relative_path is appended to the matching base directory.
    scale_factor: 1.0 for assets authored in metres, 0.01 for assets authored in cm.

All paths use the locally-cached asset directories so no Nucleus connection is required.
"""

import os

# ── Local asset cache roots ───────────────────────────────────────────────────
LOCAL_5_1 = "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1"
LOCAL_5_0 = "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.0"

# ── Generation parameters ─────────────────────────────────────────────────────
OUTPUT_DIR   = "/media/storage/pallet_dataset"
NUM_FRAMES   = 500          # images captured per camera
RESOLUTION   = (1280, 720)
MIN_PALLETS  = 1
MAX_PALLETS  = 6
SEED         = 42

# Navigable floor area to scatter pallets on (metres, warehouse coords)
SCATTER_X_MIN, SCATTER_X_MAX = -22.0,  3.0
SCATTER_Y_MIN, SCATTER_Y_MAX = -18.0,  7.0

# Replicator sub-frames per capture (higher = better ray-trace quality, slower)
RT_SUBFRAMES = 4

# ── Pallet asset lists ────────────────────────────────────────────────────────
# Each entry: (absolute_path, scale)

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
    # Stacked-pallet piles (multiple pallets as one asset)
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
    (_DT_BASE + "/Metal/Aluminum_A/AluminumPallet_A01_PR_NVD_01.usd",             0.01),
    (_DT_BASE + "/Metal/Aluminum_A/AluminumPallet_A02_PR_NVD_01.usd",             0.01),
    (_DT_BASE + "/Metal/GalvanizedSteel_A/GalvanizedSteelPallet_A01_PR_NVD_01.usd", 0.01),
]

# ── Master asset list (all groups combined, missing files auto-filtered) ──────
def _available(entries):
    return [(p, s) for p, s in entries if os.path.exists(p)]

ALL_PALLET_ASSETS = (
    _available(_SIMPLE_WAREHOUSE_PROPS) +
    _available(_ISAAC_PROPS) +
    _available(_ARCHVIS_PALLETS) +
    _available(_DIGITALTWIN_WOOD) +
    _available(_DIGITALTWIN_PLASTIC) +
    _available(_DIGITALTWIN_METAL)
)
