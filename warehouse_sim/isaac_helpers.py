"""
Isaac Sim API isolation layer.

Every call into omni.* / pxr.* lives here so the rest of the codebase
stays testable and version-change impact is contained.
"""

from __future__ import annotations
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics


# ── App helpers ─────────────────────────────────────────────────────────────

async def next_update():
    """Yield one app update so USD loading / Nucleus calls can complete."""
    import omni.kit.app
    await omni.kit.app.get_app().next_update_async()


# ── Stage access ────────────────────────────────────────────────────────────

def get_stage():
    """Return the current USD stage."""
    from isaacsim.core.utils.stage import get_current_stage
    return get_current_stage()


def get_assets_root():
    """Return the Nucleus/local assets root path string."""
    from isaacsim.storage.native import get_assets_root_path
    root = get_assets_root_path()
    if root is None:
        raise RuntimeError(
            "get_assets_root_path() returned None — "
            "Nucleus server may be unreachable. "
            "Check Nucleus is running in the Omniverse Launcher."
        )
    return root


# ── Scene management ────────────────────────────────────────────────────────

def clear_world(stage):
    """Delete /World and everything under it."""
    import omni.kit.commands
    omni.kit.commands.execute("DeletePrimsCommand", paths=["/World"])


def delete_prim(stage, prim_path: str) -> bool:
    """Delete a prim and all its children from the stage.

    Returns True if the prim existed and was deleted, False if it was not found.
    """
    import omni.kit.commands
    xf = UsdGeom.Xformable.Get(stage, prim_path)
    if xf and xf.GetPrim().IsValid():
        omni.kit.commands.execute("DeletePrimsCommand", paths=[prim_path])
        return True
    return False


def create_physics_scene(stage, path="/World/PhysicsScene"):
    """Define a gravity-enabled physics scene."""
    ps = UsdPhysics.Scene.Define(stage, path)
    ps.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
    ps.CreateGravityMagnitudeAttr(9.81)
    # Update SimulationManager's cached physics scene reference so that
    # play_timeline() does not raise "Accessed schema on invalid prim"
    # after a world rebuild cleared the previous /World/PhysicsScene prim.
    try:
        from isaacsim.core.simulation_manager import SimulationManager
        SimulationManager._physics_scene_api = ps
    except Exception:
        pass
    return ps


# ── Asset spawning ──────────────────────────────────────────────────────────

def spawn_asset(stage, prim_path, asset_path, x, y, z=0.0, yaw_deg=0.0, scale=None):
    """Create an Xform at (x, y, z) rotated by yaw_deg and load a USD reference.

    scale: uniform scale factor applied after translate/rotate.  Use 0.01 for
    assets authored in centimetres (e.g. Omniverse DigitalTwin pallets) so they
    render at the correct size in a metres-based stage.
    """
    xform = UsdGeom.Xform.Define(stage, prim_path)
    xform.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
    xform.AddRotateZOp().Set(yaw_deg)
    if scale is not None:
        xform.AddScaleOp().Set(Gf.Vec3d(scale, scale, scale))
    # Use the prim obtained directly from Define — avoids GetPrimAtPath entirely.
    xform.GetPrim().GetReferences().AddReference(asset_path)
    return xform


# ── Prim transform helpers ──────────────────────────────────────────────────

def set_prim_translate_xy(stage, prim_path, x, y):
    """Set XY of an existing prim's translate op, preserving Z."""
    xf = UsdGeom.Xformable.Get(stage, prim_path)
    if not xf:
        return
    for op in xf.GetOrderedXformOps():
        if "translate" in op.GetOpName():
            cur = op.Get()
            op.Set(Gf.Vec3d(x, y, cur[2]))
            return


def set_prim_rotate_z(stage, prim_path, yaw_deg):
    """Set the rotateZ op on an existing prim."""
    xf = UsdGeom.Xformable.Get(stage, prim_path)
    if not xf:
        return
    for op in xf.GetOrderedXformOps():
        if "rotateZ" in op.GetOpName():
            op.Set(yaw_deg)
            return


