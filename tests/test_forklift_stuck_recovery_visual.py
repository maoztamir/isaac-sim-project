"""
Visual test — forklift stuck-recovery (reversal) mechanic.

Loads the dock_queue scenario and verifies that forklifts do NOT stay
permanently frozen in the shelves area after completing their pickup.

──────────────────────────────────────────────────────────────────────────────
STEP 1: Scene build
  EXPECT: Warehouse loads, 4 forklifts spawn on the south floor.
  PASS IF: 4 forklifts visible near Y = -18.6.
  FAIL SIGN: Script error or empty viewport.

STEP 2: IDLE → PICKUP_AT_SHELVES (t ≈ 0–15 s)
  EXPECT: All 4 forklifts drive north toward the shelf aisles.
  PASS IF: Forklifts moving, spd > 0 for at least some of them.
  FAIL SIGN: Forklifts stay stationary at spawn.

STEP 3: Pickup dwell (t ≈ 15–25 s)
  EXPECT: Forklifts reach the aisle approach line (Y ≈ 6.6) and stop
          for ~4 s (PICKUP_DURATION) while the timer counts down.
  PASS IF: Console shows forklifts at Y ≈ 4–7, spd = 0.
  FAIL SIGN: Forklifts never reach Y > 4.

STEP 4: PICKUP → MOVE_TO_STAGING transition (t ≈ 25 s)
  EXPECT: Console prints "[RuleEngine] FLx: pickup_at_shelves → move_to_staging"
          for all 4 forklifts.
  PASS IF: All four transition messages appear.
  FAIL SIGN: Only some transition or none at all.

STEP 5: Recovery kicks in if blocked (t ≈ 25–27 s)
  EXPECT: Any forklift that was frozen during U-turn (blocked look-ahead)
          briefly reverses (moves slightly away from its pickup position)
          then resumes driving south.
  PASS IF: Forklift Y positions START DECREASING within ~3 s of transition.
  FAIL SIGN: Forklifts stay frozen at Y ≈ 5–6 indefinitely (old bug).

STEP 6: Forklifts reach staging (t ≈ 30–50 s)
  EXPECT: Forklifts arrive at the zebra-tape staging zone (Y ≈ -7.65).
          Console shows "state=wait_in_staging" or "state=move_to_loading".
  PASS IF: At least one forklift reports Y < -4 and state != pickup_at_shelves.
  FAIL SIGN: All forklifts still at Y > 4 after 50 s.

STEP 7: Dock pallets visible at active gates (first physics step)
  EXPECT: Console prints "[dock_queue] dock pallets spawned at gates [0, 2]".
          Two box props appear in the loading zones in front of gates 0 (left)
          and 2 (right). The middle gate (1) loading zone is empty.
  PASS IF: Two box props visible at the south wall; middle zone has no prop.
  FAIL SIGN: No boxes visible, or error loading SM_CardBoxA_01.usd.
──────────────────────────────────────────────────────────────────────────────
"""

import sys
import os
import asyncio

# ── Hot-reload block ─────────────────────────────────────────────────────────
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
# ─────────────────────────────────────────────────────────────────────────────

# ── Knobs ────────────────────────────────────────────────────────────────────
SCENARIO_NAME   = "dock_queue"
# How long (sim seconds) to wait before printing final state summary
OBSERVE_SECS    = 55.0
# Y threshold: if any forklift drops below this we consider staging reached
STAGING_Y_THRESHOLD = -4.0
# ─────────────────────────────────────────────────────────────────────────────

from warehouse_sim.scenarios.dock_queue import DockQueueScenario
import warehouse_sim.isaac_helpers as ih


async def _run():
    scenario = DockQueueScenario(seed=42)
    await scenario.build()

    print(f"\n[test] Scene built — starting simulation (observe {OBSERVE_SECS}s).")
    print("[test] Watch for forklifts driving north, pausing at shelves,")
    print("[test] then reversing briefly if blocked, and finally heading south.")

    # Start physics
    scenario.start()

    # Observe for OBSERVE_SECS sim-seconds, printing snapshots every 5 s
    elapsed = 0.0
    snapshot_interval = 5.0
    next_snap = snapshot_interval

    import time as _time
    wall_start = _time.time()

    while elapsed < OBSERVE_SECS:
        await ih.next_update()
        elapsed = scenario.sim_time

        if elapsed >= next_snap:
            next_snap += snapshot_interval
            print(f"\n[test] t={elapsed:.1f}s  snapshot:")
            for fl in scenario.forklifts:
                area = scenario.area_mgr.area_of(fl.pos[0], fl.pos[1])
                aname = area.name if area else "open"
                print(f"  FL{fl.id}: ({fl.pos[0]:6.1f},{fl.pos[1]:6.1f}) "
                      f"spd={fl.speed:.2f} state={fl.state:20s} area={aname} "
                      f"stuck={fl._stuck_secs:.2f}s  rev={fl._recovery_secs:.2f}s")

    # Final verdict
    print("\n[test] ── FINAL CHECK ───────────────────────────────────────")
    reached_staging = [fl for fl in scenario.forklifts
                       if fl.pos[1] < STAGING_Y_THRESHOLD]
    still_stuck     = [fl for fl in scenario.forklifts
                       if fl.pos[1] > 4.0 and fl.speed < 0.05]

    print(f"  Forklifts that reached staging (Y < {STAGING_Y_THRESHOLD}): "
          f"{[fl.id for fl in reached_staging]}")
    print(f"  Forklifts still frozen in shelves area: "
          f"{[fl.id for fl in still_stuck]}")

    if still_stuck:
        print("[test] FAIL — forklifts frozen. Recovery did not work.")
    else:
        print("[test] PASS — no forklifts permanently frozen.")


asyncio.ensure_future(_run())
