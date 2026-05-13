"""
Isaac Sim API isolation layer.

Every call into omni.* / pxr.* lives here so the rest of the codebase
stays testable and version-change impact is contained.
"""

from __future__ import annotations
import math
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
    # Re-register the new scene with SimulationManager so that play_timeline()
    # does not raise "Accessed schema on invalid prim" after a world rebuild
    # cleared the previous /World/PhysicsScene prim.
    # SimulationManager._physics_scene_apis is an OrderedDict:
    #   { prim_path: PhysxSchema.PhysxSceneAPI }
    try:
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import PhysxSchema
        SimulationManager._physics_scene_apis.clear()
        SimulationManager._physics_scene_apis[path] = \
            PhysxSchema.PhysxSceneAPI.Apply(ps.GetPrim())
        SimulationManager._default_physics_scene_idx = 0
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


async def wait_for_assets_loaded(timeout: float = 90.0) -> None:
    """Block until the next ASSETS_LOADED stage event fires.

    Subscribe BEFORE spawning the asset so there is no race condition.
    The event fires once the USD stage finishes resolving the reference.
    """
    import asyncio
    import omni.usd
    done = asyncio.Event()

    def _on_event(event):
        if event.type == int(omni.usd.StageEventType.ASSETS_LOADED):
            done.set()

    handle = omni.usd.get_context().get_stage_event_stream() \
        .create_subscription_to_pop(_on_event, name="ih_wait_assets_loaded")
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[ih] WARNING: wait_for_assets_loaded timed out after {timeout}s")
    finally:
        handle = None   # release subscription


# ── IRA pedestrian helpers ──────────────────────────────────────────────────

def generate_ira_command_file(pedestrians, output_path: str) -> None:
    """Write an omni.anim.people command file from pedestrian waypoint lists.

    Each pedestrian's waypoints become sequential GoTo + Idle commands.
    Character naming follows IRA convention: index 0 → "Character",
    index 1 → "Character_01", etc.
    """
    lines = []
    for ped in pedestrians:
        prefix = ped.character_name
        for (wx, wy) in ped.waypoints:
            lines.append(f"{prefix} GoTo {wx:.2f} {wy:.2f} 0.0 _")
            lines.append(f"{prefix} Idle 1.5")
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[ih] Command file written: {output_path} ({len(lines)} lines, "
          f"{len(pedestrians)} pedestrian(s))")