def update_prim_pose(stage, prim_path, x, y, yaw_deg):
    """Set both translate XY and rotateZ in one call."""
    xf = UsdGeom.Xformable.Get(stage, prim_path)
    if not xf:
        return
    for op in xf.GetOrderedXformOps():
        name = op.GetOpName()
        if "translate" in name:
            cur = op.Get()
            op.Set(Gf.Vec3d(x, y, cur[2]))
        elif "rotateZ" in name:
            op.Set(yaw_deg)


# ── Bounding-box helpers ───────────────────────────────────────────────────

def compute_world_bbox(stage, prim_path):
    """Return (min_xyz, max_xyz) as Gf.Vec3d, or None on failure."""
    xf = UsdGeom.Xformable.Get(stage, prim_path)
    if not xf:
        return None
    prim = xf.GetPrim()
    if not prim.IsValid():
        return None
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    try:
        rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        return rng.GetMin(), rng.GetMax()
    except Exception:
        return None


def iter_prim_descendants(stage, root_path):
    """Yield every descendant prim under root_path."""
    xf = UsdGeom.Xformable.Get(stage, root_path)
    if xf and xf.GetPrim().IsValid():
        yield from Usd.PrimRange(xf.GetPrim())


# ── Simulation control ──────────────────────────────────────────────────────

def subscribe_physics_step(callback):
    """Register a per-physics-step callback. Returns the subscription object."""
    import omni.physx
    return omni.physx.get_physx_interface().subscribe_physics_step_events(callback)


def play_timeline():
    """Start the simulation timeline."""
    import omni.timeline
    omni.timeline.get_timeline_interface().play()


def stop_timeline():
    """Stop the simulation timeline."""
    import omni.timeline
    omni.timeline.get_timeline_interface().stop()


# ── Visual markers ──────────────────────────────────────────────────────────

def spawn_box_marker(stage, prim_path, cx, cy, cz, sx, sy, sz, color):
    """Create a colored cube marker (no physics)."""
    cube = UsdGeom.Cube.Define(stage, prim_path)
    cube.AddTranslateOp().Set(Gf.Vec3d(cx, cy, cz))
    cube.AddScaleOp().Set(Gf.Vec3d(sx, sy, sz))
    cube.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    return cube


def apply_static_collision(stage, prim_path):
    """Apply UsdPhysics.CollisionAPI to make a prim a static collider."""
    xf = UsdGeom.Xformable.Get(stage, prim_path)
    if xf and xf.GetPrim().IsValid():
        UsdPhysics.CollisionAPI.Apply(xf.GetPrim())


def make_invisible(stage, prim_path):
    """Hide a prim via UsdGeom.Imageable."""
    img = UsdGeom.Imageable.Get(stage, prim_path)
    if img:
        img.MakeInvisible()


def make_visible(stage, prim_path):
    """Show a previously hidden prim via UsdGeom.Imageable."""
    img = UsdGeom.Imageable.Get(stage, prim_path)
    if img:
        img.MakeVisible()


# ── Shelf detection (USD scan) ─────────────────────────────────────────────

def scan_shelves_for_rects(stage, keywords, min_size=0.5, dedup_threshold=0.5,
                            warehouse_path="/World/Warehouse"):
    """Scan the warehouse USD for shelf-like prims and return axis-aligned rects.

    Returns list of (x_min, x_max, y_min, y_max) tuples.
    Falls back to large-structure detection if no keyword matches are found.
    """
    rects: list[tuple[float, float, float, float]] = []
    wh_img = UsdGeom.Imageable.Get(stage, warehouse_path)
    if not wh_img or not wh_img.GetPrim().IsValid():
        return rects
    wh = wh_img.GetPrim()

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    seen: list[tuple[float, float]] = []

    # Primary pass: keyword match on prim name
    for prim in Usd.PrimRange(wh):
        if not any(k in prim.GetName().lower() for k in keywords):
            continue
        if not prim.IsA(UsdGeom.Xformable):
            continue
        try:
            rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            mn, mx = rng.GetMin(), rng.GetMax()
            w, d, h = mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]
            if w < min_size or d < min_size or h < min_size:
                continue
            cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
            if any(abs(cx - s[0]) < dedup_threshold and
                   abs(cy - s[1]) < dedup_threshold for s in seen):
                continue
            seen.append((cx, cy))
            rects.append((mn[0], mx[0], mn[1], mx[1]))
        except Exception:
            pass

    # Fallback: detect large structures if no keywords matched
    if not rects:
        for prim in Usd.PrimRange(wh):
            if not prim.IsA(UsdGeom.Xformable):
                continue
            try:
                rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                mn, mx = rng.GetMin(), rng.GetMax()
                w, d, h = mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]
                if w > 4.0 and d > 0.8 and h > 1.5:
                    cx = (mn[0] + mx[0]) / 2
                    cy = (mn[1] + mx[1]) / 2
                    if any(abs(cx - s[0]) < 1.0 and
                           abs(cy - s[1]) < 1.0 for s in seen):
                        continue
                    seen.append((cx, cy))
                    rects.append((mn[0], mx[0], mn[1], mx[1]))
            except Exception:
                pass

    return rects


