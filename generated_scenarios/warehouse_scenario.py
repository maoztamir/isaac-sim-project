#!/usr/bin/env python3
"""
Warehouse simulation with 3 zones, loading doors, staging props,
shelf-aware forklift routing, FSM, zone occupancy, and dwell tracking.

Scenario presets (change SCENARIO below):
  "dock_queue"       — forklifts queue at loading dock
  "loading_pause"    — one forklift stalls at dock, others wait
  "area_buildup"     — all converge on staging area
  "aisle_congestion" — forklifts funnel through one shelf aisle

Run inside Isaac Sim: Window > Script Editor > Open > Ctrl+Enter
"""

# ═══════════════════════════════════════════════════════════════════════════
# SELECT SCENARIO
# ═══════════════════════════════════════════════════════════════════════════
SCENARIO = "dock_queue"
SEED = 42

# ═══════════════════════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════
WALL_X_MIN, WALL_X_MAX = -26.33,  5.46
WALL_Y_MIN, WALL_Y_MAX = -23.40, 30.60
WALL_MARGIN = 1.8
NAV_X_MIN = WALL_X_MIN + WALL_MARGIN
NAV_X_MAX = WALL_X_MAX - WALL_MARGIN
NAV_Y_MIN = WALL_Y_MIN + WALL_MARGIN
NAV_Y_MAX = WALL_Y_MAX - WALL_MARGIN
WH_CX = (WALL_X_MIN + WALL_X_MAX) / 2.0

# Forklift kinematics
FL_WHEELBASE   = 2.4
FL_MAX_SPEED   = 3.0
FL_MIN_SPEED   = 0.4
FL_ACCEL       = 1.5
FL_BRAKE       = 2.5
FL_MAX_STEER   = 65.0
FL_STEER_RATE  = 100.0
FL_HEAD_OFF    = 90.0
FL_BODY        = 0.9
FL_ARRIVE      = 2.0
AISLE_SNAP     = 0.8

# FSM timing
IDLE_DUR    = 3.5
LOADING_DUR = 5.0

# Gate geometry
GATE_OFFSETS = [-7.0, 0.0, 7.0]
GATE_W, GATE_H, GATE_D = 4.0, 4.5, 0.18
POST_W, DRUM_H = 0.20, 0.55
OPEN_W = GATE_W - 2 * POST_W
OPEN_H = GATE_H - DRUM_H
PANEL_N = 8
PANEL_H = OPEN_H / PANEL_N
GUIDE_W, SEAL_H = 0.03, 0.05
HOLE_DEPTH, WALL_T = 2.0, 0.5

# Zone geometry
LOAD_W, LOAD_D = 4.0, 4.5
STAGE_W, STAGE_D = 8.0, 7.0
STAGE_Y_NEAR = WALL_Y_MIN + LOAD_D + 1.0
STAGE_Y_FAR  = STAGE_Y_NEAR + STAGE_D
STAGE_CY     = (STAGE_Y_NEAR + STAGE_Y_FAR) / 2.0

# Zebra tape
TAPE_T, TAPE_W = 0.02, 0.25
STRIPE_SP, STRIPE_T = 0.40, 0.06
COL_YELLOW = [(1.0, 0.85, 0.0)]
COL_BLACK  = [(0.10, 0.10, 0.10)]
COL_STEEL  = [(0.35, 0.36, 0.40)]
COL_SHUT   = [(0.48, 0.50, 0.54)]
COL_SEAL   = [(0.06, 0.06, 0.06)]
COL_WALL   = [(0.60, 0.57, 0.53)]
COL_HOLE   = [(0.02, 0.02, 0.02)]

# Shelf detection
SHELF_KW = {"rack", "shelf", "shelv", "pallet_rack", "shelving",
            "storage", "fixture", "unit"}

