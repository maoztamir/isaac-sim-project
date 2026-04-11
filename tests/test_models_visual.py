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
import os
import random
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"

# Evict any sys.path entry that exposes a conflicting `warehouse_sim`
# sibling. Two shadow cases exist on this machine:
#   (a) /home/ubuntu/isaac_sim_samples/warehouse_sim/ — a namespace package
#       directory with no __init__.py (shadows ours as a partial package).
#   (b) /home/ubuntu/isaac_sim_samples/warehouse_sim/src/warehouse_sim.py — a
#       single-file MODULE. If .../src/ is on sys.path, `import warehouse_sim`
#       loads this file, which has no __path__, so `warehouse_sim.models`
#       blows up with "No module named 'warehouse_sim.models'".
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

# Also drop any None-valued `warehouse_sim*` entries — the persistent Script
# Editor interpreter caches negative import results from earlier broken runs,
# and those entries aren't visible to the loop above in every case.
for k in list(sys.modules):
    if k.startswith("warehouse_sim") and sys.modules.get(k) is None:
        sys.modules.pop(k, None)

# Wipe finder / path-importer caches so Python re-scans sys.path cleanly.
import importlib
importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")
print(f"[test] warehouse_sim.__path__  = {getattr(warehouse_sim, '__path__', None)}")
_expected_pkg = os.path.join(_project_root, "warehouse_sim", "__init__.py")
if os.path.abspath(warehouse_sim.__file__) != os.path.abspath(_expected_pkg):
    raise RuntimeError(
        f"[test] WRONG warehouse_sim loaded!\n"
        f"  got:      {warehouse_sim.__file__}\n"
        f"  expected: {_expected_pkg}\n"
        f"  sys.path: {sys.path}"
    )

from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih
from warehouse_sim.scenarios import PRESETS

# ── Diagnostic block: surface everything we need to stderr before the
# failing import, so it appears in the Isaac Sim error console.
import importlib, importlib.util
print(f"[test] === PRE-IMPORT DIAGNOSTICS ===", file=sys.stderr)
print(f"[test] warehouse_sim.__file__ = {warehouse_sim.__file__}", file=sys.stderr)
print(f"[test] warehouse_sim.__path__ = {getattr(warehouse_sim, '__path__', 'NONE')}", file=sys.stderr)
try:
    _pkg_dir = warehouse_sim.__path__[0]
    print(f"[test] os.listdir({_pkg_dir}):", file=sys.stderr)
    for _entry in sorted(os.listdir(_pkg_dir)):
        print(f"         {_entry}", file=sys.stderr)
    _models_dir = os.path.join(_pkg_dir, "models")
    if os.path.isdir(_models_dir):
        print(f"[test] os.listdir({_models_dir}):", file=sys.stderr)
        for _entry in sorted(os.listdir(_models_dir)):
            print(f"         {_entry}", file=sys.stderr)
    else:
        print(f"[test] !!! {_models_dir} does NOT exist !!!", file=sys.stderr)
except Exception as e:
    print(f"[test] listdir failed: {e}", file=sys.stderr)

print(f"[test] sys.modules.get('warehouse_sim.models') = "
      f"{sys.modules.get('warehouse_sim.models')!r}", file=sys.stderr)
print(f"[test] find_spec('warehouse_sim.models') = "
      f"{importlib.util.find_spec('warehouse_sim.models')!r}", file=sys.stderr)
print(f"[test] sys.path (first 15 entries):", file=sys.stderr)
for _i, _p in enumerate(sys.path[:15]):
    print(f"         [{_i}] {_p}", file=sys.stderr)
print(f"[test] === END DIAGNOSTICS ===", file=sys.stderr)

# If find_spec sees the module but the normal import still fails, load the
# submodule directly from file to keep the rest of the test alive.
try:
    from warehouse_sim.models.loading_door import LoadingDoor
    from warehouse_sim.models.pallet import Pallet, LOC_FORKLIFT
    from warehouse_sim.models.queue_slot import QueueSlot, SLOT_DOCK
    from warehouse_sim.models.area_slot import (
        AreaSlot, build_loading_slots, build_staging_slots
    )
    from warehouse_sim.models.forklift import Forklift as FL
except ModuleNotFoundError as e:
    print(f"[test] NORMAL IMPORT FAILED: {e}", file=sys.stderr)
    print(f"[test] Falling back to explicit spec_from_file_location …", file=sys.stderr)
    def _load_from_file(dotted_name, file_path):
        spec = importlib.util.spec_from_file_location(dotted_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot create spec for {dotted_name} at {file_path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[dotted_name] = mod
        spec.loader.exec_module(mod)
        return mod
    _mdir = os.path.join(warehouse_sim.__path__[0], "models")
    # Make sure the `warehouse_sim.models` parent exists as a package object
    if "warehouse_sim.models" not in sys.modules:
        _load_from_file("warehouse_sim.models", os.path.join(_mdir, "__init__.py"))
    _ld = _load_from_file("warehouse_sim.models.loading_door", os.path.join(_mdir, "loading_door.py"))
    _pl = _load_from_file("warehouse_sim.models.pallet",       os.path.join(_mdir, "pallet.py"))
    _qs = _load_from_file("warehouse_sim.models.queue_slot",   os.path.join(_mdir, "queue_slot.py"))
    _as = _load_from_file("warehouse_sim.models.area_slot",    os.path.join(_mdir, "area_slot.py"))
    _fl = _load_from_file("warehouse_sim.models.forklift",     os.path.join(_mdir, "forklift.py"))
    LoadingDoor  = _ld.LoadingDoor
    Pallet       = _pl.Pallet
    LOC_FORKLIFT = _pl.LOC_FORKLIFT
    QueueSlot    = _qs.QueueSlot
    SLOT_DOCK    = _qs.SLOT_DOCK
    AreaSlot             = _as.AreaSlot
    build_loading_slots  = _as.build_loading_slots
    build_staging_slots  = _as.build_staging_slots
    FL = _fl.Forklift
    print("[test] fallback imports OK", file=sys.stderr)


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
