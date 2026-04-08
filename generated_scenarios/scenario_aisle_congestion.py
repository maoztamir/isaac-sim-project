#!/usr/bin/env python3
"""
Aisle Congestion Scenario
-------------------------
Three forklifts converge on a single aisle entrance where a dropped pallet
partially blocks the turning radius, creating sustained congestion: queuing,
speed reduction, and tight-gap navigation.

Warehouse corners (from reference):
  SW (-26.33, -23.4)   SE (5.46, -23.4)
  NW (-26.33,  30.6)   NE (5.46,  30.6)

Run inside Isaac Sim: Window > Script Editor > Open > Ctrl+Enter
"""

import math
import random

import carb
import omni.kit.app
import omni.kit.commands
import omni.physx
import omni.timeline
import omni.usd
from isaacsim.core.utils.stage import get_current_stage
from isaacsim.storage.native import get_assets_root_path
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

# ==========================================================================
# SIMULATION PARAMETERS -- grouped at the top for easy tuning
# ==========================================================================
RANDOM_SEED = 42

# Forklift ground Z offset — auto-detected on first physics step by measuring
# how far the forklift's visual bottom sits above its translate origin.
# Override manually if forklifts still hover (try -0.5 or -1.0).
FORKLIFT_GROUND_Z_OFFSET = None  # auto-detected

# Warehouse bounds
WALL_X_MIN, WALL_X_MAX = -26.33,  5.46
WALL_Y_MIN, WALL_Y_MAX = -23.40, 30.60
WALL_MARGIN = 1.8

NAV_X_MIN = WALL_X_MIN + WALL_MARGIN
NAV_X_MAX = WALL_X_MAX - WALL_MARGIN
NAV_Y_MIN = WALL_Y_MIN + WALL_MARGIN
NAV_Y_MAX = WALL_Y_MAX - WALL_MARGIN

# Congestion zone -- the aisle entrance where all forklifts funnel
# This will be refined once shelf detection runs; these are defaults
# targeting the approximate centre of the warehouse shelving area.
CONGESTION_X = -10.0       # X of the target aisle (updated after shelf scan)
CONGESTION_Y_ENTRANCE = 3.0  # Y at the south mouth of the shelving area
CONGESTION_Y_INSIDE = 12.0   # Y of a point well inside the aisle

# Dropped pallet parameters
PALLET_DROP_OFFSET_X = 1.2   # metres to the right of aisle centre
PALLET_DROP_Y_OFFSET = 0.5   # metres north of the aisle entrance
PALLET_YAW = 25.0            # degrees -- tilted as if knocked off forks
PALLET_TILT_ROLL = 8.0       # degrees -- slight roll to look dropped
PALLET_OBSTACLE_HALF_W = 0.8 # obstacle half-width (m)
PALLET_OBSTACLE_HALF_D = 0.7 # obstacle half-depth (m)

# Forklift kinematic model (from reference)
FORKLIFT_WHEELBASE   = 2.4
FORKLIFT_MAX_SPEED   = 3.0
FORKLIFT_MIN_SPEED   = 0.4
FORKLIFT_ACCEL       = 1.5
FORKLIFT_BRAKE       = 2.5
FORKLIFT_MAX_STEER   = 65.0
FORKLIFT_STEER_RATE  = 100.0
FORK_HEADING_OFFSET  = 90.0
WHEEL_RADIUS         = 0.35
WAYPOINT_ARRIVE      = 2.0
FORKLIFT_BODY        = 0.9

# Fork mast animation
FORK_RAISE_SPEED     = 0.25
FORK_TRAVEL_HEIGHT   = 0.45
FORK_GROUND_HEIGHT   = 0.0
IDLE_DURATION        = 2.5    # shorter idle for tighter congestion loops

# Congestion-specific braking
CONGESTION_BRAKE_RADIUS = 5.0   # distance from pallet to start braking
CONGESTION_CREEP_SPEED  = 0.8   # max speed within brake zone

# States
STATE_DRIVE = "drive"
STATE_IDLE  = "idle"

# ==========================================================================
# Stage setup
# ==========================================================================
stage = get_current_stage()
assets_root = get_assets_root_path()

omni.kit.commands.execute("DeletePrimsCommand", paths=["/World"])

def spawn_asset(prim_path, asset_path, x, y, z=0.0, yaw_deg=0.0):
    xform = UsdGeom.Xform.Define(stage, prim_path)
    xform.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
    xform.AddRotateZOp().Set(yaw_deg)
    stage.GetPrimAtPath(Sdf.Path(prim_path)).GetReferences().AddReference(asset_path)

# Warehouse environment
spawn_asset("/World/Warehouse",
            assets_root + "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd",
            0, 0, 0)

# Physics scene
_phys_scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
_phys_scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
_phys_scene.CreateGravityMagnitudeAttr(9.81)

# ==========================================================================
# Dropped pallet -- spawned at the aisle entrance, tilted
# ==========================================================================
_pallet_usd = assets_root + "/Isaac/Props/Pallet/pallet.usd"