# Asset paths
WH_USD = assets_root + "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd"
FL_USD = assets_root + "/Isaac/Props/Forklift/forklift.usd"
PALLET_USD = assets_root + "/Isaac/Props/Pallet/pallet.usd"
BOX_USDS = [
    assets_root + "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxA_01.usd",
    assets_root + "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxB_01.usd",
    assets_root + "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxC_01.usd",
    assets_root + "/Isaac/Environments/Simple_Warehouse/Props/SM_CardBoxD_01.usd",
]

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def spawn_asset(prim_path, asset_path, x, y, z=0.0, yaw=0.0):
    xf = UsdGeom.Xform.Define(stage, prim_path)
    xf.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
    xf.AddRotateZOp().Set(yaw)
    stage.GetPrimAtPath(Sdf.Path(prim_path)).GetReferences().AddReference(asset_path)

def update_pose(prim_path, x, y, heading):
    prim = stage.GetPrimAtPath(Sdf.Path(prim_path))
    if not prim.IsValid():
        return
    for op in UsdGeom.Xformable(prim).GetOrderedXformOps():
        n = op.GetOpName()
        if "translate" in n:
            cur = op.Get()
            op.Set(Gf.Vec3d(x, y, cur[2]))
        elif "rotateZ" in n:
            op.Set(heading)

# ═══════════════════════════════════════════════════════════════════════════
# CLEAR + WAREHOUSE + PHYSICS
# ═══════════════════════════════════════════════════════════════════════════
omni.kit.commands.execute("DeletePrimsCommand", paths=["/World"])
spawn_asset("/World/Warehouse", WH_USD, 0, 0, 0)
ps = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
ps.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
ps.CreateGravityMagnitudeAttr(9.81)

# ═══════════════════════════════════════════════════════════════════════════
# LOADING DOCK GATES
# ═══════════════════════════════════════════════════════════════════════════
def _spawn_gate(idx, dcx):
    gy = WALL_Y_MIN + GATE_D / 2
    fb = f"/World/DockingDoors/gate_{idx}/frame"
    UsdGeom.Xform.Define(stage, fb)
    for side, s in (("post_l", -1), ("post_r", 1)):
        px = dcx + s * (GATE_W / 2 - POST_W / 2)
        p = UsdGeom.Cube.Define(stage, f"{fb}/{side}")
        p.AddTranslateOp().Set(Gf.Vec3d(px, gy, GATE_H / 2))
        p.AddScaleOp().Set(Gf.Vec3d(POST_W / 2, GATE_D / 2, GATE_H / 2))
        p.GetDisplayColorAttr().Set(COL_STEEL)
    d = UsdGeom.Cube.Define(stage, f"{fb}/drum")
    d.AddTranslateOp().Set(Gf.Vec3d(dcx, gy, GATE_H - DRUM_H / 2))
    d.AddScaleOp().Set(Gf.Vec3d(OPEN_W / 2, GATE_D / 2, DRUM_H / 2))
    d.GetDisplayColorAttr().Set(COL_STEEL)
    for side, s in (("gl", -1), ("gr", 1)):
        gx = dcx + s * (OPEN_W / 2 + GUIDE_W / 2)
        g = UsdGeom.Cube.Define(stage, f"{fb}/{side}")
        g.AddTranslateOp().Set(Gf.Vec3d(gx, gy, OPEN_H / 2))
        g.AddScaleOp().Set(Gf.Vec3d(GUIDE_W / 2, GATE_D / 2 + 0.01, OPEN_H / 2))
        g.GetDisplayColorAttr().Set(COL_STEEL)
    sb = f"/World/DockingDoors/gate_{idx}/shutter"
    UsdGeom.Xform.Define(stage, sb)
    for pi in range(PANEL_N):
        pz = pi * PANEL_H + PANEL_H / 2
        pn = UsdGeom.Cube.Define(stage, f"{sb}/p{pi}")
        pn.AddTranslateOp().Set(Gf.Vec3d(dcx, gy, pz))
        pn.AddScaleOp().Set(Gf.Vec3d(OPEN_W / 2, GATE_D / 2, PANEL_H / 2 - 0.005))
        pn.GetDisplayColorAttr().Set(COL_SHUT)
    sl = UsdGeom.Cube.Define(stage, f"{sb}/seal")
    sl.AddTranslateOp().Set(Gf.Vec3d(dcx, gy, SEAL_H / 2))
    sl.AddScaleOp().Set(Gf.Vec3d(OPEN_W / 2, GATE_D / 2, SEAL_H / 2))
    sl.GetDisplayColorAttr().Set(COL_SEAL)
    hcy = WALL_Y_MIN - HOLE_DEPTH / 2
    h = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/hole")
    h.AddTranslateOp().Set(Gf.Vec3d(dcx, hcy, OPEN_H / 2))
    h.AddScaleOp().Set(Gf.Vec3d(OPEN_W / 2, HOLE_DEPTH / 2, OPEN_H / 2))
    h.GetDisplayColorAttr().Set(COL_HOLE)
    jcy = WALL_Y_MIN - WALL_T / 2
    for side, s in (("l", -1), ("r", 1)):
        j = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/j{side}")
        j.AddTranslateOp().Set(Gf.Vec3d(dcx + s * (OPEN_W / 2 + WALL_T / 2), jcy, OPEN_H / 2))
        j.AddScaleOp().Set(Gf.Vec3d(WALL_T / 2, WALL_T / 2, OPEN_H / 2))
        j.GetDisplayColorAttr().Set(COL_WALL)
    lt = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/lintel")
    lt.AddTranslateOp().Set(Gf.Vec3d(dcx, jcy, OPEN_H + WALL_T / 2))
    lt.AddScaleOp().Set(Gf.Vec3d((OPEN_W + 2 * WALL_T) / 2, WALL_T / 2, WALL_T / 2))
    lt.GetDisplayColorAttr().Set(COL_WALL)

