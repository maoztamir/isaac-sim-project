"""
Visual test: two IRA-animated pedestrians walking in the warehouse.

Uses SimulationManager (same mechanism as poc_person_actor/run.py) so the
warehouse opens as the root stage — navmesh baking then has a proper scene
context and GoTo commands work correctly.

Expected visual outcomes
------------------------
STEP 1: SimulationManager setup
  EXPECT: warehouse opens as root stage, navmesh bakes (brief console activity),
          then two male construction-worker figures appear on the open floor
  PASS IF: two human figures visible, no "invalid command" errors in console
  FAIL SIGN: timeout; "NavMesh baking failed"; orange capsules instead of people

STEP 2: Timeline play
  EXPECT: both characters begin walking their rectangular patrol routes and
          loop continuously — ped0 in the west half, ped1 in the east half
  PASS IF: figures visibly move, reach waypoints, turn, and repeat
  FAIL SIGN: figures stand still; "GoTo ... invalid command" in console
"""

import asyncio
import os

# ── Absolute paths (Script Editor __file__ is unreliable) ─────────────────────
_CHARACTERS_ROOT = (
    "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1/Isaac/People/Characters"
)
_BIPED_USD     = _CHARACTERS_ROOT + "/Biped_Setup.usd"
_WAREHOUSE_USD = (
    "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1/Isaac"
    "/Environments/Simple_Warehouse/full_warehouse.usd"
)

CONFIG_PATH = "/tmp/test_pedestrian_ira_config.yaml"
CMD_PATH    = "/tmp/test_pedestrian_ira_commands.txt"

SETUP_TIMEOUT_S = 180.0

# ── Patrol waypoints (x, y in warehouse metres) ───────────────────────────────
WAYPOINTS_0 = [          # ped0: west half of open floor
    ( -5.0, -10.0),
    ( -5.0,   3.0),
    (-12.0,   3.0),
    (-12.0, -10.0),
]
WAYPOINTS_1 = [          # ped1: east half of open floor
    (-14.0, -10.0),
    (-14.0,   3.0),
    (-22.0,   3.0),
    (-22.0, -10.0),
]


# ── File generators ───────────────────────────────────────────────────────────

def _write_config() -> None:
    yaml_text = (
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
        fh.write(yaml_text)


def _write_commands() -> None:
    lines = []
    for wx, wy in WAYPOINTS_0:
        lines.append(f"Character GoTo {wx:.2f} {wy:.2f} 0.0 _")
        lines.append("Character Idle 1.5")
    for wx, wy in WAYPOINTS_1:
        lines.append(f"Character_01 GoTo {wx:.2f} {wy:.2f} 0.0 _")
        lines.append("Character_01 Idle 1.5")
    with open(CMD_PATH, "w") as fh:
        fh.write("\n".join(lines) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

async def _run():
    import carb.settings
    import omni.timeline
    from isaacsim.replicator.agent.core.simulation import SimulationManager

    _write_config()
    _write_commands()
    print(f"[test] config  : {CONFIG_PATH}")
    print(f"[test] commands: {CMD_PATH}")

    settings = carb.settings.get_settings()

    # Must be set before load_config_file() so IRA can find the AnimationGraph.
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
        print("[test] ERROR: config file failed to load — check CONFIG_PATH")
        return

    # Opens scene as root stage → navmesh bakes → spawns N characters.
    sim.set_up_simulation_from_config_file()
    print("[test] Waiting for navmesh bake and character spawn …")

    try:
        await asyncio.wait_for(setup_done.wait(), timeout=SETUP_TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"[test] ERROR: timed out after {SETUP_TIMEOUT_S}s — "
              "check Isaac Sim console for navmesh or asset errors")
        return
    finally:
        _handle = None

    print("[test] STEP 1 done — 2 IRA pedestrians spawned")

    # STEP 2 — play
    omni.timeline.get_timeline_interface().play()
    print("[test] STEP 2 done — timeline playing; characters should walk patrol routes")


asyncio.ensure_future(_run())
