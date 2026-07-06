"""
Warehouse constants and tuning parameters.
All spatial values in metres; angles in degrees.
"""
import os as _os

# ── Warehouse bounds (from full_warehouse.usd) ──────────────────────────────
WALL_X_MIN, WALL_X_MAX = -26.33,  5.46
WALL_Y_MIN, WALL_Y_MAX = -23.40, 30.60
WALL_MARGIN = 1.8

NAV_X_MIN = WALL_X_MIN + WALL_MARGIN
NAV_X_MAX = WALL_X_MAX - WALL_MARGIN
NAV_Y_MIN = WALL_Y_MIN + WALL_MARGIN
NAV_Y_MAX = WALL_Y_MAX - WALL_MARGIN

# Centre of the warehouse floor
WAREHOUSE_CX = (WALL_X_MIN + WALL_X_MAX) / 2.0   # ~ -10.435
WAREHOUSE_CY = (WALL_Y_MIN + WALL_Y_MAX) / 2.0   # ~   3.60

# ── Surveillance cameras ─────────────────────────────────────────────────────
CAMERA_HEIGHT  = 15.0   # metres above the floor
CAMERA_FOV_DEG = 70.0   # horizontal field of view

# Reference USD that stores the four manually-positioned camera prims.
# Path is resolved relative to this config file so it works regardless of
# the current working directory.
CAMERA_POSITIONS_USD = _os.path.normpath(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                  "..", "tests", "camera_position.usd")
)

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

def compute_zones(gate_offsets):
    """Return LoadingZone / StagingArea / ShelvesArea bounds for any gate layout."""
    lx_min = WAREHOUSE_CX + gate_offsets[0]  - LOAD_W    / 2.0
    lx_max = WAREHOUSE_CX + gate_offsets[-1] + LOAD_W    / 2.0
    sx_min = WAREHOUSE_CX + gate_offsets[0]  - STAGING_W / 2.0
    sx_max = WAREHOUSE_CX + gate_offsets[-1] + STAGING_W / 2.0
    return {
        "LoadingZone": (lx_min, lx_max, WALL_Y_MIN, WALL_Y_MIN + LOAD_D),
        "StagingArea": (sx_min, sx_max, STAGING_Y_NEAR, STAGING_Y_FAR),
        "ShelvesArea": (NAV_X_MIN, NAV_X_MAX, _SHELF_START_EST, NAV_Y_MAX),
    }

# ZONES keeps the standard 3-gate layout for all existing scenarios.
ZONES = compute_zones(GATE_OFFSETS)

# ── Surveillance cameras ──────────────────────────────────────────────────────
# All four cameras are defined here from the warehouse geometry so that the
# test script and generate_homography.py share one source of truth.
# Format: { name: (eye_xyz, target_xyz, fov_deg) }
#
# Target for all cameras: midpoint between loading and staging zone centres.
SURVEILLANCE_CAMERAS = {
    # Positions from tests/camera_position.usd — match the _out_sdrec_5 recording.
    # Target is the floor point (Z=0) along each camera's look direction.
    "cam_south": ((-9.8341, -22.5330, 6.9060), (-10.7264,  -5.1664, 0.0), 70.0),
    "cam_north": ((-10.5431,  9.8619, 8.2098), (-10.6338,  -6.9230, 0.0), 70.0),
    "cam_west":  ((-25.4845,  6.1854, 6.6975), (-14.8844,  -5.0847, 0.0), 70.0),
    "cam_east":  ((  4.0934,  6.2543, 8.3897), ( -5.4913,  -3.1932, 0.0), 70.0),
}

# ── Live Alerts scenario gate layout ─────────────────────────────────────────
# 4 gates with 6 m spacing, labeled to match Nashville DC demo video.
LIVE_ALERTS_GATE_OFFSETS = [-9.0, -3.0, 3.0, 9.0]
GATE_DOOR_NUMBERS        = [12, 4, 7, 9]   # display label per gate index

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
AISLE_HALF_WIDTH     = 0.1   # max X drift from aisle centreline inside shelf area

# ── Fork mast animation ─────────────────────────────────────────────────────
FORK_RAISE_SPEED   = 0.25
FORK_TRAVEL_HEIGHT = 0.45   # legacy height constant
FORK_GROUND_HEIGHT = 0.0

# Local-frame offset for a pallet child prim to sit on the forks.
# Calibrated from test_pallet_position_visual.py — user moved blue origin
# cube to the exact fork centre:
#   forklift anchor world:  (-21.530, -18.600, 0)
#   pallet origin world:    (-20.334, -18.528, 0.194)
#   world offset:           (+1.196, +0.072, +0.194)
#   forklift rotateZ=90 inverse → local: (world_dy, -world_dx, world_dz)
PALLET_FORK_LOCAL_X =  0.072   # local X (≈ centred left/right on forks)
PALLET_FORK_LOCAL_Y = -1.196   # local Y (forward, towards fork tines)
PALLET_FORK_LOCAL_Z =  0.194   # height — fork tine travel height