for _i, _off in enumerate(GATE_OFFSETS):
    _spawn_gate(_i, WH_CX + _off)

# ═══════════════════════════════════════════════════════════════════════════
# ZEBRA TAPE MARKINGS
# ═══════════════════════════════════════════════════════════════════════════
def _zebra_edge(pb, horiz, ex, ey, elen):
    th = TAPE_T / 2; tw = TAPE_W / 2
    sx, sy = (elen / 2, tw) if horiz else (tw, elen / 2)
    b = UsdGeom.Cube.Define(stage, f"{pb}_b")
    b.AddTranslateOp().Set(Gf.Vec3d(ex, ey, TAPE_T / 2))
    b.AddScaleOp().Set(Gf.Vec3d(sx, sy, th))
    b.GetDisplayColorAttr().Set(COL_BLACK)
    diag = TAPE_W * 1.5; n = int(elen / STRIPE_SP) + 1
    for i in range(n):
        t = -elen / 2 + i * STRIPE_SP
        bx = ex + t if horiz else ex
        by = ey if horiz else ey + t
        s = UsdGeom.Cube.Define(stage, f"{pb}_s{i}")
        s.AddTranslateOp().Set(Gf.Vec3d(bx, by, TAPE_T + th))
        s.AddRotateZOp().Set(45.0)
        s.AddScaleOp().Set(Gf.Vec3d(diag / 2, STRIPE_T / 2, th))
        s.GetDisplayColorAttr().Set(COL_YELLOW)

def _zebra_rect(pb, cx, cy, w, d):
    hw, hd = w / 2, d / 2
    for lb, h, ex, ey, el in [("s", True, cx, cy-hd, w), ("n", True, cx, cy+hd, w),
                               ("w", False, cx-hw, cy, d), ("e", False, cx+hw, cy, d)]:
        _zebra_edge(f"{pb}/{lb}", h, ex, ey, el)

# Loading zone markings
for _i, _off in enumerate(GATE_OFFSETS):
    _zebra_rect(f"/World/LoadZones/z{_i}", WH_CX + _off,
                WALL_Y_MIN + LOAD_D / 2, LOAD_W, LOAD_D)

# Staging area markings
for _i, _off in enumerate(GATE_OFFSETS):
    _zebra_rect(f"/World/StageZones/z{_i}", WH_CX + _off,
                STAGE_CY, STAGE_W, STAGE_D)

