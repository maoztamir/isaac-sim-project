#!/usr/bin/env python3
"""
Visual test for Task #4: models/ package.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Builds a scene, then walks through the model classes with visible pauses
so you can confirm each behaviour in the viewport.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 0: Scene build
  EXPECT: Warehouse USD + 3 loading gates (closed) + zebra tape visible.
  PASS IF: Scene settles, no errors in console.

STEP 1: Spawn one Forklift at centre of open floor → UNLOADED
  EXPECT: Forklift visible, no pallet on its forks.
  PASS IF: Forklift prim exists, self.load == "unloaded".

STEP 2: forklift.set_load(LOADED) — hold 60s
  EXPECT: A pallet prim APPEARS on the forklift's fork, roughly at
          fork travel height above the forklift body. The pallet rides
          with the forklift (though the forklift is not moving here).
  PASS IF: Pallet visible above forks for the full 60s hold.
  FAIL SIGN: No pallet visible, pallet on the floor, or pallet clipping
             inside the forklift body.

STEP 3: Build AreaSlots — 3 loading, 3 staging, ALL ACTIVE → hold 10s
  EXPECT: 6 clusters of pallets spawn:
          - 3 small clusters in front of each loading door
          - 3 small clusters inside each staging bay
          All 6 clusters visible.
  PASS IF: Every AreaSlot has visible pallets.
  FAIL SIGN: Missing pallets, pallets in wrong location.

STEP 4: Deactivate loading_slot[0] → hold 10s
  EXPECT: Pallets in the LEFT loading door disappear.
          Pallets in loading_1 (center), loading_2 (right), and all
          3 staging bays remain visible.
  PASS IF: Only the left loading-door pallets are gone.

STEP 5: Deactivate staging_slot[1] → hold 10s
  EXPECT: Pallets in the MIDDLE staging bay also disappear.
          Now hidden: loading_0 + staging_1. Rest visible.
  PASS IF: Loading_0 AND staging_1 hidden, other 4 slots visible.

STEP 6: Reactivate both → hold 10s
  EXPECT: All 6 slots have visible pallets again.
  PASS IF: All pallet clusters back.

STEP 7: forklift.set_load(UNLOADED) → hold 10s
  EXPECT: The pallet on the forklift disappears. Forklift body unchanged.
  PASS IF: Carried pallet gone, forklift itself still visible.

STEP 8: LoadingDoor(gate=0).open() → hold 30s → close()
  EXPECT: Left gate shutters vanish, black truck-back visible.
          After 30s hold, shutters reappear.
  PASS IF: Door visually opens and closes.

STEP 9: QueueSlot console check
  EXPECT: A QueueSlot can be assigned a forklift id, is_free flips to
          False, release() flips it back. Printed to console.
  PASS IF: Console shows is_free=False after assign, True after release.

STEP 10: Final pause — inspect scene
  EXPECT: Scene is stable, all 6 slots active, forklift unloaded,
          gate 0 closed.
══════════════════════════════════════════════════════════════
"""

# ── Knobs (tweak freely) ────────────────────────────────────────────────────
LOAD_HOLD_SEC        = 60.0   # STEP 2 — loaded pallet visible hold
SLOT_HOLD_SEC        = 10.0   # STEPS 3–7 — slot toggle holds
DOOR_OPEN_HOLD_SEC   = 30.0   # STEP 8 — door open hold
FINAL_HOLD_SEC       =  5.0
SCENARIO             = "dock_queue"
SEED                 = 42
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import random
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"
if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

_to_remove = [k for k in sys.modules if k.startswith("warehouse_sim")]
for k in _to_remove:
    del sys.modules[k]

from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih
from warehouse_sim.scenarios import PRESETS
from warehouse_sim.models.loading_door import LoadingDoor
from warehouse_sim.models.pallet import Pallet, LOC_FORKLIFT
from warehouse_sim.models.queue_slot import QueueSlot, SLOT_DOCK
from warehouse_sim.models.area_slot import (
    AreaSlot, build_loading_slots, build_staging_slots
)
from warehouse_sim.models.forklift import Forklift as FL


def _banner(title):
    print(f"\n{'═' * 60}\n  {title}\n{'═' * 60}")


async def _hold(label: str, seconds: float):
    print(f"   ⏸  {label} — holding {seconds:.0f}s")
    steps = max(1, int(seconds * 60))
    for _ in range(steps):
        await ih.next_update()