# Actual drop position (refined after shelf scan, but placed now with defaults)
_pallet_x = CONGESTION_X + PALLET_DROP_OFFSET_X
_pallet_y = CONGESTION_Y_ENTRANCE + PALLET_DROP_Y_OFFSET

_pallet_path = "/World/Obstacles/dropped_pallet"
_pallet_xform = UsdGeom.Xform.Define(stage, _pallet_path)
_pallet_xform.AddTranslateOp().Set(Gf.Vec3d(_pallet_x, _pallet_y, 0.0))
_pallet_xform.AddRotateXYZOp().Set(Gf.Vec3f(PALLET_TILT_ROLL, 0.0, PALLET_YAW))
stage.GetPrimAtPath(Sdf.Path(_pallet_path)).GetReferences().AddReference(_pallet_usd)

# Apply static collision to the pallet
def _apply_physics(prim_path):
    prim = stage.GetPrimAtPath(Sdf.Path(prim_path))
    if prim.IsValid():
        UsdPhysics.CollisionAPI.Apply(prim)

_apply_physics(_pallet_path)

# A few scattered cardboard boxes near the pallet to sell the "dropped load" look
_box_usds = [
    assets_root + "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxA_01.usd",
    assets_root + "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxB_01.usd",
    assets_root + "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxC_01.usd",
]
random.seed(RANDOM_SEED)
for bi in range(3):
    bx = _pallet_x + random.uniform(-0.8, 0.8)
    by = _pallet_y + random.uniform(-0.6, 0.6)
    bz = random.uniform(0.0, 0.15)  # some on the floor, some slightly elevated
    byaw = random.uniform(0, 360)
    box_path = f"/World/Obstacles/dropped_box_{bi}"
    spawn_asset(box_path, random.choice(_box_usds), bx, by, bz, byaw)
    _apply_physics(box_path)

# Obstacle rect for the dropped pallet (used by forklift avoidance)
_PALLET_OBSTACLE = (
    _pallet_x - PALLET_OBSTACLE_HALF_W,
    _pallet_x + PALLET_OBSTACLE_HALF_W,
    _pallet_y - PALLET_OBSTACLE_HALF_D,
    _pallet_y + PALLET_OBSTACLE_HALF_D,
)

# ==========================================================================
# Visual markers -- red danger zone around pallet, yellow at aisle entrance
# ==========================================================================
TAPE_THICK = 0.02
TAPE_WIDTH = 0.15

def _spawn_tape_rect(prim_base, cx, cy, hw, hd, color):
    """Spawn a rectangle of tape strips on the floor."""
    tw = TAPE_WIDTH / 2.0
    th = TAPE_THICK / 2.0
    z  = TAPE_THICK / 2.0
    strips = [
        ("near",  cx,       cy - hd, hw, tw),
        ("far",   cx,       cy + hd, hw, tw),
        ("left",  cx - hw,  cy,      tw, hd),
        ("right", cx + hw,  cy,      tw, hd),
    ]
    for label, x, y, sx, sy in strips:
        box = UsdGeom.Cube.Define(stage, f"{prim_base}_{label}")
        box.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
        box.AddScaleOp().Set(Gf.Vec3d(sx, sy, th))
        box.GetDisplayColorAttr().Set(color)

# Red danger zone around the dropped pallet
_spawn_tape_rect("/World/Markers/danger_zone",
                 _pallet_x, _pallet_y,
                 PALLET_OBSTACLE_HALF_W + 0.3,
                 PALLET_OBSTACLE_HALF_D + 0.3,
                 [(0.9, 0.1, 0.1)])

# Yellow aisle entrance marker
_spawn_tape_rect("/World/Markers/aisle_entrance",
                 CONGESTION_X, CONGESTION_Y_ENTRANCE,
                 2.0, 0.5,
                 [(1.0, 0.9, 0.0)])

# ==========================================================================
# Congestion observation camera
# ==========================================================================
_cam = UsdGeom.Camera.Define(stage, "/World/Cameras/congestion_cam")
_cam.AddTranslateOp().Set(Gf.Vec3d(CONGESTION_X + 6.0,
                                     CONGESTION_Y_ENTRANCE - 4.0,
                                     8.0))
_cam.AddRotateXYZOp().Set(Gf.Vec3f(55.0, 0.0, 145.0))
_cam.GetFocalLengthAttr().Set(14.0)
_cam.GetHorizontalApertureAttr().Set(20.955)
_cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.1, 100.0))

# ==========================================================================
# Shelf detection (lazy, runs on first physics step)
# ==========================================================================
_SHELF_RECTS      = []
_AISLE_XS         = []
_SHELF_AREA_Y_MIN = None
_SHELF_AREA_Y_MAX = None
_shelves_ready    = False
AISLE_SNAP        = 0.8

_SHELF_KEYWORDS = {"rack", "shelf", "shelv", "pallet_rack", "shelving",
                    "storage", "fixture", "unit"}

def _inside_shelf(x, y, margin=0.0):
    for rx0, rx1, ry0, ry1 in _SHELF_RECTS:
        if rx0 - margin < x < rx1 + margin and ry0 - margin < y < ry1 + margin:
            return True
    return False

