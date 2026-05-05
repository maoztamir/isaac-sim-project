"""
Visual test: 2 IRA-animated pedestrians + 2 kinematic forklifts sharing the
warehouse floor.

Architecture
------------
IRA path (proven):   SimulationManager → opens warehouse as ROOT stage →
                     navmesh bakes → 2 pedestrians spawned + wired.

Forklift path:       After setup_done, spawn 2 forklift USD prims into the
                     live stage, then drive them with Forklift.update() on
                     every physics step (same kinematic bicycle model used by
                     the full scenario framework).

Expected visual outcomes
------------------------
STEP 1: SimulationManager setup (~30-60 s)
  EXPECT: warehouse opens as root stage, navmesh bakes, two male construction-
          worker figures appear on the open floor
  PASS IF: two human figures visible; console prints "STEP 1 done"
  FAIL SIGN: timeout; orange capsules instead of people; "NavMesh baking failed"

STEP 2: Forklift spawn
  EXPECT: two yellow forklift models appear — one on the east side of the open
          floor (~X=-4), one on the west side (~X=-17)
  PASS IF: two forklift prims visible in viewport; console prints "STEP 2 done"
  FAIL SIGN: blank spot where forklifts should be; USD load error in console

STEP 3: Simulation running
  EXPECT: forklifts drive their respective rectangular patrol routes (looping
          continuously); pedestrians walk their rectangular patrol routes;
          all four actors co-exist on the floor simultaneously
  PASS IF: forklift console readout every 5 s shows changing X/Y coordinates
           and non-zero speed; character figures visibly move in viewport
  FAIL SIGN: forklifts pinned at spawn; "GoTo invalid command" for pedestrians
"""

import sys
import os

# ── Module hot-reload (for warehouse_sim imports) ─────────────────────────────
_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"
_bad_paths = []
for p in list(sys.path):
    try:
        if p and p != _project_root and os.path.isdir(os.path.join(p, "warehouse_sim")):
            _bad_paths.append(p)
    except Exception:
        pass
for p in _bad_paths:
    while p in sys.path:
        sys.path.remove(p)
if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

_to_remove = [k for k in sys.modules if k.startswith("warehouse_sim")]
for k in _to_remove:
    del sys.modules[k]

for k in list(sys.modules):
    if k.startswith("warehouse_sim") and sys.modules.get(k) is None:
        sys.modules.pop(k, None)

import glob as _glob
for _pyc in _glob.glob(
        os.path.join(_project_root, "warehouse_sim", "**", "*.pyc"),
        recursive=True):
    try:
        os.remove(_pyc)
    except OSError:
        pass

import importlib
importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")

# ── Framework imports ─────────────────────────────────────────────────────────
import asyncio
from warehouse_sim.models.forklift import Forklift
from warehouse_sim.shelves import ShelfMap
from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih

# ── Absolute asset paths ──────────────────────────────────────────────────────
_CHARACTERS_ROOT = (
    "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1/Isaac/People/Characters"
)
_BIPED_USD     = _CHARACTERS_ROOT + "/Biped_Setup.usd"
_WAREHOUSE_USD = (
    "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1/Isaac"
    "/Environments/Simple_Warehouse/full_warehouse.usd"
)

CONFIG_PATH     = "/tmp/test_fl_ped_config.yaml"
CMD_PATH        = "/tmp/test_fl_ped_commands.txt"
SETUP_TIMEOUT_S = 180.0

# ── Pedestrian patrol waypoints (x, y metres) ─────────────────────────────────
WAYPOINTS_PED0 = [          # east half of open floor
    ( -4.0, -12.0),
    ( -4.0,   4.0),
    ( -9.0,   4.0),
    ( -9.0, -12.0),
]
WAYPOINTS_PED1 = [          # west half of open floor
    (-16.0, -12.0),
    (-16.0,   4.0),
    (-22.0,   4.0),
    (-22.0, -12.0),
]

# ── Forklift routes: (spawn_x, spawn_y, spawn_heading, [patrol waypoints]) ───
# Headings: 180 = north (+Y), 0 = south (-Y), 90 = east (+X), 270 = west (-X)
FL_ROUTES = [
    # FL0: east-side rectangle, starts at south end, heads north
    (-4.0, -14.0, 180.0, [(-4.0, -14.0), (-4.0, 5.0), (-9.0, 5.0), (-9.0, -14.0)]),
    # FL1: west-side rectangle, starts at north end, heads south (opposite phase)
    (-17.0, 5.0, 0.0,   [(-17.0, 5.0), (-17.0, -14.0), (-22.0, -14.0), (-22.0, 5.0)]),
]

# ── Simulation state ──────────────────────────────────────────────────────────
_forklifts:  list[Forklift] = []
_fl_routes:  list[list]     = []   # stored for loop re-issue
_shelf_map:  ShelfMap | None = None
_phys_sub                   = None
_sim_time:   float          = 0.0
_last_print: float          = -6.0  # force first print immediately