# ── Loading dock gates ──────────────────────────────────────────────────────

def spawn_gate(stage, idx, door_cx, C):
    """Spawn one loading dock gate from cube primitives.

    Matches the reference: frame (posts, drum, guides), shutter panels,
    floor seal, wall hole with jambs/lintel, and a truck-back panel.
    """
    gate_y = C.WALL_Y_MIN + C.GATE_D / 2

    # Frame
    frame = f"/World/DockingDoors/gate_{idx}/frame"
    UsdGeom.Xform.Define(stage, frame)
    for side, sign in (("post_left", -1), ("post_right", +1)):
        px = door_cx + sign * (C.GATE_W / 2 - C.POST_W / 2)
        p = UsdGeom.Cube.Define(stage, f"{frame}/{side}")
        p.AddTranslateOp().Set(Gf.Vec3d(px, gate_y, C.GATE_TOTAL_H / 2))
        p.AddScaleOp().Set(Gf.Vec3d(C.POST_W / 2, C.GATE_D / 2, C.GATE_TOTAL_H / 2))
        p.GetDisplayColorAttr().Set(C.STEEL_COL)

    drum = UsdGeom.Cube.Define(stage, f"{frame}/drum_housing")
    drum.AddTranslateOp().Set(Gf.Vec3d(door_cx, gate_y, C.GATE_TOTAL_H - C.DRUM_H / 2))
    drum.AddScaleOp().Set(Gf.Vec3d(C.OPENING_W / 2, C.GATE_D / 2, C.DRUM_H / 2))
    drum.GetDisplayColorAttr().Set(C.STEEL_COL)

    for side, sign in (("guide_left", -1), ("guide_right", +1)):
        gx = door_cx + sign * (C.OPENING_W / 2 + C.GUIDE_W / 2)
        g = UsdGeom.Cube.Define(stage, f"{frame}/{side}")
        g.AddTranslateOp().Set(Gf.Vec3d(gx, gate_y, C.OPENING_H / 2))
        g.AddScaleOp().Set(Gf.Vec3d(C.GUIDE_W / 2, C.GATE_D / 2 + 0.01, C.OPENING_H / 2))
        g.GetDisplayColorAttr().Set(C.STEEL_COL)

    # Shutter panels
    shutter = f"/World/DockingDoors/gate_{idx}/shutter"
    UsdGeom.Xform.Define(stage, shutter)
    for pi in range(C.PANEL_N):
        pz = pi * C.PANEL_H + C.PANEL_H / 2
        panel = UsdGeom.Cube.Define(stage, f"{shutter}/panel_{pi}")
        panel.AddTranslateOp().Set(Gf.Vec3d(door_cx, gate_y, pz))
        panel.AddScaleOp().Set(Gf.Vec3d(C.OPENING_W / 2, C.GATE_D / 2,
                                         C.PANEL_H / 2 - C.PANEL_GAP))
        panel.GetDisplayColorAttr().Set(C.SHUTTER_COL)

    seal = UsdGeom.Cube.Define(stage, f"{shutter}/floor_seal")
    seal.AddTranslateOp().Set(Gf.Vec3d(door_cx, gate_y, C.SEAL_H / 2))
    seal.AddScaleOp().Set(Gf.Vec3d(C.OPENING_W / 2, C.GATE_D / 2, C.SEAL_H / 2))
    seal.GetDisplayColorAttr().Set(C.SEAL_COL)

    # Shutter-open black patch (hidden by default)
    open_y = gate_y + C.GATE_D / 2 + 0.01
    op = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/shutter_open")
    op.AddTranslateOp().Set(Gf.Vec3d(door_cx, open_y, C.OPENING_H / 2))
    op.AddScaleOp().Set(Gf.Vec3d(C.OPENING_W / 2, 0.01, C.OPENING_H / 2))
    op.GetDisplayColorAttr().Set([(0.0, 0.0, 0.0)])
    UsdGeom.Imageable(op).MakeInvisible()

    # Wall hole
    hole_cy = C.WALL_Y_MIN - C.HOLE_DEPTH / 2
    hole = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/hole")
    hole.AddTranslateOp().Set(Gf.Vec3d(door_cx, hole_cy, C.HOLE_H / 2))
    hole.AddScaleOp().Set(Gf.Vec3d(C.HOLE_W / 2, C.HOLE_DEPTH / 2, C.HOLE_H / 2))
    hole.GetDisplayColorAttr().Set(C.HOLE_COLOR)

    # Truck back
    tb_y = C.WALL_Y_MIN - 0.02
    tb = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/truck_back")
    tb.AddTranslateOp().Set(Gf.Vec3d(door_cx, tb_y, C.OPENING_H / 2))
    tb.AddScaleOp().Set(Gf.Vec3d(C.OPENING_W / 2, 0.01, C.OPENING_H / 2))
    tb.GetDisplayColorAttr().Set([(0.0, 0.0, 0.0)])

    # Jambs and lintel
    jamb_cy = C.WALL_Y_MIN - C.WALL_T / 2
    for side, sign in (("left", -1), ("right", +1)):
        j = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/jamb_{side}")
        j.AddTranslateOp().Set(Gf.Vec3d(
            door_cx + sign * (C.HOLE_W / 2 + C.WALL_T / 2), jamb_cy, C.HOLE_H / 2))
        j.AddScaleOp().Set(Gf.Vec3d(C.WALL_T / 2, C.WALL_T / 2, C.HOLE_H / 2))
        j.GetDisplayColorAttr().Set(C.WALL_COLOR)

    lintel = UsdGeom.Cube.Define(stage, f"/World/DockingDoors/gate_{idx}/lintel")
    lintel.AddTranslateOp().Set(Gf.Vec3d(door_cx, jamb_cy, C.HOLE_H + C.WALL_T / 2))
    lintel.AddScaleOp().Set(Gf.Vec3d((C.HOLE_W + 2 * C.WALL_T) / 2,
                                      C.WALL_T / 2, C.WALL_T / 2))
    lintel.GetDisplayColorAttr().Set(C.WALL_COLOR)