def _in_shelf_area(y):
    return (_SHELF_AREA_Y_MIN is not None and
            _SHELF_AREA_Y_MIN - 1.0 < y < _SHELF_AREA_Y_MAX + 1.0)

def _nearest_aisle(x):
    if not _AISLE_XS:
        return x
    return min(_AISLE_XS, key=lambda ax: abs(ax - x))

def _compute_aisles():
    global _SHELF_AREA_Y_MIN, _SHELF_AREA_Y_MAX
    if not _SHELF_RECTS:
        return
    _SHELF_AREA_Y_MIN = min(r[2] for r in _SHELF_RECTS)
    _SHELF_AREA_Y_MAX = max(r[3] for r in _SHELF_RECTS)
    intervals = sorted((r[0], r[1]) for r in _SHELF_RECTS)
    merged = []
    for a, b in intervals:
        if merged and a < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    for i in range(len(merged) - 1):
        gx0, gx1 = merged[i][1], merged[i + 1][0]
        if gx1 - gx0 > 1.0:
            _AISLE_XS.append((gx0 + gx1) / 2.0)
    if merged:
        if merged[0][0] - NAV_X_MIN > 2.0:
            _AISLE_XS.append((NAV_X_MIN + merged[0][0]) / 2.0)
        if NAV_X_MAX - merged[-1][1] > 2.0:
            _AISLE_XS.append((merged[-1][1] + NAV_X_MAX) / 2.0)
    _AISLE_XS.sort()
    print(f"[Congestion] Shelf Y: {_SHELF_AREA_Y_MIN:.1f} -> {_SHELF_AREA_Y_MAX:.1f}")
    print(f"[Congestion] Aisles X: {[round(x, 1) for x in _AISLE_XS]}")

def _detect_forklift_z_offset():
    """Measure how far the forklift's visual bottom is from its translate origin.

    The forklift USD may have internal geometry offset above the prim origin.
    We compute:  offset = -(bbox_bottom_z - translate_z)
    so that setting translate.z = offset puts the wheels on the floor (Z=0).
    """
    global FORKLIFT_GROUND_Z_OFFSET
    if FORKLIFT_GROUND_Z_OFFSET is not None:
        return  # already set (manual override or prior detection)

    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])

    # Use the first forklift prim to measure
    fl_prim = stage.GetPrimAtPath(Sdf.Path(forklifts[0]["path"]))
    if not fl_prim.IsValid():
        FORKLIFT_GROUND_Z_OFFSET = 0.0
        return

    try:
        rng = bbox_cache.ComputeWorldBound(fl_prim).ComputeAlignedRange()
        bbox_bottom = rng.GetMin()[2]
        # Current translate Z
        xf = UsdGeom.Xformable(fl_prim)
        cur_z = 0.0
        for op in xf.GetOrderedXformOps():
            if "translate" in op.GetOpName():
                cur_z = op.Get()[2]
                break
        # The visual bottom is at bbox_bottom; we want it at floor Z=0.
        # If bbox_bottom = 0.8 and cur_z = 0.0, the model floats 0.8m above floor.
        # We need to set translate Z to cur_z - bbox_bottom = -0.8.
        FORKLIFT_GROUND_Z_OFFSET = cur_z - bbox_bottom
        print(f"[Congestion] Forklift bbox bottom Z: {bbox_bottom:.3f}, "
              f"translate Z: {cur_z:.3f}, "
              f"ground offset: {FORKLIFT_GROUND_Z_OFFSET:.3f}")
    except Exception as e:
        print(f"[Congestion] Forklift Z detection failed ({e}), trying fallback")
        FORKLIFT_GROUND_Z_OFFSET = 0.0

    # Also detect warehouse floor Z for additional correction
    wh = stage.GetPrimAtPath(Sdf.Path("/World/Warehouse"))
    if wh.IsValid():
        floor_keywords = {"floor", "ground", "plane"}
        for prim in Usd.PrimRange(wh):
            if any(k in prim.GetName().lower() for k in floor_keywords):
                try:
                    rng = bbox_cache.ComputeWorldBound(prim).ComputeAlignedRange()
                    floor_top_z = rng.GetMax()[2]
                    # Adjust offset so forklift bottom sits on the floor surface
                    FORKLIFT_GROUND_Z_OFFSET += floor_top_z
                    print(f"[Congestion] Floor top Z: {floor_top_z:.3f}, "
                          f"final offset: {FORKLIFT_GROUND_Z_OFFSET:.3f}")
                    return
                except Exception:
                    pass
    print(f"[Congestion] No floor prim found, using offset: {FORKLIFT_GROUND_Z_OFFSET:.3f}")