async def setup_ira_pedestrians(biped_usd: str, character_usd: str,
                                command_file_path: str, count: int) -> None:
    """Spawn and wire IRA-animated characters on the already-loaded stage.

    Bakes the navmesh, spawns `count` character USDs at staggered positions
    on the open warehouse floor, then attaches the animation graph and
    CharacterBehavior script so omni.anim.people can drive movement.

    Must be called after the warehouse scene is fully loaded.
    """
    import asyncio
    import carb.settings
    import omni.anim.navigation.core as nav
    from isaacsim.replicator.agent.core.stage_util import CharacterUtil
    from isaacsim.replicator.agent.core.settings import BehaviorScriptPaths
    from omni.anim.people.scripts.custom_command.populate_anim_graph import (
        populate_anim_graph,
    )

    s = carb.settings.get_settings()
    s.set("/exts/isaacsim.replicator.agent/asset_settings/default_biped_assets_path",
          biped_usd)
    s.set("/exts/omni.anim.people/command_settings/command_file_path",
          command_file_path)
    s.set("/exts/omni.anim.people/command_settings/number_of_loop", "inf")
    s.set("/exts/omni.anim.people/navigation_settings/navmesh_enabled", True)

    # Load the invisible biped skeleton then re-run populate_anim_graph so the
    # AnimationGraph is guaranteed present before characters are wired.
    CharacterUtil.load_default_biped_to_stage()
    await next_update()
    populate_anim_graph()

    # Navmesh bake — the warehouse floor must be loaded before this runs.
    # Caller is responsible for waiting for ASSETS_LOADED (via
    # ih.wait_for_assets_loaded()) before calling this function.
    _inav = nav.acquire_interface()
    _inav.start_navmesh_baking_and_wait()
    if _inav.get_navmesh() is None:
        # NavMesh baking fails when the warehouse is loaded as a USD reference
        # sub-prim (no NavMeshVolume present).  Fall back to straight-line GoTo
        # so characters still walk their patrol routes without obstacle avoidance.
        print("[ih] NavMesh baking failed — falling back to direct-path navigation "
              "(navmesh_enabled=False). Characters will walk straight-line routes.")
        s.set("/exts/omni.anim.people/navigation_settings/navmesh_enabled", False)
    else:
        print("[ih] NavMesh baked successfully.")

    # Spawn each character, then wait for their USD references to resolve so
    # SkelRoot prims exist when get_characters_in_stage() is called.
    _spawn_xs = [-5.0, -12.0, -19.0, -3.0]
    for i in range(count):
        char_name = CharacterUtil.get_character_name_by_index(i)
        sx = _spawn_xs[i % len(_spawn_xs)]
        CharacterUtil.load_character_usd_to_stage(
            character_usd, [sx, -10.0, 0.0], 0, char_name
        )

    await asyncio.sleep(2.0)  # let character USD references resolve

    # Wire animation graph + CharacterBehavior script to every character.
    biped_prim  = CharacterUtil.get_default_biped_character()
    char_list   = CharacterUtil.get_characters_in_stage()
    anim_graph  = CharacterUtil.get_anim_graph_from_character(biped_prim)
    if anim_graph is None:
        print("[ih] WARNING: AnimationGraph not found — characters will not animate.")
    CharacterUtil.setup_animation_graph_to_character(char_list, anim_graph)
    CharacterUtil.setup_python_scripts_to_character(
        char_list, BehaviorScriptPaths.behavior_script_path()
    )
    print(f"[ih] IRA pedestrians ready: {count} character(s), "
          f"{len(char_list)} SkelRoot(s) wired.")


# ── Visual markers ──────────────────────────────────────────────────────────

def spawn_box_marker(stage, prim_path, cx, cy, cz, sx, sy, sz, color):
    """Create a colored cube marker (no physics)."""
    cube = UsdGeom.Cube.Define(stage, prim_path)
    cube.AddTranslateOp().Set(Gf.Vec3d(cx, cy, cz))
    cube.AddScaleOp().Set(Gf.Vec3d(sx, sy, sz))
    cube.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    return cube


def spawn_capsule_marker(stage, prim_path, x, y, height, radius, color):
    """Create a colored upright capsule marker (no physics, no external USD)."""
    cap = UsdGeom.Capsule.Define(stage, prim_path)
    cap.GetHeightAttr().Set(height)
    cap.GetRadiusAttr().Set(radius)
    cap.GetAxisAttr().Set("Z")
    cap.AddTranslateOp().Set(Gf.Vec3d(x, y, height / 2.0 + radius))
    cap.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    return cap


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


