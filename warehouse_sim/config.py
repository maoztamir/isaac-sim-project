"""
Warehouse constants and tuning parameters.
All spatial values in metres; angles in degrees.
"""

# ── Warehouse bounds (from full_warehouse.usd) ──────────────────────────────
WALL_X_MIN, WALL_X_MAX = -26.33,  5.46
WALL_Y_MIN, WALL_Y_MAX = -23.40, 30.60
WALL_MARGIN = 1.8

NAV_X_MIN = WALL_X_MIN + WALL_MARGIN
NAV_X_MAX = WALL_X_MAX - WALL_MARGIN
NAV_Y_MIN = WALL_Y_MIN + WALL_MARGIN
NAV_Y_MAX = WALL_Y_MAX - WALL_MARGIN

# Centre X of the warehouse (used to position gates and staging)
WAREHOUSE_CX = (WALL_X_MIN + WALL_X_MAX) / 2.0   # ~ -10.435

# ── Loading dock gate geometry ──────────────────────────────────────────────
GATE_OFFSETS = [-7.0, 0.0, 7.0]         # X offsets from WAREHOUSE_CX
GATE_W       = 4.0                       # outer width
GATE_TOTAL_H = 4.5                       # outer height
GATE_D       = 0.18                      # front-to-back depth
POST_W       = 0.20                      # vertical post width
DRUM_H       = 0.55                      # drum housing height
OPENING_W    = GATE_W - 2 * POST_W      # 3.60 m clear opening
OPENING_H    = GATE_TOTAL_H - DRUM_H    # 3.95 m door travel height
PANEL_N      = 8                         # shutter slats
PANEL_H      = OPENING_H / PANEL_N
PANEL_GAP    = 0.005
GUIDE_W      = 0.03
SEAL_H       = 0.05
HOLE_W       = OPENING_W
HOLE_H       = OPENING_H
HOLE_DEPTH   = 2.0
WALL_T       = 0.5

# Gate colours
STEEL_COL    = [(0.35, 0.36, 0.40)]
SHUTTER_COL  = [(0.48, 0.50, 0.54)]
SEAL_COL     = [(0.06, 0.06, 0.06)]
WALL_COLOR   = [(0.60, 0.57, 0.53)]
HOLE_COLOR   = [(0.02, 0.02, 0.02)]

# ── Loading zone geometry ───────────────────────────────────────────────────
LOAD_W = 4.0                             # per-door loading zone width
LOAD_D = 4.5                             # loading zone depth into warehouse

# ── Staging area geometry ───────────────────────────────────────────────────
STAGING_W = 8.0                          # staging zone width
STAGING_D = 7.0                          # staging zone depth
_LOAD_TOP = WALL_Y_MIN + LOAD_D                   # top edge of loading zone
_SHELF_START_EST = (WALL_Y_MIN + WALL_Y_MAX) / 2.0  # approx shelf boundary
STAGING_CENTER_Y = (_LOAD_TOP + _SHELF_START_EST) / 2.0
STAGING_Y_NEAR = STAGING_CENTER_Y - STAGING_D / 2.0
STAGING_Y_FAR  = STAGING_CENTER_Y + STAGING_D / 2.0

# ── Zebra tape floor markings ──────────────────────────────────────────────
TAPE_THICK   = 0.02
TAPE_WIDTH   = 0.25
STRIPE_SPACE = 0.40
STRIPE_THICK = 0.06
YELLOW       = [(1.0, 0.85, 0.0)]
BLACK        = [(0.10, 0.10, 0.10)]

# ── Zone rectangles (x_min, x_max, y_min, y_max) ────────────────────────────
# LoadingZone: spans all 3 loading doors on the south wall
_load_x_min = WAREHOUSE_CX + GATE_OFFSETS[0] - LOAD_W / 2.0
_load_x_max = WAREHOUSE_CX + GATE_OFFSETS[-1] + LOAD_W / 2.0
_load_y_min = WALL_Y_MIN
_load_y_max = WALL_Y_MIN + LOAD_D

# StagingArea: spans all 3 staging zones between loading and shelves
_stag_x_min = WAREHOUSE_CX + GATE_OFFSETS[0] - STAGING_W / 2.0
_stag_x_max = WAREHOUSE_CX + GATE_OFFSETS[-1] + STAGING_W / 2.0

# ShelvesArea: refined by shelf detection; these are initial bounds
ZONES = {
    "LoadingZone": (_load_x_min, _load_x_max, _load_y_min, _load_y_max),
    "StagingArea": (_stag_x_min, _stag_x_max, STAGING_Y_NEAR, STAGING_Y_FAR),
    "ShelvesArea": (NAV_X_MIN, NAV_X_MAX, _SHELF_START_EST, NAV_Y_MAX),
}

# ── Forklift kinematic model ────────────────────────────────────────────────
FORKLIFT_WHEELBASE   = 2.4
FORKLIFT_MAX_SPEED   = 3.0
FORKLIFT_MIN_SPEED   = 0.4
FORKLIFT_ACCEL       = 1.5
FORKLIFT_BRAKE       = 2.5
FORKLIFT_MAX_STEER   = 65.0
FORKLIFT_STEER_RATE  = 100.0
FORKLIFT_HEADING_OFFSET = 90.0
FORKLIFT_BODY_HALF   = 0.9
FORKLIFT_ARRIVE_RADIUS = 2.0
AISLE_SNAP           = 0.8

# ── Fork mast animation ─────────────────────────────────────────────────────
FORK_RAISE_SPEED   = 0.25
FORK_TRAVEL_HEIGHT = 0.45
FORK_GROUND_HEIGHT = 0.0

# ── FSM timing ──────────────────────────────────────────────────────────────
IDLE_DURATION    = 3.5
LOADING_DURATION = 5.0

# ── Shelf detection keywords ────────────────────────────────────────────────
SHELF_KEYWORDS = frozenset({
    "rack", "shelf", "shelv", "pallet_rack", "shelving",
    "storage", "fixture", "unit",
})

# ── Staging props ───────────────────────────────────────────────────────────
PALLET_H = 0.15

# ── Asset paths (relative to get_assets_root_path()) ────────────────────────
WAREHOUSE_USD = "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd"
FORKLIFT_USD  = "/Isaac/Props/Forklift/forklift.usd"
PALLET_USD    = "/Isaac/Props/Pallet/pallet.usd"
BOX_USDS      = [
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxA_01.usd",
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxB_01.usd",
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxC_01.usd",
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxD_01.usd",
]