def _init_shelf_rects():
    global _shelves_ready
    wh_prim = stage.GetPrimAtPath(Sdf.Path("/World/Warehouse"))
    if not wh_prim.IsValid():
        _shelves_ready = True
        return
    _detect_forklift_z_offset()
    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    seen = []
    for prim in Usd.PrimRange(wh_prim):
        if not any(k in prim.GetName().lower() for k in _SHELF_KEYWORDS):
            continue
        if not prim.IsA(UsdGeom.Xformable):
            continue
        try:
            rng = bbox_cache.ComputeWorldBound(prim).ComputeAlignedRange()
            mn, mx = rng.GetMin(), rng.GetMax()
            w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
            if w < 0.5 or d < 0.5 or h < 0.5:
                continue
            rcx, rcy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
            if any(abs(rcx-s[0]) < 0.5 and abs(rcy-s[1]) < 0.5 for s in seen):
                continue
            seen.append((rcx, rcy))
            _SHELF_RECTS.append((mn[0], mx[0], mn[1], mx[1]))
        except Exception:
            pass

    if not _SHELF_RECTS:
        print("[Congestion] No shelf keywords matched -- broad fallback scan.")
        for prim in Usd.PrimRange(wh_prim):
            if not prim.IsA(UsdGeom.Xformable):
                continue
            try:
                rng = bbox_cache.ComputeWorldBound(prim).ComputeAlignedRange()
                mn, mx = rng.GetMin(), rng.GetMax()
                w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
                if w > 4.0 and d > 0.8 and h > 1.5:
                    rcx = (mn[0]+mx[0])/2
                    rcy = (mn[1]+mx[1])/2
                    if any(abs(rcx-s[0]) < 1.0 and abs(rcy-s[1]) < 1.0 for s in seen):
                        continue
                    seen.append((rcx, rcy))
                    _SHELF_RECTS.append((mn[0], mx[0], mn[1], mx[1]))
            except Exception:
                pass

    _compute_aisles()
    _update_congestion_point()
    _shelves_ready = True
    print(f"[Congestion] {len(_SHELF_RECTS)} shelf rects registered.")

def _update_congestion_point():
    """After shelf detection, pick the best aisle for the congestion scenario
    and reposition the dropped pallet and waypoints accordingly."""
    global CONGESTION_X, CONGESTION_Y_ENTRANCE, CONGESTION_Y_INSIDE
    global _pallet_x, _pallet_y, _PALLET_OBSTACLE

    if _AISLE_XS and _SHELF_AREA_Y_MIN is not None:
        # Pick a middle aisle for maximum traffic impact
        mid_idx = len(_AISLE_XS) // 2
        CONGESTION_X = _AISLE_XS[mid_idx]
        CONGESTION_Y_ENTRANCE = _SHELF_AREA_Y_MIN - 0.5
        CONGESTION_Y_INSIDE = (_SHELF_AREA_Y_MIN + _SHELF_AREA_Y_MAX) / 2.0

        # Update pallet position
        _pallet_x = CONGESTION_X + PALLET_DROP_OFFSET_X
        _pallet_y = CONGESTION_Y_ENTRANCE + PALLET_DROP_Y_OFFSET

        # Move the pallet prim to the refined position
        pallet_prim = stage.GetPrimAtPath(Sdf.Path(_pallet_path))
        if pallet_prim.IsValid():
            xf = UsdGeom.Xformable(pallet_prim)
            for op in xf.GetOrderedXformOps():
                if "translate" in op.GetOpName():
                    op.Set(Gf.Vec3d(_pallet_x, _pallet_y, 0.0))
                    break

        # Move scattered boxes near pallet
        random.seed(RANDOM_SEED + 1)
        for bi in range(3):
            bp = stage.GetPrimAtPath(Sdf.Path(f"/World/Obstacles/dropped_box_{bi}"))
            if bp.IsValid():
                bxf = UsdGeom.Xformable(bp)
                for op in bxf.GetOrderedXformOps():
                    if "translate" in op.GetOpName():
                        op.Set(Gf.Vec3d(
                            _pallet_x + random.uniform(-0.8, 0.8),
                            _pallet_y + random.uniform(-0.6, 0.6),
                            random.uniform(0.0, 0.15),
                        ))
                        break

        # Update obstacle rect
        _PALLET_OBSTACLE = (
            _pallet_x - PALLET_OBSTACLE_HALF_W,
            _pallet_x + PALLET_OBSTACLE_HALF_W,
            _pallet_y - PALLET_OBSTACLE_HALF_D,
            _pallet_y + PALLET_OBSTACLE_HALF_D,
        )

        # Move visual markers
        _move_tape_markers()

        # Regenerate forklift waypoints to funnel through the refined aisle
        _regenerate_waypoints()

        print(f"[Congestion] Aisle chosen: X={CONGESTION_X:.1f}, "
              f"entrance Y={CONGESTION_Y_ENTRANCE:.1f}, "
              f"pallet at ({_pallet_x:.1f}, {_pallet_y:.1f})")