# ═══════════════════════════════════════════════════════════════════════════
# STAGING PROPS (pallets + boxes)
# ═══════════════════════════════════════════════════════════════════════════
random.seed(7)
for _zi, _off in enumerate(GATE_OFFSETS):
    _zcx = WH_CX + _off
    _hw = STAGE_W / 2 - 1.2; _hd = STAGE_D / 2 - 1.0
    for _pi in range(random.randint(3, 6)):
        _px = _zcx + random.uniform(-_hw, _hw)
        _py = STAGE_CY + random.uniform(-_hd, _hd)
        _yaw = random.choice([0, 90, 180, -90])
        _base = f"/World/StageProps/z{_zi}_s{_pi}"
        spawn_asset(f"{_base}_pal", PALLET_USD, _px, _py, 0, _yaw)
        UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(Sdf.Path(f"{_base}_pal")))
        _z = 0.15
        for _bi in range(random.randint(1, 3)):
            spawn_asset(f"{_base}_b{_bi}", random.choice(BOX_USDS), _px, _py, _z, _yaw)
            UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(Sdf.Path(f"{_base}_b{_bi}")))
            _z += 0.55

# ═══════════════════════════════════════════════════════════════════════════
# SHELF DETECTION
# ═══════════════════════════════════════════════════════════════════════════
_SHELF_RECTS = []
_AISLE_XS = []
_SHELF_Y_MIN = None
_SHELF_Y_MAX = None
_shelves_ready = False

def _inside_shelf(x, y, m=0.0):
    for r0, r1, r2, r3 in _SHELF_RECTS:
        if r0 - m < x < r1 + m and r2 - m < y < r3 + m:
            return True
    return False

def _in_shelf_area(y):
    return _SHELF_Y_MIN is not None and _SHELF_Y_MIN - 1 < y < _SHELF_Y_MAX + 1

def _nearest_aisle(x):
    if not _AISLE_XS: return x
    return min(_AISLE_XS, key=lambda a: abs(a - x))

def _init_shelves():
    global _shelves_ready, _SHELF_Y_MIN, _SHELF_Y_MAX
    wh = stage.GetPrimAtPath(Sdf.Path("/World/Warehouse"))
    if not wh.IsValid():
        _shelves_ready = True; return
    bc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    seen = []
    for p in Usd.PrimRange(wh):
        if not any(k in p.GetName().lower() for k in SHELF_KW): continue
        if not p.IsA(UsdGeom.Xformable): continue
        try:
            r = bc.ComputeWorldBound(p).ComputeAlignedRange()
            mn, mx = r.GetMin(), r.GetMax()
            w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
            if w < 0.5 or d < 0.5 or h < 0.5: continue
            cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
            if any(abs(cx-s[0]) < 0.5 and abs(cy-s[1]) < 0.5 for s in seen): continue
            seen.append((cx, cy))
            _SHELF_RECTS.append((mn[0], mx[0], mn[1], mx[1]))
        except Exception: pass
    if not _SHELF_RECTS:
        for p in Usd.PrimRange(wh):
            if not p.IsA(UsdGeom.Xformable): continue
            try:
                r = bc.ComputeWorldBound(p).ComputeAlignedRange()
                mn, mx = r.GetMin(), r.GetMax()
                w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
                if w > 4 and d > 0.8 and h > 1.5:
                    cx = (mn[0]+mx[0])/2; cy = (mn[1]+mx[1])/2
                    if any(abs(cx-s[0]) < 1 and abs(cy-s[1]) < 1 for s in seen): continue
                    seen.append((cx, cy))
                    _SHELF_RECTS.append((mn[0], mx[0], mn[1], mx[1]))
            except Exception: pass
    if _SHELF_RECTS:
        _SHELF_Y_MIN = min(r[2] for r in _SHELF_RECTS)
        _SHELF_Y_MAX = max(r[3] for r in _SHELF_RECTS)
        ivs = sorted((r[0], r[1]) for r in _SHELF_RECTS)
        mg = []
        for a, b in ivs:
            if mg and a < mg[-1][1]: mg[-1] = (mg[-1][0], max(mg[-1][1], b))
            else: mg.append((a, b))
        for i in range(len(mg) - 1):
            g0, g1 = mg[i][1], mg[i+1][0]
            if g1 - g0 > 1: _AISLE_XS.append((g0 + g1) / 2)
        if mg:
            if mg[0][0] - NAV_X_MIN > 2: _AISLE_XS.append((NAV_X_MIN + mg[0][0]) / 2)
            if NAV_X_MAX - mg[-1][1] > 2: _AISLE_XS.append((mg[-1][1] + NAV_X_MAX) / 2)
        _AISLE_XS.sort()
    _shelves_ready = True
    print(f"[Warehouse] {len(_SHELF_RECTS)} shelves, {len(_AISLE_XS)} aisles")