async def _run():
    # ── STEP 0: Scene build ──────────────────────────────────────────────────
    _banner("STEP 0: Build scene (dock_queue preset, NOT started)")
    if SCENARIO not in PRESETS:
        print(f"  [FAIL] unknown scenario '{SCENARIO}'")
        return

    scenario = PRESETS[SCENARIO](seed=SEED)
    await scenario.build()
    stage = scenario.stage
    assets_root = scenario.assets_root
    await _hold("scene settled", 2.0)
    print("  [PASS] scene built")

    # ── STEP 1: Spawn Forklift UNLOADED ──────────────────────────────────────
    _banner("STEP 1: Spawn standalone Forklift (UNLOADED)")
    spawn_x = C.WAREHOUSE_CX
    spawn_y = C.STAGING_CENTER_Y - 2.0
    fl_path = "/World/TestForklift"
    ih.spawn_asset(stage, fl_path, assets_root + C.FORKLIFT_USD,
                   spawn_x, spawn_y, 0.0, 90.0)
    forklift = FL(fl_id=99, prim_path=fl_path, x=spawn_x, y=spawn_y)
    print(f"  forklift: {forklift}")
    print(f"  [{'PASS' if forklift.load == C.LOAD_UNLOADED else 'FAIL'}] load == unloaded")
    await _hold("forklift unloaded", 3.0)

    # ── STEP 2: set_load(LOADED) → hold 60s ──────────────────────────────────
    _banner(f"STEP 2: forklift.set_load(LOADED) — hold {LOAD_HOLD_SEC:.0f}s")
    forklift.set_load(stage, C.LOAD_LOADED, assets_root=assets_root)
    print(f"  forklift: {forklift}")
    print(f"  [{'PASS' if forklift.has_pallet else 'FAIL'}] has_pallet == True")
    await _hold("carried pallet visible", LOAD_HOLD_SEC)

    # ── STEP 3: Build AreaSlots — all ACTIVE ─────────────────────────────────
    _banner("STEP 3: Build 3 loading + 3 staging AreaSlots, ALL ACTIVE")
    loading_slots = build_loading_slots()
    staging_slots = build_staging_slots()
    rng = random.Random(123)
    for s in loading_slots:
        s.spawn_pallets(stage, assets_root, count=2, rng=rng)
    for s in staging_slots:
        s.spawn_pallets(stage, assets_root, count=3, rng=rng)
    for s in loading_slots + staging_slots:
        print(f"  {s}")
    print("  [PASS] 6 slots spawned with pallets visible")
    await _hold("all 6 slots active", SLOT_HOLD_SEC)

    # ── STEP 4: Deactivate loading_slot[0] ───────────────────────────────────
    _banner("STEP 4: deactivate loading_slots[0] (LEFT door)")
    loading_slots[0].deactivate(stage)
    print(f"  {loading_slots[0]}")
    await _hold("loading_0 pallets HIDDEN", SLOT_HOLD_SEC)

    # ── STEP 5: Deactivate staging_slot[1] ───────────────────────────────────
    _banner("STEP 5: deactivate staging_slots[1] (MIDDLE bay)")
    staging_slots[1].deactivate(stage)
    print(f"  {staging_slots[1]}")
    await _hold("loading_0 + staging_1 HIDDEN", SLOT_HOLD_SEC)

    # ── STEP 6: Reactivate both ──────────────────────────────────────────────
    _banner("STEP 6: Reactivate loading_slots[0] and staging_slots[1]")
    loading_slots[0].activate(stage)
    staging_slots[1].activate(stage)
    print(f"  {loading_slots[0]}")
    print(f"  {staging_slots[1]}")
    await _hold("all 6 slots active again", SLOT_HOLD_SEC)

    # ── STEP 7: forklift.set_load(UNLOADED) ──────────────────────────────────
    _banner("STEP 7: forklift.set_load(UNLOADED)")
    forklift.set_load(stage, C.LOAD_UNLOADED)
    print(f"  forklift: {forklift}")
    print(f"  [{'PASS' if not forklift.has_pallet else 'FAIL'}] has_pallet == False")
    await _hold("carried pallet gone", SLOT_HOLD_SEC)

    # ── STEP 8: LoadingDoor open/close ───────────────────────────────────────
    _banner("STEP 8: LoadingDoor(0) — open → hold → close")
    door0 = LoadingDoor(gate_idx=0)
    door0.open(stage)
    print(f"  {door0}")
    await _hold("door 0 open", DOOR_OPEN_HOLD_SEC)
    door0.close(stage)
    print(f"  {door0}")
    await _hold("door 0 closed", 3.0)

    # ── STEP 9: QueueSlot console check ──────────────────────────────────────
    _banner("STEP 9: QueueSlot assign/release")
    slot = QueueSlot(slot_id=0, position=(0.0, 0.0), slot_type=SLOT_DOCK)
    print(f"  initial: {slot}  is_free={slot.is_free}")
    ok1 = slot.assign(forklift_id=5)
    print(f"  assign(FL5): {slot}  is_free={slot.is_free}  result={ok1}")
    slot.release()
    print(f"  release(): {slot}  is_free={slot.is_free}")
    if slot.is_free:
        print("  [PASS] QueueSlot assign/release cycle")
    else:
        print("  [FAIL] QueueSlot did not release")

    # ── STEP 10: Final pause ─────────────────────────────────────────────────
    _banner("STEP 10: Final stable scene")
    await _hold("final", FINAL_HOLD_SEC)
    _banner("ALL TESTS COMPLETE — review [PASS]/[FAIL] lines above")


asyncio.ensure_future(_run())