def open_gate(stage, idx, panel_n):
    """Visually open a dock gate: hide shutter panels + floor seal, show truck-back.

    panel_n: number of shutter panels (C.PANEL_N).
    """
    shutter = f"/World/DockingDoors/gate_{idx}/shutter"
    for pi in range(panel_n):
        make_invisible(stage, f"{shutter}/panel_{pi}")
    make_invisible(stage, f"{shutter}/floor_seal")
    make_visible(stage, f"/World/DockingDoors/gate_{idx}/shutter_open")


def close_gate(stage, idx, panel_n):
    """Visually close a dock gate: show shutter panels + floor seal, hide truck-back."""
    shutter = f"/World/DockingDoors/gate_{idx}/shutter"
    for pi in range(panel_n):
        make_visible(stage, f"{shutter}/panel_{pi}")
    make_visible(stage, f"{shutter}/floor_seal")
    make_invisible(stage, f"/World/DockingDoors/gate_{idx}/shutter_open")


async def _sleep_app(seconds: float):
    """Yield app updates for ~seconds so the viewport refreshes in between."""
    import omni.kit.app
    app = omni.kit.app.get_app()
    # ~60 Hz driven by app updates; avoids wall-clock drift in Script Editor.
    steps = max(1, int(seconds * 60))
    for _ in range(steps):
        await app.next_update_async()