# ═══════════════════════════════════════════════════════════════════════════
# ZONES (occupancy + dwell tracking)
# ═══════════════════════════════════════════════════════════════════════════
_lx0 = WH_CX + GATE_OFFSETS[0] - LOAD_W / 2
_lx1 = WH_CX + GATE_OFFSETS[-1] + LOAD_W / 2
_sx0 = WH_CX + GATE_OFFSETS[0] - STAGE_W / 2
_sx1 = WH_CX + GATE_OFFSETS[-1] + STAGE_W / 2

class Zone:
    def __init__(self, name, x0, x1, y0, y1):
        self.name, self.x0, self.x1, self.y0, self.y1 = name, x0, x1, y0, y1
        self._occ = set()
        self._entry = {}
    def contains(self, x, y):
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1
    @property
    def occupancy(self): return len(self._occ)
    @property
    def occupant_ids(self): return set(self._occ)
    def update(self, fid, x, y, t):
        inside = self.contains(x, y)
        was = fid in self._occ
        if inside and not was: self._occ.add(fid); self._entry[fid] = t
        elif not inside and was: self._occ.discard(fid); self._entry.pop(fid, None)
    def dwell(self, fid, t):
        e = self._entry.get(fid); return (t - e) if e else 0.0
    @property
    def center(self): return ((self.x0+self.x1)/2, (self.y0+self.y1)/2)

zones = {
    "LoadingZone": Zone("LoadingZone", _lx0, _lx1, WALL_Y_MIN, WALL_Y_MIN + LOAD_D),
    "StagingArea": Zone("StagingArea", _sx0, _sx1, STAGE_Y_NEAR, STAGE_Y_FAR),
    "ShelvesArea": Zone("ShelvesArea", NAV_X_MIN, NAV_X_MAX, STAGE_Y_FAR + 1, NAV_Y_MAX),
}

def zone_of(x, y):
    for z in zones.values():
        if z.contains(x, y): return z
    return None

# ═══════════════════════════════════════════════════════════════════════════
# WAYPOINT GENERATION
# ═══════════════════════════════════════════════════════════════════════════
rng = random.Random(SEED)

def rand_pt(prefer_aisle=False):
    if prefer_aisle and _AISLE_XS and _SHELF_Y_MIN is not None:
        return (rng.choice(_AISLE_XS),
                rng.uniform(_SHELF_Y_MIN + 1, _SHELF_Y_MAX - 1))
    for _ in range(30):
        x = rng.uniform(NAV_X_MIN + 1, NAV_X_MAX - 1)
        y = rng.uniform(NAV_Y_MIN + 1, NAV_Y_MAX - 1)
        if not _inside_shelf(x, y, 1.5): return (x, y)
    return (x, y)

def rand_zone_pt(z):
    for _ in range(30):
        x = rng.uniform(z.x0 + 0.5, z.x1 - 0.5)
        y = rng.uniform(z.y0 + 0.5, z.y1 - 0.5)
        if not _inside_shelf(x, y, 1.5): return (x, y)
    return z.center

def gen_patrol(n=8):
    return [rand_pt(prefer_aisle=(i % 3 == 0)) for i in range(n)]

def gen_zone_route(zone_list, pts_per=2):
    pts = []
    for z in zone_list:
        for _ in range(pts_per): pts.append(rand_zone_pt(z))
    return pts

