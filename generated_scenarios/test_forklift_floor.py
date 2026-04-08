#!/usr/bin/env python3
"""
Warehouse + one forklift moving randomly, avoids shelves.
Run inside Isaac Sim: Window > Script Editor > Open > Ctrl+Enter
"""

import math
import random

import omni.kit.commands
import omni.physx
import omni.timeline
import omni.usd
from isaacsim.core.utils.stage import get_current_stage
from isaacsim.storage.native import get_assets_root_path
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

stage = get_current_stage()
assets_root = get_assets_root_path()

omni.kit.commands.execute("DeletePrimsCommand", paths=["/World"])

# Warehouse
wh = UsdGeom.Xform.Define(stage, "/World/Warehouse")
wh.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0))
stage.GetPrimAtPath(Sdf.Path("/World/Warehouse")).GetReferences().AddReference(
    assets_root + "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd")

# Physics
ps = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
ps.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
ps.CreateGravityMagnitudeAttr(9.81)

# Warehouse navigable bounds
NAV_X_MIN, NAV_X_MAX = -24.5, 3.7
NAV_Y_MIN, NAV_Y_MAX = -21.6, 28.8

# Forklift parameters
SPEED = 3.0
TURN_RATE = 80.0
HEADING_OFFSET = 90.0
ARRIVE_RADIUS = 2.0
BODY_HALF = 0.9
AISLE_SNAP = 0.8

# ── Shelf detection data ────────────────────────────────────────────────────
_SHELF_RECTS = []
_AISLE_XS = []
_SHELF_AREA_Y_MIN = None
_SHELF_AREA_Y_MAX = None
_shelves_ready = False
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
    print(f"[TEST] Shelf Y: {_SHELF_AREA_Y_MIN:.1f} -> {_SHELF_AREA_Y_MAX:.1f}")
    print(f"[TEST] Aisles X: {[round(x, 1) for x in _AISLE_XS]}")

def _init_shelf_rects():
    global _shelves_ready
    wh_prim = stage.GetPrimAtPath(Sdf.Path("/World/Warehouse"))
    if not wh_prim.IsValid():
        _shelves_ready = True
        return
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
        print("[TEST] No shelf keywords matched — broad fallback scan.")
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
    _shelves_ready = True
    print(f"[TEST] {len(_SHELF_RECTS)} shelf rects registered.")

# ── Waypoint generation (avoids shelves) ────────────────────────────────────
def _rand_floor_pt(prefer_aisle=False):
    if prefer_aisle and _AISLE_XS and _SHELF_AREA_Y_MIN is not None:
        ax = random.choice(_AISLE_XS)
        ay = random.uniform(_SHELF_AREA_Y_MIN + 1.0, _SHELF_AREA_Y_MAX - 1.0)
        return (ax, ay)
    for _ in range(30):
        x = random.uniform(NAV_X_MIN + 1.0, NAV_X_MAX - 1.0)
        y = random.uniform(NAV_Y_MIN + 1.0, NAV_Y_MAX - 1.0)
        if not _inside_shelf(x, y, margin=1.5):
            return (x, y)
    return (x, y)

def new_waypoints():
    pts = []
    for i in range(8):
        pts.append(_rand_floor_pt(prefer_aisle=(i % 3 == 0)))
    return pts

# ── Spawn forklift ──────────────────────────────────────────────────────────
fl_path = "/World/Forklifts/forklift_0"
fl = UsdGeom.Xform.Define(stage, fl_path)
fl.AddTranslateOp().Set(Gf.Vec3d(-10.0, 0.0, 0.0))
fl.AddRotateZOp().Set(90.0)
stage.GetPrimAtPath(Sdf.Path(fl_path)).GetReferences().AddReference(
    assets_root + "/Isaac/Props/Forklift/forklift.usd")

# Forklift state
random.seed(42)
pos = [-10.0, 0.0]
heading = 90.0
waypoints = []
wp_idx = 0