def _move_tape_markers():
    """Reposition tape markers after congestion point is refined."""
    # Danger zone around pallet
    for label, dx, dy, sx, sy in [
        ("near",  0, -(PALLET_OBSTACLE_HALF_D+0.3), PALLET_OBSTACLE_HALF_W+0.3, TAPE_WIDTH/2),
        ("far",   0,  (PALLET_OBSTACLE_HALF_D+0.3), PALLET_OBSTACLE_HALF_W+0.3, TAPE_WIDTH/2),
        ("left",  -(PALLET_OBSTACLE_HALF_W+0.3), 0, TAPE_WIDTH/2, PALLET_OBSTACLE_HALF_D+0.3),
        ("right",  (PALLET_OBSTACLE_HALF_W+0.3), 0, TAPE_WIDTH/2, PALLET_OBSTACLE_HALF_D+0.3),
    ]:
        p = stage.GetPrimAtPath(Sdf.Path(f"/World/Markers/danger_zone_{label}"))
        if p.IsValid():
            xf = UsdGeom.Xformable(p)
            for op in xf.GetOrderedXformOps():
                if "translate" in op.GetOpName():
                    op.Set(Gf.Vec3d(_pallet_x + dx, _pallet_y + dy, TAPE_THICK/2))
                    break

    # Aisle entrance marker
    for label, dx, dy, sx, sy in [
        ("near",  0, -0.5, 2.0, TAPE_WIDTH/2),
        ("far",   0,  0.5, 2.0, TAPE_WIDTH/2),
        ("left", -2.0, 0,  TAPE_WIDTH/2, 0.5),
        ("right", 2.0, 0,  TAPE_WIDTH/2, 0.5),
    ]:
        p = stage.GetPrimAtPath(Sdf.Path(f"/World/Markers/aisle_entrance_{label}"))
        if p.IsValid():
            xf = UsdGeom.Xformable(p)
            for op in xf.GetOrderedXformOps():
                if "translate" in op.GetOpName():
                    op.Set(Gf.Vec3d(CONGESTION_X + dx,
                                     CONGESTION_Y_ENTRANCE + dy,
                                     TAPE_THICK/2))
                    break

    # Move the camera
    cam_prim = stage.GetPrimAtPath(Sdf.Path("/World/Cameras/congestion_cam"))
    if cam_prim.IsValid():
        xf = UsdGeom.Xformable(cam_prim)
        for op in xf.GetOrderedXformOps():
            if "translate" in op.GetOpName():
                op.Set(Gf.Vec3d(CONGESTION_X + 6.0,
                                 CONGESTION_Y_ENTRANCE - 4.0,
                                 8.0))
                break

# ==========================================================================
# Forklifts -- all three funnel through the same aisle entrance
# ==========================================================================
_forklift_usd = assets_root + "/Isaac/Props/Forklift/forklift.usd"
forklifts = []

def _make_congestion_waypoints(forklift_idx):
    """Generate waypoints that loop through the congestion aisle.

    Each forklift takes a distinct route: different approach angles,
    different wander points on the open floor, so they arrive at the
    bottleneck at staggered times rather than as a synchronized pack.
    """
    offset_x = (forklift_idx - 1) * 3.0  # -3.0, 0, +3.0 — wider spread

    # Each forklift wanders to a unique open-floor point before converging
    wander_pts = [
        # FL0: approaches from far south-west
        [(-18.0, NAV_Y_MIN + 3.0), (-14.0, CONGESTION_Y_ENTRANCE - 8.0)],
        # FL1: approaches from south-centre, loops east first
        [(CONGESTION_X + 6.0, NAV_Y_MIN + 5.0), (NAV_X_MAX - 3.0, CONGESTION_Y_ENTRANCE - 5.0)],
        # FL2: approaches from south-east, swings wide
        [(NAV_X_MAX - 4.0, NAV_Y_MIN + 4.0), (CONGESTION_X + 8.0, CONGESTION_Y_ENTRANCE - 3.0)],
    ]

    pts = []
    # Unique wander/approach phase
    for wx, wy in wander_pts[forklift_idx]:
        pts.append((wx, wy))
    # Converge toward aisle entrance — staggered X so they queue, not overlap
    pts.append((CONGESTION_X + offset_x * 0.4, CONGESTION_Y_ENTRANCE - 3.0 - forklift_idx * 1.5))
    # Queue point — slightly staggered
    pts.append((CONGESTION_X - 0.3 + forklift_idx * 0.6, CONGESTION_Y_ENTRANCE - 0.5))
    # Through the gap (on the clear side of the dropped pallet)
    pts.append((CONGESTION_X - 0.5, CONGESTION_Y_ENTRANCE + 2.0))
    # Inside the aisle — different depths per forklift
    pts.append((CONGESTION_X, CONGESTION_Y_INSIDE + forklift_idx * 2.0))
    # Exit: each forklift exits to a different side
    exit_offsets = [(-6.0, 4.0), (0.0, 6.0), (6.0, 4.0)]
    ex, ey = exit_offsets[forklift_idx]
    pts.append((CONGESTION_X + ex, CONGESTION_Y_INSIDE + ey))
    # Loop back wide — different return paths
    pts.append((CONGESTION_X + offset_x + forklift_idx * 3.0,
                CONGESTION_Y_ENTRANCE - 6.0 - forklift_idx * 3.0))
    return pts

random.seed(RANDOM_SEED)

# Start positions: staggered south of the shelving area
_start_positions = [
    (CONGESTION_X - 8.0,  NAV_Y_MIN + 3.0),   # far left
    (CONGESTION_X + 4.0,  NAV_Y_MIN + 6.0),   # centre-right
    (NAV_X_MAX - 4.0,     NAV_Y_MIN + 4.0),   # far right
]