# ═══════════════════════════════════════════════════════════════════════════
# FORKLIFT FSM
# ═══════════════════════════════════════════════════════════════════════════
ST_DRIVE, ST_IDLE, ST_LOADING, ST_WAIT = "drive", "idle", "loading", "waiting"

class Forklift:
    def __init__(self, fid, path, x, y):
        self.id, self.path = fid, path
        self.pos, self.heading, self.speed, self.steer = [x, y], 90.0, 0.0, 0.0
        self.state, self.timer = ST_DRIVE, 0.0
        self.wps, self.wpi = [], 0

    def set_wps(self, wps, start=0):
        self.wps = wps; self.wpi = start % max(1, len(wps))

    def _adv(self):
        if self.wps: self.wpi = (self.wpi + 1) % len(self.wps)

    def _blocked(self, all_fl):
        rd = math.radians(self.heading - FL_HEAD_OFF)
        lx = self.pos[0] + FL_BODY * 4 * math.cos(rd)
        ly = self.pos[1] + FL_BODY * 4 * math.sin(rd)
        for o in all_fl:
            if o.id == self.id: continue
            if math.hypot(lx - o.pos[0], ly - o.pos[1]) < FL_BODY * 3: return True
        return False

    def enter_loading(self):
        self.state, self.timer, self.speed = ST_LOADING, LOADING_DUR, 0.0

    def update(self, dt, all_fl):
        if self.state == ST_IDLE:
            self.timer -= dt
            if self.timer <= 0: self.state = ST_DRIVE; self._adv()
            return
        if self.state == ST_LOADING:
            self.timer -= dt
            if self.timer <= 0: self.state = ST_DRIVE; self._adv()
            return
        if self.state == ST_WAIT:
            if not self._blocked(all_fl): self.state = ST_DRIVE
            return
        if not self.wps: return

        tx, ty = self.wps[self.wpi]
        for _ in range(len(self.wps)):
            if not _inside_shelf(tx, ty, 1.5): break
            self._adv(); tx, ty = self.wps[self.wpi]

        fx, fy = self.pos
        dx, dy = tx - fx, ty - fy
        dist = math.hypot(dx, dy)

        if dist < FL_ARRIVE:
            self.speed = 0; self.state = ST_IDLE; self.timer = IDLE_DUR
            update_pose(self.path, fx, fy, self.heading); return

        if self._blocked(all_fl):
            self.speed = 0; self.state = ST_WAIT; return

        if _in_shelf_area(fy) and _AISLE_XS:
            ax = _nearest_aisle(fx)
            if abs(fx - ax) > AISLE_SNAP: dx, dy = ax - fx, 0.0
            else: dx, dy = ax - fx, ty - fy

        des = math.degrees(math.atan2(dy, dx)) + FL_HEAD_OFF
        err = (des - self.heading + 180) % 360 - 180
        st_tgt = max(-FL_MAX_STEER, min(FL_MAX_STEER, err * 0.8))
        sd = st_tgt - self.steer
        self.steer += max(-FL_STEER_RATE * dt, min(FL_STEER_RATE * dt, sd))

        sr = abs(self.steer) / FL_MAX_STEER
        ms = FL_MAX_SPEED * (1 - 0.75 * sr)
        bd = self.speed ** 2 / (2 * FL_BRAKE)
        ts = max(FL_MIN_SPEED, math.sqrt(max(0, 2*FL_BRAKE*(dist-0.3)))) if dist < bd + 0.5 else ms
        if ts > self.speed: self.speed = min(self.speed + FL_ACCEL * dt, ts)
        else: self.speed = max(self.speed - FL_BRAKE * dt, ts)
        self.speed = max(0, self.speed)

        hr = self.speed * math.tan(math.radians(self.steer)) / FL_WHEELBASE
        self.heading += math.degrees(hr) * dt
        mr = math.radians(self.heading - FL_HEAD_OFF)
        nx = fx + self.speed * dt * math.cos(mr)
        ny = fy + self.speed * dt * math.sin(mr)

        if _inside_shelf(nx, ny, FL_BODY): self._adv(); return

        nx = max(NAV_X_MIN, min(NAV_X_MAX, nx))
        ny = max(NAV_Y_MIN, min(NAV_Y_MAX, ny))

        for r0, r1, r2, r3 in _SHELF_RECTS:
            e0, e1 = r0 - FL_BODY, r1 + FL_BODY
            e2, e3 = r2 - FL_BODY, r3 + FL_BODY
            if e0 < nx < e1 and e2 < ny < e3:
                dl, dr, db, dt_ = nx-e0, e1-nx, ny-e2, e3-ny
                dm = min(dl, dr, db, dt_)
                if dm == dl: nx = e0
                elif dm == dr: nx = e1
                elif dm == db: ny = e2
                else: ny = e3
                self.speed *= 0.4; self._adv(); break

        sep = FL_BODY * 2.2
        for o in all_fl:
            if o.id == self.id: continue
            d = math.hypot(nx - o.pos[0], ny - o.pos[1])
            if 0.001 < d < sep:
                push = sep - d
                nx += (nx - o.pos[0]) / d * push
                ny += (ny - o.pos[1]) / d * push
                nx = max(NAV_X_MIN, min(NAV_X_MAX, nx))
                ny = max(NAV_Y_MIN, min(NAV_Y_MAX, ny))
                self.speed *= 0.5

        self.pos = [nx, ny]
        update_pose(self.path, nx, ny, self.heading)