# ── Forklift FSM states ──────────────────────────────────────────────────────
# Movement states: what the forklift is currently doing
STATE_IDLE              = "idle"               # stationary, no task
STATE_PICKUP_AT_SHELVES = "pickup_at_shelves"  # at shelves, picking up pallet
STATE_MOVE_TO_STAGING   = "move_to_staging"    # driving toward staging area (loaded)
STATE_WAIT_IN_STAGING   = "wait_in_staging"    # holding in staging, dock not ready
STATE_MOVE_TO_LOADING   = "move_to_loading"    # driving toward loading dock (loaded)
STATE_WAIT_AT_DOCK_QUEUE= "wait_at_dock_queue" # queued at dock, waiting for slot
STATE_LOADING           = "loading"            # at dock, transferring pallet
STATE_RETURNING         = "returning"          # driving back to shelves (unloaded)

# ── Forklift load property ───────────────────────────────────────────────────
# Independent of state — what the forklift is carrying.
# Drives fork height and pallet prim visibility (wired in Task #4 models/forklift.py).
LOAD_LOADED   = "loaded"    # pallet on forks: fork raised to FORK_TRAVEL_HEIGHT
LOAD_UNLOADED = "unloaded"  # no pallet: fork lowered to FORK_GROUND_HEIGHT

# Expected load property per state (for rule engine validation in Task #6)
STATE_EXPECTED_LOAD = {
    STATE_IDLE:               LOAD_UNLOADED,
    STATE_PICKUP_AT_SHELVES:  LOAD_UNLOADED,  # picking up — becomes loaded on completion
    STATE_MOVE_TO_STAGING:    LOAD_LOADED,
    STATE_WAIT_IN_STAGING:    LOAD_LOADED,
    STATE_MOVE_TO_LOADING:    LOAD_LOADED,
    STATE_WAIT_AT_DOCK_QUEUE: LOAD_LOADED,
    STATE_LOADING:            LOAD_LOADED,    # drops pallet — becomes unloaded on completion
    STATE_RETURNING:          LOAD_UNLOADED,
}

# ── Area capacities ──────────────────────────────────────────────────────────
# Maximum number of forklifts allowed in each area simultaneously.
# ShelvesArea has no capacity limit — forklifts move freely in aisles.
LOADING_AREA_CAPACITY  = 1   # one forklift per dock at a time
STAGING_AREA_CAPACITY  = 6   # staging holds up to 6 waiting forklifts

# ── Detection thresholds ─────────────────────────────────────────────────────
QUEUE_SUSTAINED_SECS   = 15.0  # seconds at dock queue before "queue formed" event fires
IDLE_WARN_SECS         = 20.0  # seconds in STATE_IDLE before "idle too long" alert fires
NEAR_MISS_DIST         = 2.5   # metres — proximity alert trigger distance
NEAR_MISS_SPEED_MIN    = 0.5   # m/s — min speed of one forklift to count as near-miss
CONGESTION_SPEED_RATIO = 0.3   # speed < 30% of max while in traffic area → congestion log

# ── Pedestrian kinematics & safety thresholds ─────────────────────────────────
PEDESTRIAN_SPEED     = 1.4   # m/s nominal walking speed
PEDESTRIAN_WARN_DIST = 2.0   # m  — log warning when forklift this close
PEDESTRIAN_STOP_DIST = 1.0   # m  — emergency-stop both actors at this distance

# ── Scenario preset levers ───────────────────────────────────────────────────
# Each scenario reads its own sub-dict to tune its specific behaviour.
SCENARIO_PRESETS = {
    "dock_queue": {
        "num_forklifts":    4,
        "loading_duration": 20.0,   # long dock time causes queue to build up
        "dock_capacity":    1,
    },
    "loading_pause": {
        "num_forklifts":    3,
        "loading_duration": 8.0,
        "pause_at_sec":     30.0,   # door closes at T=30s, forklifts stop advancing
        "pause_duration":   20.0,   # door stays closed for 20s then reopens
    },
    "area_buildup": {
        "num_forklifts":    5,
        "loading_duration": 12.0,
        "release_interval": 8.0,    # slow outflow — staging fills up
    },
    "aisle_congestion": {
        "num_forklifts":    6,
        "loading_duration": 6.0,
        "target_aisle_x":   None,   # None = auto-pick narrowest aisle at runtime
    },
    "vehicle_idle": {
        "num_forklifts":    4,
        "idle_forklift_ids": [1, 2],  # these forklifts receive no task
        "loading_duration": 6.0,
    },
    "safety_proximity": {
        "num_forklifts":    4,
        "crossing_speed":   2.5,    # forklifts approach crossing point at this speed
        "loading_duration": 6.0,
    },
}