for fi in range(3):
    sx, sy = _start_positions[fi]
    path = f"/World/Forklifts/forklift_{fi}"
    spawn_asset(path, _forklift_usd, sx, sy, 0.0, 90.0)
    forklifts.append({
        "path":        path,
        "pos":         [sx, sy],
        "heading":     90.0,
        "speed":       0.0,
        "steer_angle": 0.0,
        "waypoints":   _make_congestion_waypoints(fi),
        "wp_idx":      fi * 2,  # stagger so forklifts start at different waypoints
        "state":       STATE_DRIVE,
        "idle_timer":  0.0,
        "fork_height": 0.0,
        "fork_target": FORK_TRAVEL_HEIGHT,
        "wheel_angle": 0.0,
        "wheel_prims": None,
        "fork_prims":  None,
    })

def _regenerate_waypoints():
    """Refresh all forklift waypoints after congestion point is refined."""
    for fi, fl in enumerate(forklifts):
        fl["waypoints"] = _make_congestion_waypoints(fi)
        # Keep wp_idx valid
        fl["wp_idx"] = fl["wp_idx"] % len(fl["waypoints"])

# ==========================================================================
# Forklift physics helpers (from reference)
# ==========================================================================

def _steer_speed_limit(steer_deg):
    ratio = abs(steer_deg) / FORKLIFT_MAX_STEER
    return FORKLIFT_MAX_SPEED * (1.0 - 0.75 * ratio)

def _braking_distance(speed):
    return (speed * speed) / (2.0 * FORKLIFT_BRAKE)

def _collect_wheel_prims(root_prim):
    found = []
    for child in root_prim.GetAllChildren():
        if "wheel" in child.GetName().lower():
            found.append(child)
        found.extend(_collect_wheel_prims(child))
    return found

def _get_or_add_rotate_x(xform_obj):
    for op in xform_obj.GetOrderedXformOps():
        if "rotateX" in op.GetOpName():
            return op
    return xform_obj.AddRotateXOp()

def _collect_fork_prims(root_prim):
    found = []
    for child in Usd.PrimRange(root_prim):
        name = child.GetName().lower()
        if any(k in name for k in ("fork", "mast", "lift", "carriage", "tine")):
            if child.IsA(UsdGeom.Xformable):
                found.append(child)
    return found

def _update_fork_height(fl, prim, step_dt):
    diff = fl["fork_target"] - fl["fork_height"]
    step = FORK_RAISE_SPEED * step_dt
    if abs(diff) <= step:
        fl["fork_height"] = fl["fork_target"]
    else:
        fl["fork_height"] += math.copysign(step, diff)
    if fl["fork_prims"] is None:
        fl["fork_prims"] = _collect_fork_prims(prim)
    for fp in fl["fork_prims"]:
        xf = UsdGeom.Xformable(fp)
        for op in xf.GetOrderedXformOps():
            if "translate" in op.GetOpName():
                t = op.Get()
                if t is not None:
                    op.Set(Gf.Vec3d(t[0], t[1], fl["fork_height"]))
                break

# ==========================================================================
# Obstacle avoidance -- shelves + dropped pallet
# ==========================================================================

def _inside_obstacle(x, y, margin=0.0):
    """Check collision with both shelves and the dropped pallet."""
    # Pallet obstacle
    ox0, ox1, oy0, oy1 = _PALLET_OBSTACLE
    if (ox0 - margin < x < ox1 + margin and
        oy0 - margin < y < oy1 + margin):
        return True
    # Shelf obstacles
    return _inside_shelf(x, y, margin)

def _dist_to_pallet(x, y):
    """Distance from (x,y) to the centre of the dropped pallet."""
    return math.hypot(x - _pallet_x, y - _pallet_y)

# ==========================================================================
# Forklift movement -- adapted from reference with congestion braking
# ==========================================================================

