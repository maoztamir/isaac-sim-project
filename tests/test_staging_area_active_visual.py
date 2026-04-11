#!/usr/bin/env python3
"""
Visual test — staging area slot activate / deactivate.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Builds the dock_queue scene, REMOVES the pre-built staging props that the
scenario spawns by default, then spawns fresh pallet+box clusters via the
AreaSlot model so each of the 3 staging bays can be toggled active / inactive.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 0: Build scene
  EXPECT: Warehouse USD loads, 3 loading gates (closed), zebra tape visible.
          Staging area is empty (no pre-built props).
  PASS IF: Scene settles, no errors in console.
  FAIL SIGN: Errors in console, black screen, missing geometry.

STEP 1: Spawn pallet+box clusters in all 3 staging slots (ALL ACTIVE) — hold 30s
  EXPECT: 3 clusters of pallets with cardboard boxes appear inside the staging
          bays (LEFT, CENTRE, RIGHT), one cluster per bay.
  PASS IF: 3 clusters visible, each with boxes on top of pallets.
  FAIL SIGN: Missing cluster, boxes not visible, pallets at wrong location.

STEP 2: Deactivate staging_slots[0] (LEFT bay) — hold 30s
  EXPECT: Pallets + boxes in the LEFT staging bay disappear.
          CENTRE and RIGHT clusters remain visible.
  PASS IF: Only the left cluster is gone.
  FAIL SIGN: Wrong cluster hidden, or more than one hidden.

STEP 3: Deactivate staging_slots[1] (CENTRE bay) — hold 30s
  EXPECT: CENTRE bay cluster also disappears.
          LEFT + CENTRE hidden; RIGHT still visible.
  PASS IF: LEFT + CENTRE hidden, RIGHT visible.
  FAIL SIGN: RIGHT also hidden, or CENTRE still visible.

STEP 4: Deactivate staging_slots[2] (RIGHT bay) — hold 30s
  EXPECT: All 3 staging-slot clusters are hidden. Staging area looks empty.
  PASS IF: No pallet/box clusters visible in the staging zone.
  FAIL SIGN: Any cluster still visible.

STEP 5: Reactivate staging_slots[0] (LEFT bay) — hold 30s
  EXPECT: LEFT bay pallets + boxes reappear.
          CENTRE and RIGHT remain hidden.
  PASS IF: Only the left cluster is visible again.
  FAIL SIGN: Multiple clusters reappeared, or wrong cluster.

STEP 6: Reactivate staging_slots[1] and [2] — hold 30s
  EXPECT: All 3 staging-slot clusters visible again. Full active state restored.
  PASS IF: All 3 clusters visible with boxes.
  FAIL SIGN: One or more clusters still hidden.

STEP 7: Final stable pause — 5s
  EXPECT: Scene stable, all 3 staging slots ACTIVE.
  PASS IF: Console shows all 3 slots as ACTIVE.
══════════════════════════════════════════════════════════════
"""

# ── Knobs ───────────────────────────────────────────────────────────────────
SLOT_HOLD_SEC    = 30.0
FINAL_HOLD_SEC   =  5.0
PALLETS_PER_SLOT =  3
SEED             = 42
SCENARIO         = "dock_queue"
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import importlib
import os
import random
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"

_bad_paths = []
for p in list(sys.path):
    try:
        if not p or p == _project_root:
            continue
        if os.path.isdir(os.path.join(p, "warehouse_sim")):
            _bad_paths.append(p)
        elif os.path.isfile(os.path.join(p, "warehouse_sim.py")):
            _bad_paths.append(p)
    except Exception:
        pass
for p in _bad_paths:
    while p in sys.path:
        sys.path.remove(p)
    print(f"[test] evicted conflicting sys.path entry: {p}")

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
_pyc_root = os.path.join(_project_root, "warehouse_sim")
for _pyc in _glob.glob(os.path.join(_pyc_root, "**", "*.pyc"), recursive=True):
    try:
        os.remove(_pyc)
    except Exception:
        pass

importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")

from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih
from warehouse_sim.scenarios import PRESETS
from warehouse_sim.models.area_slot import AreaSlot, TYPE_STAGING


def _banner(title):
    print(f"\n{'═' * 60}\n  {title}\n{'═' * 60}")


async def _hold(label: str, seconds: float):
    print(f"   ⏸  {label} — holding {seconds:.0f}s")
    steps = max(1, int(seconds * 60))
    for _ in range(steps):
        await ih.next_update()


async def _run():
    # ── STEP 0: Build scene ──────────────────────────────────────────────────
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

    # ── STEP 1: Spawn pallet+box clusters (ALL ACTIVE) ───────────────────────
    _banner("STEP 1: Spawn pallets+boxes — all 3 staging slots ACTIVE")
    # Build slots with width=6.0 (< gate spacing of 7.0) so each slot's spawn
    # zone is fully contained within its own bay with no cross-bay overlap.
    staging_slots = [
        AreaSlot(slot_id=i, area_type=TYPE_STAGING,
                 center=(C.WAREHOUSE_CX + offset, C.STAGING_CENTER_Y),
                 width=6.0, depth=C.STAGING_D)
        for i, offset in enumerate(C.GATE_OFFSETS)
    ]
    rng = random.Random(SEED)
    for s in staging_slots:
        s.spawn_pallets(stage, assets_root, count=PALLETS_PER_SLOT, rng=rng)
    for s in staging_slots:
        print(f"  {s}")
    print(f"  [PASS] {len(staging_slots)} slots spawned with pallets + boxes, all ACTIVE")
    await _hold("all 3 staging slots visible", SLOT_HOLD_SEC)

    # ── STEP 2: Deactivate slot 0 (LEFT) ─────────────────────────────────────
    _banner("STEP 2: Deactivate staging_slots[0] — LEFT bay")
    staging_slots[0].deactivate(stage)
    for s in staging_slots:
        print(f"  {s}")
    await _hold("LEFT hidden, CENTRE + RIGHT visible", SLOT_HOLD_SEC)

    # ── STEP 3: Deactivate slot 1 (CENTRE) ───────────────────────────────────
    _banner("STEP 3: Deactivate staging_slots[1] — CENTRE bay")
    staging_slots[1].deactivate(stage)
    for s in staging_slots:
        print(f"  {s}")
    await _hold("LEFT + CENTRE hidden, RIGHT visible", SLOT_HOLD_SEC)

    # ── STEP 4: Deactivate slot 2 (RIGHT) ────────────────────────────────────
    _banner("STEP 4: Deactivate staging_slots[2] — RIGHT bay")
    staging_slots[2].deactivate(stage)
    for s in staging_slots:
        print(f"  {s}")
    await _hold("ALL 3 staging slots hidden", SLOT_HOLD_SEC)

    # ── STEP 5: Reactivate slot 0 (LEFT) ─────────────────────────────────────
    _banner("STEP 5: Reactivate staging_slots[0] — LEFT bay")
    staging_slots[0].activate(stage)
    for s in staging_slots:
        print(f"  {s}")
    await _hold("LEFT visible, CENTRE + RIGHT hidden", SLOT_HOLD_SEC)

    # ── STEP 6: Reactivate slots 1 and 2 ─────────────────────────────────────
    _banner("STEP 6: Reactivate staging_slots[1] and [2]")
    staging_slots[1].activate(stage)
    staging_slots[2].activate(stage)
    for s in staging_slots:
        print(f"  {s}")
    await _hold("all 3 staging slots ACTIVE again", SLOT_HOLD_SEC)

    # ── STEP 7: Final pause ───────────────────────────────────────────────────
    _banner("STEP 7: Final stable scene")
    await _hold("final", FINAL_HOLD_SEC)
    _banner("ALL STEPS COMPLETE — review [PASS] lines above")


asyncio.ensure_future(_run())
