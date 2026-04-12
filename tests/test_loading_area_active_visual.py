#!/usr/bin/env python3
"""
Visual test — loading area slot activate / deactivate.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Builds the dock_queue scene (scene is NOT started — no forklift movement),
spawns pallets in all 3 loading-door slots, then toggles each slot off and on
so you can visually confirm that individual bays can be marked active / idle.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 0: Build scene
  EXPECT: Warehouse USD loads, 3 loading gates (closed), zebra tape visible.
  PASS IF: Scene settles with no errors in console.
  FAIL SIGN: Errors in console, black screen, missing geometry.

STEP 1: Spawn pallets in all 3 loading slots (ALL ACTIVE) — hold 30s
  EXPECT: 3 small pallet clusters appear, one in front of each loading gate
          (LEFT, CENTRE, RIGHT). All 3 clusters visible simultaneously.
  PASS IF: 3 clusters visible, 2 pallets each.
  FAIL SIGN: Missing cluster, pallets spawned far from gates or at origin.

STEP 2: Deactivate loading_slots[0] (LEFT gate) — hold 30s
  EXPECT: Pallets in front of the LEFT gate disappear.
          CENTRE and RIGHT clusters remain visible.
  PASS IF: Only the left cluster is gone.
  FAIL SIGN: Wrong cluster hidden, or more than one cluster missing.

STEP 3: Deactivate loading_slots[1] (CENTRE gate) — hold 30s
  EXPECT: Pallets in front of the CENTRE gate also disappear.
          LEFT and CENTRE now hidden; RIGHT still visible.
  PASS IF: LEFT + CENTRE hidden, RIGHT visible.
  FAIL SIGN: RIGHT cluster also hidden, or CENTRE still visible.

STEP 4: Deactivate loading_slots[2] (RIGHT gate) — hold 30s
  EXPECT: All 3 loading-slot pallet clusters are hidden.
          The loading area looks empty.
  PASS IF: No pallet clusters visible in the loading zone.
  FAIL SIGN: Any cluster still visible.

STEP 5: Reactivate loading_slots[0] (LEFT gate) — hold 30s
  EXPECT: LEFT gate pallets reappear.
          CENTRE and RIGHT remain hidden.
  PASS IF: Only the left cluster is visible again.
  FAIL SIGN: Multiple clusters reappeared, or wrong cluster.

STEP 6: Reactivate loading_slots[1] and [2] — hold 30s
  EXPECT: All 3 loading-slot pallet clusters visible again.
          Full active state restored.
  PASS IF: All 3 clusters visible.
  FAIL SIGN: One or more clusters still hidden.

STEP 7: Final stable pause — 5s
  EXPECT: Scene stable, all 3 loading slots ACTIVE with pallets visible.
  PASS IF: Console shows all 3 slots as ACTIVE.
══════════════════════════════════════════════════════════════
"""

# ── Knobs ───────────────────────────────────────────────────────────────────
SLOT_HOLD_SEC   = 30.0   # hold duration after each activate / deactivate
FINAL_HOLD_SEC  =  5.0
PALLETS_PER_SLOT = 2
SEED             = 42
SCENARIO         = "dock_queue"
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import importlib
import os
import random
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"

# Evict any sys.path entry that exposes a conflicting `warehouse_sim` sibling
# — either a namespace-package directory OR a single-file warehouse_sim.py.
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

# Drop any None-valued warehouse_sim entries (negative cache from earlier
# broken runs in the persistent Script Editor interpreter).
for k in list(sys.modules):
    if k.startswith("warehouse_sim") and sys.modules.get(k) is None:
        sys.modules.pop(k, None)

# Delete stale .pyc files so Isaac Sim's persistent interpreter picks up
# source changes rather than cached bytecode from a previous run.
import glob as _glob
for _pyc in _glob.glob(
        os.path.join(_project_root, "warehouse_sim", "**", "*.pyc"),
        recursive=True):
    try:
        os.remove(_pyc)
    except OSError:
        pass

# Wipe finder / path-importer caches so Python re-scans sys.path cleanly.
importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")

from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih
from warehouse_sim.scenarios import PRESETS
from warehouse_sim.models.area_slot import AreaSlot, build_loading_slots


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

    # ── STEP 1: Spawn pallets in all 3 loading slots (ALL ACTIVE) ────────────
    _banner("STEP 1: Spawn pallets — all 3 loading slots ACTIVE")
    loading_slots = build_loading_slots()
    rng = random.Random(SEED)
    for s in loading_slots:
        s.spawn_pallets(stage, assets_root, count=PALLETS_PER_SLOT, rng=rng)
    for s in loading_slots:
        print(f"  {s}")
    print(f"  [PASS] {len(loading_slots)} slots spawned, all ACTIVE")
    await _hold("all 3 loading slots visible", SLOT_HOLD_SEC)

    # ── STEP 2: Deactivate slot 0 (LEFT) ─────────────────────────────────────
    _banner("STEP 2: Deactivate loading_slots[0] — LEFT gate")
    loading_slots[0].deactivate(stage)
    for s in loading_slots:
        print(f"  {s}")
    await _hold("LEFT hidden, CENTRE + RIGHT visible", SLOT_HOLD_SEC)

    # ── STEP 3: Deactivate slot 1 (CENTRE) ───────────────────────────────────
    _banner("STEP 3: Deactivate loading_slots[1] — CENTRE gate")
    loading_slots[1].deactivate(stage)
    for s in loading_slots:
        print(f"  {s}")
    await _hold("LEFT + CENTRE hidden, RIGHT visible", SLOT_HOLD_SEC)

    # ── STEP 4: Deactivate slot 2 (RIGHT) ────────────────────────────────────
    _banner("STEP 4: Deactivate loading_slots[2] — RIGHT gate")
    loading_slots[2].deactivate(stage)
    for s in loading_slots:
        print(f"  {s}")
    await _hold("ALL 3 loading slots hidden", SLOT_HOLD_SEC)

    # ── STEP 5: Reactivate slot 0 (LEFT) ─────────────────────────────────────
    _banner("STEP 5: Reactivate loading_slots[0] — LEFT gate")
    loading_slots[0].activate(stage)
    for s in loading_slots:
        print(f"  {s}")
    await _hold("LEFT visible, CENTRE + RIGHT hidden", SLOT_HOLD_SEC)

    # ── STEP 6: Reactivate slots 1 and 2 ─────────────────────────────────────
    _banner("STEP 6: Reactivate loading_slots[1] and [2]")
    loading_slots[1].activate(stage)
    loading_slots[2].activate(stage)
    for s in loading_slots:
        print(f"  {s}")
    await _hold("all 3 loading slots ACTIVE again", SLOT_HOLD_SEC)

    # ── STEP 7: Final pause ───────────────────────────────────────────────────
    _banner("STEP 7: Final stable scene")
    await _hold("final", FINAL_HOLD_SEC)
    _banner("ALL STEPS COMPLETE — review [PASS] lines above")


asyncio.ensure_future(_run())