def _move_forklift(fl, step_dt):
    prim = stage.GetPrimAtPath(Sdf.Path(fl["path"]))
    if not prim.IsValid():
        return

    # -- STATE: IDLE --
    if fl["state"] == STATE_IDLE:
        fl["idle_timer"] -= step_dt
        if fl["idle_timer"] > IDLE_DURATION * 0.5:
            fl["fork_target"] = FORK_GROUND_HEIGHT
        else:
            fl["fork_target"] = FORK_TRAVEL_HEIGHT
        _update_fork_height(fl, prim, step_dt)
        if fl["idle_timer"] <= 0.0:
            fl["state"] = STATE_DRIVE
            fl["wp_idx"] = (fl["wp_idx"] + 1) % len(fl["waypoints"])
        return

    # -- STATE: DRIVE --
    fx, fy = fl["pos"]
    wp = fl["waypoints"][fl["wp_idx"]]

    # Skip waypoints that fall inside shelves or the pallet obstacle
    for _skip in range(len(fl["waypoints"])):
        if not _inside_obstacle(wp[0], wp[1], margin=1.5):
            break
        fl["wp_idx"] = (fl["wp_idx"] + 1) % len(fl["waypoints"])
        wp = fl["waypoints"][fl["wp_idx"]]

    dx, dy = wp[0] - fx, wp[1] - fy
    dist_to_wp = math.hypot(dx, dy)

    # -- Arrival --
    if dist_to_wp < WAYPOINT_ARRIVE:
        fl["speed"] = 0.0
        fl["state"] = STATE_IDLE
        fl["idle_timer"] = IDLE_DURATION
        fl["fork_target"] = FORK_GROUND_HEIGHT
        return

    # -- Lane constraint in shelf area --
    # Also constrain when APPROACHING the shelf area (within 2m) to prevent
    # entering at an angle that would clip a shelf.
    if (_in_shelf_area(fy) or
        (_SHELF_AREA_Y_MIN is not None and
         abs(fy - _SHELF_AREA_Y_MIN) < 2.0 and dy > 0) or
        (_SHELF_AREA_Y_MAX is not None and
         abs(fy - _SHELF_AREA_Y_MAX) < 2.0 and dy < 0)) and _AISLE_XS:
        ax = _nearest_aisle(fx)
        if abs(fx - ax) > AISLE_SNAP:
            dx, dy = ax - fx, 0.0  # merge into aisle first
        else:
            dx, dy = ax - fx, wp[1] - fy  # drive along aisle

    # -- Steering --
    desired_heading = math.degrees(math.atan2(dy, dx)) + FORK_HEADING_OFFSET
    heading_err = (desired_heading - fl["heading"] + 180.0) % 360.0 - 180.0
    steer_target = max(-FORKLIFT_MAX_STEER,
                       min(FORKLIFT_MAX_STEER, heading_err * 0.8))
    steer_diff = steer_target - fl["steer_angle"]
    fl["steer_angle"] += max(-FORKLIFT_STEER_RATE * step_dt,
                              min(FORKLIFT_STEER_RATE * step_dt, steer_diff))

    # -- Speed control --
    max_speed = _steer_speed_limit(fl["steer_angle"])

    # Congestion braking: slow down near the dropped pallet
    pallet_dist = _dist_to_pallet(fx, fy)
    if pallet_dist < CONGESTION_BRAKE_RADIUS:
        congestion_factor = pallet_dist / CONGESTION_BRAKE_RADIUS
        max_speed = min(max_speed, CONGESTION_CREEP_SPEED +
                        (FORKLIFT_MAX_SPEED - CONGESTION_CREEP_SPEED) * congestion_factor)

    # Waypoint braking
    brake_dist = _braking_distance(fl["speed"])
    if dist_to_wp < brake_dist + 0.5:
        target_speed = max(FORKLIFT_MIN_SPEED,
                           math.sqrt(max(0.0, 2.0 * FORKLIFT_BRAKE * (dist_to_wp - 0.3))))
    else:
        target_speed = max_speed

    # Accelerate or brake
    speed_diff = target_speed - fl["speed"]
    if speed_diff > 0:
        fl["speed"] = min(fl["speed"] + FORKLIFT_ACCEL * step_dt, target_speed)
    else:
        fl["speed"] = max(fl["speed"] - FORKLIFT_BRAKE * step_dt, target_speed)
    fl["speed"] = max(0.0, fl["speed"])

    # -- Bicycle kinematic update --
    steer_rad = math.radians(fl["steer_angle"])
    heading_rate = fl["speed"] * math.tan(steer_rad) / FORKLIFT_WHEELBASE
    fl["heading"] += math.degrees(heading_rate) * step_dt

    move_rad = math.radians(fl["heading"] - FORK_HEADING_OFFSET)
    nx = fx + fl["speed"] * step_dt * math.cos(move_rad)
    ny = fy + fl["speed"] * step_dt * math.sin(move_rad)

    # -- Look-ahead: reject move if it enters a shelf, skip waypoint --
    if _inside_shelf(nx, ny, margin=FORKLIFT_BODY):
        nx, ny = fx, fy  # stay put
        fl["speed"] = 0.0
        fl["wp_idx"] = (fl["wp_idx"] + 1) % len(fl["waypoints"])

    # -- Wall clamp --
    nx = max(NAV_X_MIN, min(NAV_X_MAX, nx))
    ny = max(NAV_Y_MIN, min(NAV_Y_MAX, ny))

    # -- Shelf push-out: hard-eject if we clip inside a shelf rect --
    for rx0, rx1, ry0, ry1 in _SHELF_RECTS:
        ex0, ex1 = rx0 - FORKLIFT_BODY, rx1 + FORKLIFT_BODY
        ey0, ey1 = ry0 - FORKLIFT_BODY, ry1 + FORKLIFT_BODY
        if ex0 < nx < ex1 and ey0 < ny < ey1:
            dl, dr = nx - ex0, ex1 - nx
            db, dt = ny - ey0, ey1 - ny
            d_min = min(dl, dr, db, dt)
            if   d_min == dl: nx = ex0
            elif d_min == dr: nx = ex1
            elif d_min == db: ny = ey0
            else:             ny = ey1
            fl["speed"] *= 0.4
            # Skip current waypoint to avoid driving right back into the shelf
            fl["wp_idx"] = (fl["wp_idx"] + 1) % len(fl["waypoints"])
            break

    # -- Pallet obstacle push-out --
    ox0, ox1, oy0, oy1 = _PALLET_OBSTACLE
    pex0, pex1 = ox0 - FORKLIFT_BODY, ox1 + FORKLIFT_BODY
    pey0, pey1 = oy0 - FORKLIFT_BODY, oy1 + FORKLIFT_BODY
    if pex0 < nx < pex1 and pey0 < ny < pey1:
        dl, dr = nx - pex0, pex1 - nx
        db, dt = ny - pey0, pey1 - ny
        d_min = min(dl, dr, db, dt)
        if   d_min == dl: nx = pex0
        elif d_min == dr: nx = pex1
        elif d_min == db: ny = pey0
        else:             ny = pey1
        fl["speed"] *= 0.3  # harder brake near the dropped pallet

    # -- Forklift-to-forklift separation --
    SEP = FORKLIFT_BODY * 2.2
    for other in forklifts:
        if other is fl:
            continue
        ox, oy = other["pos"]
        dist = math.hypot(nx - ox, ny - oy)
        if 0.001 < dist < SEP:
            push = SEP - dist
            nx += (nx - ox) / dist * push
            ny += (ny - oy) / dist * push
            nx = max(NAV_X_MIN, min(NAV_X_MAX, nx))
            ny = max(NAV_Y_MIN, min(NAV_Y_MAX, ny))
            fl["speed"] *= 0.5  # more aggressive slowdown in congestion

    fl["pos"] = [nx, ny]
    fl["fork_target"] = FORK_TRAVEL_HEIGHT

    # -- Apply USD transform --
    xform = UsdGeom.Xformable(prim)
    ops = {op.GetOpName(): op for op in xform.GetOrderedXformOps()}
    t_op = ops.get("xformOp:translate")
    if t_op:
        gz = FORKLIFT_GROUND_Z_OFFSET if FORKLIFT_GROUND_Z_OFFSET is not None else 0.0
        t_op.Set(Gf.Vec3d(nx, ny, gz))
    for op in xform.GetOrderedXformOps():
        if "rotateZ" in op.GetOpName():
            op.Set(fl["heading"])
            break

    # -- Wheel spin --
    if fl["wheel_prims"] is None:
        fl["wheel_prims"] = _collect_wheel_prims(prim)
    if fl["wheel_prims"]:
        fl["wheel_angle"] += math.degrees(fl["speed"] * step_dt / WHEEL_RADIUS)
        for wp_prim in fl["wheel_prims"]:
            _get_or_add_rotate_x(UsdGeom.Xformable(wp_prim)).Set(fl["wheel_angle"])

    # -- Fork height animation --
    _update_fork_height(fl, prim, step_dt)