def spawn_door_label(stage, idx, door_cx, C, number=None):
    """Spawn yellow 7-segment digit(s) above loading dock gate idx.

    number: integer to display (e.g. 12, 4, 7).  Defaults to idx+1 when None.
    Supports 1- and 2-digit numbers.  Segments are cube prims under
    /World/DockLabels/label_{idx}, centred on door_cx at Z = GATE_TOTAL_H + 0.6 m.
    """
    display   = number if number is not None else idx + 1
    digits    = [int(d) for d in str(display)]   # e.g. 12 → [1, 2]

    gate_y  = C.WALL_Y_MIN + C.GATE_D / 2
    label_z = C.GATE_TOTAL_H + 0.6
    h_half  = 0.50
    w_half  = 0.30
    q_half  = 0.25
    seg_t   = 0.10
    depth   = 0.08
    # Horizontal distance between digit centres for 2-digit numbers
    digit_step = w_half * 2 + 0.12

    segs = {
        "top": ( 0,       +h_half, w_half,           seg_t / 2),
        "mid": ( 0,        0,      w_half,           seg_t / 2),
        "bot": ( 0,       -h_half, w_half,           seg_t / 2),
        "tl":  (-w_half,  +q_half, seg_t / 2, q_half - seg_t / 2),
        "tr":  (+w_half,  +q_half, seg_t / 2, q_half - seg_t / 2),
        "bl":  (-w_half,  -q_half, seg_t / 2, q_half - seg_t / 2),
        "br":  (+w_half,  -q_half, seg_t / 2, q_half - seg_t / 2),
    }
    patterns = {
        0: {"top", "tl", "tr", "bl", "br", "bot"},
        1: {"tr", "br"},
        2: {"top", "tr", "mid", "bl", "bot"},
        3: {"top", "tr", "mid", "br", "bot"},
        4: {"tl", "tr", "mid", "br"},
        5: {"top", "tl", "mid", "br", "bot"},
        6: {"top", "tl", "mid", "bl", "br", "bot"},
        7: {"top", "tr", "br"},
        8: {"top", "tl", "tr", "mid", "bl", "br", "bot"},
        9: {"top", "tl", "tr", "mid", "br", "bot"},
    }

    color = [(1.0, 0.85, 0.0)]  # yellow
    root  = f"/World/DockLabels/label_{idx}"
    UsdGeom.Xform.Define(stage, root)

    n = len(digits)
    # Centre the whole number: left edge of first digit at door_cx - total_w/2
    total_w = n * digit_step - (digit_step - w_half * 2)
    first_cx = door_cx - total_w / 2 + w_half

    for di, digit in enumerate(digits):
        digit_cx = first_cx + di * digit_step
        active = patterns.get(digit, set())
        for seg_name, (cx_off, cz_off, hsx, hsz) in segs.items():
            if seg_name not in active:
                continue
            p = UsdGeom.Cube.Define(stage, f"{root}/d{di}_{seg_name}")
            # Negate cx_off so digits read correctly from the north camera
            # (looking south: camera-right = west = -X).
            p.AddTranslateOp().Set(
                Gf.Vec3d(digit_cx - cx_off, gate_y, label_z + cz_off))
            p.AddScaleOp().Set(Gf.Vec3d(hsx, depth / 2, hsz))
            p.GetDisplayColorAttr().Set(color)


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


# ── Surveillance cameras ──────────────────────────────────────────────────────

def spawn_cameras_from_usd(stage, source_usd_path, parent_path="/World/Cameras"):
    """Read UsdGeom.Camera prims from *source_usd_path* and recreate them in *stage*.

    The source USD is opened as a temporary read-only stage.  Every Camera prim
    found anywhere in that stage is copied to ``parent_path/<cam_name>`` in the
    target stage, preserving the full transform op and all camera attributes
    (focalLength, horizontalAperture, verticalAperture, clippingRange).

    Returns a list of the destination prim paths created.
    """
    src = Usd.Stage.Open(source_usd_path)
    if not src:
        raise RuntimeError(
            f"spawn_cameras_from_usd: could not open '{source_usd_path}'"
        )

    # Ensure the /World/Cameras xform exists
    UsdGeom.Xform.Define(stage, parent_path)

    created = []
    for prim in Usd.PrimRange(src.GetPseudoRoot()):
        if not prim.IsA(UsdGeom.Camera):
            continue

        cam_name = prim.GetName()
        src_cam  = UsdGeom.Camera(prim)
        src_xf   = UsdGeom.Xformable(prim)
        dst_path = f"{parent_path}/{cam_name}"

        dst_cam = UsdGeom.Camera.Define(stage, dst_path)

        # Copy the first transform op (xformOp:transform or xformOp:translate)
        for op in src_xf.GetOrderedXformOps():
            op_name = op.GetOpName()
            val     = op.Get()
            if val is None:
                continue
            if "transform" in op_name:
                dst_cam.AddTransformOp().Set(val)
                break
            if "translate" in op_name:
                dst_cam.AddTranslateOp().Set(val)
                break

        # Copy camera attributes
        fl = src_cam.GetFocalLengthAttr().Get()
        ha = src_cam.GetHorizontalApertureAttr().Get()
        va = src_cam.GetVerticalApertureAttr().Get()
        cr = src_cam.GetClippingRangeAttr().Get()
        if fl is not None:
            dst_cam.CreateFocalLengthAttr(fl)
        if ha is not None:
            dst_cam.CreateHorizontalApertureAttr(ha)
        if va is not None:
            dst_cam.CreateVerticalApertureAttr(va)
        if cr is not None:
            dst_cam.CreateClippingRangeAttr(cr)

        created.append(dst_path)
        print(f"[spawn_cameras_from_usd] {cam_name} → {dst_path}")

    return created