# ═══════════════════════════════════════════════════════════════════════════
# SPAWN FORKLIFTS + SCENARIO SETUP
# ═══════════════════════════════════════════════════════════════════════════
forklifts = []

def _spawn_forklifts(n, starts=None):
    for i in range(n):
        sx, sy = starts[i] if starts else (NAV_X_MIN + 3 + i * 7, NAV_Y_MIN + 3)
        p = f"/World/Forklifts/forklift_{i}"
        spawn_asset(p, FL_USD, sx, sy, 0, 90)
        forklifts.append(Forklift(i, p, sx, sy))

def _setup_dock_queue():
    starts = [(NAV_X_MIN+3, NAV_Y_MIN+3), (NAV_X_MIN+3, NAV_Y_MIN+7),
              (NAV_X_MIN+8, NAV_Y_MIN+3), (NAV_X_MIN+8, NAV_Y_MIN+7)]
    _spawn_forklifts(4, starts)

def _setup_loading_pause():
    _spawn_forklifts(3)

def _setup_area_buildup():
    _spawn_forklifts(4)

def _setup_aisle_congestion():
    _spawn_forklifts(3)

_SETUP = {
    "dock_queue": _setup_dock_queue,
    "loading_pause": _setup_loading_pause,
    "area_buildup": _setup_area_buildup,
    "aisle_congestion": _setup_aisle_congestion,
}

_SETUP.get(SCENARIO, _setup_dock_queue)()

# ═══════════════════════════════════════════════════════════════════════════
# WAYPOINT ASSIGNMENT (after shelf detection)
# ═══════════════════════════════════════════════════════════════════════════
_wps_assigned = False