# ── Config-driven scenarios ──────────────────────────────────────────────────
# Entries here create scenarios without a Python subclass.  Set SCENARIO to the
# dict key in main.py and ConfigScenario does the rest.  Python-class entries in
# scenarios/PRESETS always take priority when the same name appears in both.
#
# Supported keys per entry:
#   num_forklifts    (int)        how many forklifts to spawn
#   loading_duration (float)      seconds at dock per cycle
#   pickup_duration  (float)      seconds at shelf pickup per cycle
#   spawn_strategy   (str)        "grid" | "near_aisle"
#   near_aisle_x     (float|None) X for near_aisle; None = auto from ShelfMap
#   doors            (dict)       open_all_at_start (bool) + events list
#   idle_forklift_ids(list[int])  forklift IDs that never receive tasks
#   thresholds       (dict)       per-scenario overrides for IDLE_WARN_SECS,
#                                 NEAR_MISS_DIST
CONFIG_SCENARIOS = {
    "vehicle_idle": {
        "num_forklifts":     4,
        "loading_duration":  6.0,
        "spawn_strategy":    "grid",
        "doors": {
            "open_all_at_start": True,
            "events": [],
        },
        "idle_forklift_ids": [1, 2],   # FL1 and FL2 stay parked
        "thresholds": {
            "IDLE_WARN_SECS": 60.0,    # suppress idle alert for active forklifts
        },
    },
}

# ── FSM timing ──────────────────────────────────────────────────────────────
IDLE_DURATION    = 3.5
PICKUP_DURATION  = 4.0   # seconds spent picking up a pallet at the shelves
LOADING_DURATION = 5.0   # seconds spent transferring pallet at the dock

# ── Shelf detection keywords ────────────────────────────────────────────────
SHELF_KEYWORDS = frozenset({
    "rack", "shelf", "shelv", "pallet_rack", "shelving",
    "storage", "fixture", "unit",
})

# ── Staging props ───────────────────────────────────────────────────────────
PALLET_H = 0.15

# ── Pallet / box footprint dimensions (metres) ───────────────────────────────
# PALLET_USD is authored at 112 × 112 cm; PALLET_SCALE = 0.01 → 1.12 × 1.12 m.
PALLET_FOOTPRINT_W = 1.12   # pallet width  (X axis)
PALLET_FOOTPRINT_D = 1.12   # pallet depth  (Y axis)

# BOX_USDS are Isaac Simple_Warehouse cardboard box props.
# Approximate footprint derived from visual inspection.
BOX_FOOTPRINT_W = 0.60   # loose box width  (X axis)
BOX_FOOTPRINT_D = 0.60   # loose box depth  (Y axis)

# ── Overspill detection ──────────────────────────────────────────────────────
# Distance (metres) outside a zone boundary at which a misplaced pallet/box
# is still considered "in the vicinity" and therefore an overspill alert.
OVERSPILL_BUFFER_M = 1.5

# ── Asset paths ──────────────────────────────────────────────────────────────
# WAREHOUSE_USD and FORKLIFT_USD are relative paths appended to assets_root.
# PALLET_USD is an absolute URL and must be used directly (no assets_root prefix).
WAREHOUSE_USD    = "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd"
FORKLIFT_USD     = "/Isaac/Props/Forklift/forklift.usd"

# ── IRA (isaacsim.replicator.agent) pedestrian assets ────────────────────────
# Absolute local paths — no assets_root prefix needed.
IRA_CHARACTERS_DIR = "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1/Isaac/People/Characters"
IRA_BIPED_USD      = IRA_CHARACTERS_DIR + "/Biped_Setup.usd"
IRA_CHARACTER_USD  = (IRA_CHARACTERS_DIR
                      + "/male_adult_construction_01_new"
                      + "/male_adult_construction_01_new.usd")
# Absolute local path to the warehouse USD used by SimulationManager.
# SimulationManager requires a local file path (not a Nucleus URL).
IRA_WAREHOUSE_USD  = ("/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1/Isaac"
                      "/Environments/Simple_Warehouse/full_warehouse.usd")
PALLET_USD    = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/DigitalTwin/Assets/Warehouse/Shipping/Cardboard_Boxes_on_Pallet/Pallet_Asm_A/Pallet_Asm_A06_112x112x109cm_PR_V_NVD_01.usd"
PALLET_SCALE  = 0.01   # asset is authored in cm; stage is in metres
CRATE_USD     = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/DigitalTwin/Assets/Warehouse/Shipping/Wood_Crate_on_Pallet/Plywood_A/PlywoodCrateAssembly_A05_PR_NVD_01.usd"
CRATE_SCALE   = 0.01   # asset is authored in cm; stage is in metres
BOX_USDS      = [
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxA_01.usd",
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxB_01.usd",
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxC_01.usd",
    "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxD_01.usd",
]