# ── Config / command file generators ─────────────────────────────────────────

def _write_config() -> None:
    text = (
        "isaacsim.replicator.agent:\n"
        "  version: 0.7.0\n"
        "  global:\n"
        "    seed: 42\n"
        "    simulation_length: 9000\n"
        "  scene:\n"
        f"    asset_path: {_WAREHOUSE_USD}\n"
        "  character:\n"
        f"    asset_path: {_CHARACTERS_ROOT}\n"
        f"    command_file: {CMD_PATH}\n"
        "    filters: []\n"
        "    num: 2\n"
        "    spawn_area: []\n"
        "    navigation_area: []\n"
    )
    with open(CONFIG_PATH, "w") as fh:
        fh.write(text)


def _write_commands() -> None:
    lines = []
    for wx, wy in WAYPOINTS_PED0:
        lines.append(f"Character GoTo {wx:.2f} {wy:.2f} 0.0 _")
        lines.append("Character Idle 1.5")
    for wx, wy in WAYPOINTS_PED1:
        lines.append(f"Character_01 GoTo {wx:.2f} {wy:.2f} 0.0 _")
        lines.append("Character_01 Idle 1.5")
    with open(CMD_PATH, "w") as fh:
        fh.write("\n".join(lines) + "\n")


# ── Physics step callback ─────────────────────────────────────────────────────

def _on_step(dt: float) -> None:
    global _sim_time, _last_print
    _sim_time += dt
    stage = ih.get_stage()

    for fl, wps in zip(_forklifts, _fl_routes):
        if not fl.waypoints:
            fl.set_waypoints(wps)
            fl.state = C.STATE_RETURNING
        fl.update(dt, stage, _shelf_map, _forklifts)

    if _sim_time - _last_print >= 5.0:
        _last_print = _sim_time
        for fl in _forklifts:
            print(f"[test] t={_sim_time:.1f}s  "
                  f"FL{fl.id}=({fl.pos[0]:.1f},{fl.pos[1]:.1f}) "
                  f"spd={fl.speed:.2f}  state={fl.state}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def _run() -> None:
    global _forklifts, _fl_routes, _shelf_map, _phys_sub

    import carb.settings
    import omni.timeline
    from isaacsim.replicator.agent.core.simulation import SimulationManager

    _write_config()
    _write_commands()
    print(f"[test] config  : {CONFIG_PATH}")
    print(f"[test] commands: {CMD_PATH}")

    settings = carb.settings.get_settings()
    settings.set(
        "/exts/isaacsim.replicator.agent/asset_settings/default_biped_assets_path",
        _BIPED_USD,
    )
    settings.set("/exts/omni.anim.people/command_settings/number_of_loop", "inf")
    settings.set("/exts/omni.anim.people/navigation_settings/navmesh_enabled", True)

    sim = SimulationManager()
    setup_done = asyncio.Event()

    def _on_setup_done(event):
        setup_done.set()

    _handle = sim.register_set_up_simulation_done_callback(_on_setup_done)

    ok = sim.load_config_file(CONFIG_PATH)
    if not ok:
        print("[test] ERROR: config file failed to load")
        return

    sim.set_up_simulation_from_config_file()
    print("[test] Waiting for IRA setup (navmesh bake + pedestrian spawn) …")

    try:
        await asyncio.wait_for(setup_done.wait(), timeout=SETUP_TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"[test] ERROR: timed out after {SETUP_TIMEOUT_S}s — "
              "check console for navmesh or asset errors")
        return
    finally:
        _handle = None

    print("[test] STEP 1 done — 2 IRA pedestrians spawned and ready")

    # ── STEP 2: spawn forklifts into the live stage ───────────────────────────
    stage       = ih.get_stage()
    assets_root = ih.get_assets_root()
    _shelf_map  = ShelfMap()   # empty — open-floor patrol, no shelf avoidance needed

    for i, (sx, sy, hdg, wps) in enumerate(FL_ROUTES):
        path = f"/World/Forklifts/forklift_{i}"
        ih.spawn_asset(stage, path, assets_root + C.FORKLIFT_USD,
                       sx, sy, 0.0, hdg)
        fl = Forklift(i, path, sx, sy, heading=hdg)
        fl.set_waypoints(wps)
        fl.state = C.STATE_RETURNING
        _forklifts.append(fl)
        _fl_routes.append(wps)

    await ih.next_update()   # let forklift USD references resolve
    print("[test] STEP 2 done — 2 forklifts spawned")

    # ── STEP 3: subscribe and play ────────────────────────────────────────────
    _phys_sub = ih.subscribe_physics_step(_on_step)
    ih.play_timeline()
    print("[test] STEP 3 done — timeline playing; all 4 actors active")


asyncio.ensure_future(_run())