def _assign_waypoints():
    global _wps_assigned; _wps_assigned = True
    ld = zones["LoadingZone"]; sa = zones["StagingArea"]; sh = zones["ShelvesArea"]

    if SCENARIO == "dock_queue":
        for fl in forklifts:
            fl.set_wps(gen_zone_route([sa, ld, sh]), start=fl.id * 2)
    elif SCENARIO == "loading_pause":
        for fl in forklifts:
            if fl.id == 0:
                fl.set_wps(gen_zone_route([ld], pts_per=1))
            else:
                fl.set_wps(gen_zone_route([sa, sh, ld]))
    elif SCENARIO == "area_buildup":
        for fl in forklifts:
            wps = [rand_zone_pt(sa) for _ in range(3)] + [rand_pt(prefer_aisle=True)]
            fl.set_wps(wps, start=fl.id)
    elif SCENARIO == "aisle_congestion":
        ax = _AISLE_XS[len(_AISLE_XS)//2] if _AISLE_XS else WH_CX
        ym = _SHELF_Y_MIN or STAGE_Y_FAR + 2
        yx = _SHELF_Y_MAX or NAV_Y_MAX - 2
        for fl in forklifts:
            sp = (fl.id - 1) * 5
            fl.set_wps([
                (ax + sp, NAV_Y_MIN + 3 + fl.id * 2),
                (ax, ym - 1),
                (ax, (ym + yx) / 2 + fl.id * 2),
                (ax, yx + 1),
                (ax + sp + 4, NAV_Y_MIN + 5),
            ], start=fl.id)
    else:
        for fl in forklifts:
            fl.set_wps(gen_patrol(), start=fl.id * 2)

# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO-SPECIFIC PER-STEP LOGIC
# ═══════════════════════════════════════════════════════════════════════════
_stall_triggered = False

def _scenario_step(dt, sim_time):
    global _stall_triggered
    ld = zones["LoadingZone"]; sa = zones["StagingArea"]

    if SCENARIO == "dock_queue":
        for fl in forklifts:
            if fl.state == ST_IDLE and ld.contains(fl.pos[0], fl.pos[1]):
                fl.enter_loading()

    elif SCENARIO == "loading_pause":
        fl0 = forklifts[0]
        if (not _stall_triggered and fl0.state == ST_IDLE and
                ld.contains(fl0.pos[0], fl0.pos[1])):
            fl0.state = ST_LOADING; fl0.timer = 15.0
            _stall_triggered = True
            print(f"[loading_pause] FL0 stalled at dock for 15s!")

    elif SCENARIO == "area_buildup":
        if sa.occupancy >= 3:
            for fid in sa.occupant_ids:
                if sa.dwell(fid, sim_time) > 10:
                    print(f"[area_buildup] WARNING: FL{fid} in StagingArea "
                          f"for {sa.dwell(fid, sim_time):.1f}s")
        for fl in forklifts:
            if fl.state == ST_DRIVE and fl.wpi == 0 and fl.wps:
                wps = [rand_zone_pt(sa) for _ in range(3)] + [rand_pt(prefer_aisle=True)]
                fl.set_wps(wps)

    elif SCENARIO == "aisle_congestion":
        if _SHELF_Y_MIN is not None:
            n = sum(1 for fl in forklifts if _in_shelf_area(fl.pos[1]))
            if n >= 2 and int(sim_time) % 10 == 0:
                print(f"[aisle_congestion] {n} forklifts in shelf area")

# ═══════════════════════════════════════════════════════════════════════════
# PHYSICS STEP
# ═══════════════════════════════════════════════════════════════════════════
sim_time = 0.0
_tele_timer = 0.0

def on_physics_step(dt):
    global sim_time, _tele_timer, _wps_assigned

    if not _shelves_ready:
        _init_shelves()
    if not _wps_assigned:
        _assign_waypoints()

    sim_time += dt

    for fl in forklifts:
        fl.update(dt, forklifts)

    for fl in forklifts:
        for z in zones.values():
            z.update(fl.id, fl.pos[0], fl.pos[1], sim_time)

    _scenario_step(dt, sim_time)

    _tele_timer += dt
    if _tele_timer >= 10.0:
        _tele_timer = 0.0
        print(f"[{SCENARIO}] t={sim_time:.1f}s")
        for fl in forklifts:
            z = zone_of(fl.pos[0], fl.pos[1])
            zn = z.name if z else "open"
            print(f"  FL{fl.id}: ({fl.pos[0]:6.1f},{fl.pos[1]:6.1f}) "
                  f"spd={fl.speed:.1f} st={fl.state} zone={zn}")
        for z in zones.values():
            ids = sorted(z.occupant_ids)
            dw = [f"FL{i}={z.dwell(i, sim_time):.1f}s" for i in ids]
            print(f"  [{z.name}] occ={z.occupancy} {' '.join(dw)}")

physx_sub = omni.physx.get_physx_interface().subscribe_physics_step_events(on_physics_step)

timeline = omni.timeline.get_timeline_interface()
timeline.play()

print(f"[{SCENARIO}] Loaded: {len(forklifts)} forklifts, "
      f"{len(zones)} zones, 3 dock gates.")