def spawn_camera(stage, path, eye, target, fov_deg=70.0):
    """Create a USD perspective camera at *eye* aimed at *target*.

    eye, target: 3-tuples or Gf.Vec3d (world-space, metres, Z-up).
    fov_deg: horizontal field of view in degrees.

    The camera looks along its local -Z axis (USD/OpenGL convention).
    A look-at matrix is built from the eye→target direction using Z-up as
    the world up vector, with a Y-up fallback when the look direction is
    nearly parallel to Z.
    """
    eye    = Gf.Vec3d(*eye)
    target = Gf.Vec3d(*target)

    fwd = target - eye
    fwd_len = fwd.GetLength()
    if fwd_len < 1e-10:
        raise ValueError(f"spawn_camera: eye and target are the same point ({path})")
    fwd = fwd / fwd_len

    # Camera local axes (right=X, up=Y, look=-Z)
    world_up = Gf.Vec3d(0, 0, 1)
    right = Gf.Vec3d(
        fwd[1]*world_up[2] - fwd[2]*world_up[1],
        fwd[2]*world_up[0] - fwd[0]*world_up[2],
        fwd[0]*world_up[1] - fwd[1]*world_up[0],
    )
    right_len = right.GetLength()
    if right_len < 1e-6:
        # Camera is pointing nearly straight up or down — use Y as fallback up
        world_up = Gf.Vec3d(0, 1, 0)
        right = Gf.Vec3d(
            fwd[1]*world_up[2] - fwd[2]*world_up[1],
            fwd[2]*world_up[0] - fwd[0]*world_up[2],
            fwd[0]*world_up[1] - fwd[1]*world_up[0],
        )
        right_len = right.GetLength()
    right = right / right_len

    up = Gf.Vec3d(
        right[1]*fwd[2] - right[2]*fwd[1],
        right[2]*fwd[0] - right[0]*fwd[2],
        right[0]*fwd[1] - right[1]*fwd[0],
    )

    # Row-major 4×4 transform: rows = [right, up, -fwd, eye]
    mat = Gf.Matrix4d(
        (right[0],  right[1],  right[2],  0.0),
        (up[0],     up[1],     up[2],     0.0),
        (-fwd[0],  -fwd[1],   -fwd[2],    0.0),
        (eye[0],    eye[1],    eye[2],    1.0),
    )

    cam = UsdGeom.Camera.Define(stage, path)
    cam.AddTransformOp().Set(mat)

    # Focal length from horizontal FOV and standard 20.955 mm aperture
    aperture = 20.955
    focal_length = aperture / (2.0 * math.tan(math.radians(fov_deg / 2.0)))
    cam.CreateHorizontalApertureAttr(aperture)
    cam.CreateFocalLengthAttr(focal_length)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 100000.0))

    return cam


def set_active_camera(cam_prim_path: str) -> bool:
    """Set the active viewport camera to *cam_prim_path*.

    Returns True if the viewport was switched, False otherwise.
    """
    try:
        from omni.kit.viewport.utility import get_active_viewport
        vp = get_active_viewport()
        if vp is None:
            print(f"[ih] set_active_camera: no active viewport")
            return False
        vp.camera_path = cam_prim_path
        print(f"[ih] active camera → {cam_prim_path}")
        return True
    except Exception as e:
        print(f"[ih] set_active_camera failed: {e}")
        return False