# ==========================================================================
# Congestion telemetry
# ==========================================================================
_telemetry_interval = 5.0  # seconds between status prints
_telemetry_timer = 0.0

def _print_congestion_status():
    """Print forklift positions and speeds for observability."""
    for fi, fl in enumerate(forklifts):
        d = _dist_to_pallet(fl["pos"][0], fl["pos"][1])
        print(f"  FL{fi}: pos=({fl['pos'][0]:6.1f}, {fl['pos'][1]:6.1f}) "
              f"spd={fl['speed']:.1f} m/s  wp={fl['wp_idx']}  "
              f"state={fl['state']}  dist_to_pallet={d:.1f}m")

# ==========================================================================
# Physics step callback
# ==========================================================================
def on_physics_step(step_dt):
    global _shelves_ready, _telemetry_timer

    if not _shelves_ready:
        _init_shelf_rects()

    for fl in forklifts:
        _move_forklift(fl, step_dt)

    # Periodic telemetry
    _telemetry_timer += step_dt
    if _telemetry_timer >= _telemetry_interval:
        _telemetry_timer = 0.0
        print("[Congestion] Status:")
        _print_congestion_status()

physx_sub = omni.physx.get_physx_interface().subscribe_physics_step_events(
    on_physics_step)

# ==========================================================================
# Start simulation
# ==========================================================================
timeline = omni.timeline.get_timeline_interface()
timeline.play()

print("[Congestion] Aisle congestion scenario loaded:")
print(f"  Warehouse: X [{WALL_X_MIN}, {WALL_X_MAX}]  Y [{WALL_Y_MIN}, {WALL_Y_MAX}]")
print(f"  Congestion aisle (initial): X={CONGESTION_X:.1f}, entrance Y={CONGESTION_Y_ENTRANCE:.1f}")
print(f"  Dropped pallet at ({_pallet_x:.1f}, {_pallet_y:.1f}), yaw={PALLET_YAW} deg")
print(f"  Pallet obstacle rect: {_PALLET_OBSTACLE}")
print("  3 forklifts funneling through the blocked aisle entrance")
print("  Camera: /World/Cameras/congestion_cam")
print("  Congestion brake zone: {:.1f}m radius, creep speed {:.1f} m/s".format(
    CONGESTION_BRAKE_RADIUS, CONGESTION_CREEP_SPEED))