async def open_gate_animated(stage, idx, panel_n, duration=1.2):
    """Roll-up open: reveal truck-back, then hide panels bottom → top, then floor seal.

    `duration` is total animation length in seconds. State on entry doesn't
    matter — function always ends in the fully-open state.
    """
    shutter = f"/World/DockingDoors/gate_{idx}/shutter"
    # Truck-back becomes visible immediately so it's seen through panels as they clear.
    make_visible(stage, f"/World/DockingDoors/gate_{idx}/shutter_open")
    # Floor seal lifts first (bottom of the roll).
    make_invisible(stage, f"{shutter}/floor_seal")

    # Divide remaining duration across the N panels.
    per_step = max(0.02, duration / max(1, panel_n))
    for pi in range(panel_n):  # bottom → top
        make_invisible(stage, f"{shutter}/panel_{pi}")
        await _sleep_app(per_step)


async def close_gate_animated(stage, idx, panel_n, duration=1.2):
    """Roll-down close: show panels top → bottom, then floor seal, then hide truck-back."""
    shutter = f"/World/DockingDoors/gate_{idx}/shutter"

    per_step = max(0.02, duration / max(1, panel_n))
    for pi in range(panel_n - 1, -1, -1):  # top → bottom
        make_visible(stage, f"{shutter}/panel_{pi}")
        await _sleep_app(per_step)

    # Floor seal drops into place, then truck-back hides.
    make_visible(stage, f"{shutter}/floor_seal")
    make_invisible(stage, f"/World/DockingDoors/gate_{idx}/shutter_open")


# ── Zebra tape floor markings ──────────────────────────────────────────────

def spawn_zebra_edge(stage, prim_base, is_horiz, ex, ey, edge_len, C):
    """One edge: black base strip + yellow 45-deg stripes."""
    th = C.TAPE_THICK / 2.0
    tw = C.TAPE_WIDTH / 2.0
    z0 = C.TAPE_THICK / 2.0
    z1 = C.TAPE_THICK + th

    sx, sy = (edge_len / 2.0, tw) if is_horiz else (tw, edge_len / 2.0)
    base = UsdGeom.Cube.Define(stage, f"{prim_base}_base")
    base.AddTranslateOp().Set(Gf.Vec3d(ex, ey, z0))
    base.AddScaleOp().Set(Gf.Vec3d(sx, sy, th))
    base.GetDisplayColorAttr().Set(C.BLACK)

    diag = C.TAPE_WIDTH * 1.5
    n = int(edge_len / C.STRIPE_SPACE) + 1
    for i in range(n):
        t = -edge_len / 2.0 + i * C.STRIPE_SPACE
        bx = ex + t if is_horiz else ex
        by = ey     if is_horiz else ey + t
        s = UsdGeom.Cube.Define(stage, f"{prim_base}_s{i}")
        s.AddTranslateOp().Set(Gf.Vec3d(bx, by, z1))
        s.AddRotateZOp().Set(45.0)
        s.AddScaleOp().Set(Gf.Vec3d(diag / 2.0, C.STRIPE_THICK / 2.0, th))
        s.GetDisplayColorAttr().Set(C.YELLOW)


def spawn_zebra_rect(stage, prim_base, rect_cx, rect_cy, rect_w, rect_d, C):
    """Spawn zebra-striped tape border around a rectangular floor zone."""
    hw, hd = rect_w / 2.0, rect_d / 2.0
    for label, is_h, ex, ey, elen in [
        ("south", True,  rect_cx,      rect_cy - hd, rect_w),
        ("north", True,  rect_cx,      rect_cy + hd, rect_w),
        ("west",  False, rect_cx - hw, rect_cy,      rect_d),
        ("east",  False, rect_cx + hw, rect_cy,      rect_d),
    ]:
        spawn_zebra_edge(stage, f"{prim_base}/{label}", is_h, ex, ey, elen, C)
