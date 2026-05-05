"""
POC: one animated person walking in the warehouse using IRA.

Run from Isaac Sim Script Editor:
  1. Window > Script Editor
  2. Open this file (or paste its contents)
  3. Ctrl+Enter

What happens:
  - IRA loads full_warehouse.usd and bakes its navmesh
  - One character asset is spawned at a random navmesh position
  - The character's animation graph and CharacterBehavior script are wired up
  - commands.txt drives the character on a rectangular patrol loop forever
  - Timeline plays automatically once setup is complete
"""

import asyncio

# ── Paths (absolute — __file__ is unreliable in Script Editor's temp dir) ─────
_CHARACTERS_ROOT = (
    "/home/ubuntu/isaacsim_assets/Assets/Isaac/5.1/Isaac/People/Characters"
)
_BIPED_USD = _CHARACTERS_ROOT + "/Biped_Setup.usd"

CONFIG_PATH = (
    "/home/ubuntu/isaac_sim_samples/isaac-sim-project/poc_person_actor/config.yaml"
)

# Seconds to wait for navmesh baking + asset spawn before giving up.
SETUP_TIMEOUT_S = 180.0


# ── Main ──────────────────────────────────────────────────────────────────────

async def _run():
    import carb
    import carb.settings
    import omni.timeline

    from isaacsim.replicator.agent.core.simulation import SimulationManager

    print(f"[poc] config: {CONFIG_PATH}")

    settings = carb.settings.get_settings()

    # Point IRA at the local biped USD so populate_anim_graph() can find the
    # AnimationGraph prim.  Must be set before load_config_file() because
    # _on_config_file_loaded → setup_all_characters reads this setting.
    settings.set(
        "/exts/isaacsim.replicator.agent/asset_settings/default_biped_assets_path",
        _BIPED_USD,
    )

    # Tell omni.anim.people to loop the command file forever.
    settings.set("/exts/omni.anim.people/command_settings/number_of_loop", "inf")
    # Use navmesh for navigation (required for GoTo commands to work).
    settings.set("/exts/omni.anim.people/navigation_settings/navmesh_enabled", True)

    sim = SimulationManager()

    # --- Wait for SET_UP_SIMULATION_DONE_EVENT via asyncio.Event ---------------
    setup_done = asyncio.Event()

    def _on_setup_done(event):
        setup_done.set()

    _handle = sim.register_set_up_simulation_done_callback(_on_setup_done)

    # Load config (synchronous — reads YAML and enumerates character folder).
    ok = sim.load_config_file(CONFIG_PATH)
    if not ok:
        print("[poc] ERROR: config file failed to load — check CONFIG_PATH")
        return

    # Kick off async setup: opens scene → ASSETS_LOADED → navmesh bake → spawn.
    sim.set_up_simulation_from_config_file()
    print("[poc] Waiting for navmesh bake and character spawn …")

    try:
        await asyncio.wait_for(setup_done.wait(), timeout=SETUP_TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"[poc] ERROR: timed out after {SETUP_TIMEOUT_S} s — "
              "check Isaac Sim console for navmesh or asset errors")
        return
    finally:
        _handle = None  # release carb observer

    print("[poc] Setup complete — playing timeline")
    omni.timeline.get_timeline_interface().play()
    print("[poc] Done — character should now be walking the patrol route.")


asyncio.ensure_future(_run())