# ── Physics step ────────────────────────────────────────────────────────────
def on_physics_step(dt):
    global pos, heading, wp_idx, waypoints, _shelves_ready

    # Lazy shelf detection on first step
    if not _shelves_ready:
        _init_shelf_rects()
        waypoints = new_waypoints()

    if not waypoints:
        waypoints = new_waypoints()

    tx, ty = waypoints[wp_idx]

    # Skip waypoints that landed inside a shelf
    for _ in range(len(waypoints)):
        if not _inside_shelf(tx, ty, margin=1.5):
            break
        wp_idx = (wp_idx + 1) % len(waypoints)
        tx, ty = waypoints[wp_idx]

    dx, dy = tx - pos[0], ty - pos[1]
    dist = math.hypot(dx, dy)

    # Arrived — next waypoint
    if dist < ARRIVE_RADIUS:
        wp_idx += 1
        if wp_idx >= len(waypoints):
            waypoints = new_waypoints()
            wp_idx = 0
        return

    # Lane constraint: when in the shelf area, snap to nearest aisle
    if _in_shelf_area(pos[1]) and _AISLE_XS:
        ax = _nearest_aisle(pos[0])
        if abs(pos[0] - ax) > AISLE_SNAP:
            dx, dy = ax - pos[0], 0.0
        else:
            dx, dy = ax - pos[0], ty - pos[1]

    # Steer toward target
    desired = math.degrees(math.atan2(dy, dx)) + HEADING_OFFSET
    err = (desired - heading + 180) % 360 - 180
    heading += max(-TURN_RATE * dt, min(TURN_RATE * dt, err))

    # Move forward
    move_rad = math.radians(heading - HEADING_OFFSET)
    nx = pos[0] + SPEED * dt * math.cos(move_rad)
    ny = pos[1] + SPEED * dt * math.sin(move_rad)

    # Look-ahead: reject move into a shelf, skip waypoint
    if _inside_shelf(nx, ny, margin=BODY_HALF):
        wp_idx = (wp_idx + 1) % len(waypoints)
        if wp_idx == 0:
            waypoints = new_waypoints()
        return

    # Wall clamp
    nx = max(NAV_X_MIN, min(NAV_X_MAX, nx))
    ny = max(NAV_Y_MIN, min(NAV_Y_MAX, ny))

    # Shelf push-out: if we still clip a shelf, eject to nearest edge
    for rx0, rx1, ry0, ry1 in _SHELF_RECTS:
        ex0, ex1 = rx0 - BODY_HALF, rx1 + BODY_HALF
        ey0, ey1 = ry0 - BODY_HALF, ry1 + BODY_HALF
        if ex0 < nx < ex1 and ey0 < ny < ey1:
            dl, dr = nx - ex0, ex1 - nx
            db, dt_ = ny - ey0, ey1 - ny
            d_min = min(dl, dr, db, dt_)
            if   d_min == dl: nx = ex0
            elif d_min == dr: nx = ex1
            elif d_min == db: ny = ey0
            else:             ny = ey1
            wp_idx = (wp_idx + 1) % len(waypoints)
            if wp_idx == 0:
                waypoints = new_waypoints()
            break

    pos[0], pos[1] = nx, ny

    # Update prim
    prim = stage.GetPrimAtPath(Sdf.Path(fl_path))
    xf = UsdGeom.Xformable(prim)
    for op in xf.GetOrderedXformOps():
        name = op.GetOpName()
        if "translate" in name:
            cur = op.Get()
            op.Set(Gf.Vec3d(nx, ny, cur[2]))
        elif "rotateZ" in name:
            op.Set(heading)

physx_sub = omni.physx.get_physx_interface().subscribe_physics_step_events(on_physics_step)

timeline = omni.timeline.get_timeline_interface()
timeline.play()

print("[TEST] Loaded: warehouse + 1 forklift with shelf avoidance.")
