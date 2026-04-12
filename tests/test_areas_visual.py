#!/usr/bin/env python3
"""
Visual test for Task #3: areas.py (Area / AreaManager).

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

No viewport changes — all output goes to the Script Editor console.
Read each STEP block and verify every [PASS] / [FAIL] line.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES
══════════════════════════════════════════════════════════════

STEP 1: Import
  EXPECT: "Area" and "AreaManager" imported cleanly, no errors.
  PASS IF: "[PASS] areas imported" in console.
  FAIL SIGN: ImportError or AttributeError.

STEP 2: LoadingArea — capacity=1, forklift enters → is_full
  EXPECT: After FL0 enters the area, is_full=True (capacity reached).
  PASS IF: occupancy=1, is_full=True, entry_count=1.
  FAIL SIGN: is_full=False despite occupancy >= capacity.

STEP 3: Second forklift outside — is_full still True, occupancy still 1
  EXPECT: FL1 is outside the area boundary, so occupancy stays at 1.
          is_full correctly reflects the state — rule engine (Task #6)
          will use this to block FL1 from advancing.
  PASS IF: occupancy=1, is_full=True.
  FAIL SIGN: occupancy changed unexpectedly.

STEP 4: is_blocked override
  EXPECT: Setting is_blocked=True does not change occupancy or is_full.
          It is a separate flag for the rule engine to gate entry.
  PASS IF: is_blocked=True printed, is_full and occupancy unchanged.
  FAIL SIGN: is_blocked affects occupancy count.

STEP 5: Forklift exits — counters update
  EXPECT: After FL0 moves outside, occupancy=0, is_full=False,
          entry_count=1, exit_count=1, transition_count=2.
  PASS IF: All five values match exactly.
  FAIL SIGN: Any counter wrong or is_full still True.

STEP 6: ShelvesArea (capacity=None) — never full
  EXPECT: Even with 10 forklifts inside, is_full=False.
  PASS IF: is_full=False printed after all 10 forklifts added.
  FAIL SIGN: is_full=True for unlimited area.

STEP 7: pallet_count field
  EXPECT: pallet_count reflects external assignment; default is 0.
  PASS IF: pallet_count=3 after assignment, decrements correctly.
  FAIL SIGN: AttributeError or value mismatch.

STEP 8: StagingArea capacity=6, dwell tracking
  EXPECT: 6 forklifts fill it (is_full=True); dwell times increase
          with advancing sim_time; transition_count = 6 entries.
  PASS IF: is_full=True, all dwell times > 0, transition_count=6.
  FAIL SIGN: is_full=False at 6 occupants, or dwell=0.

STEP 9: AreaManager.area_of()
  EXPECT: Returns the correct Area for a position inside it,
          None for a position in open floor.
  PASS IF: area_of returns "LoadingArea" for a point inside it,
           None for a point outside all areas.
  FAIL SIGN: Wrong area returned or None for a valid inside point.

STEP 10: print_status()
  EXPECT: One line per area with occupancy, capacity, full, blocked,
          pallets, transitions, and dwell times all visible.
  PASS IF: Three lines printed (LoadingArea, StagingArea, ShelvesArea).
  FAIL SIGN: Missing line, wrong format, or AttributeError.
══════════════════════════════════════════════════════════════
"""

import asyncio
import os
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

import importlib
importlib.invalidate_caches()

import warehouse_sim
print(f"[test] warehouse_sim loaded from: {warehouse_sim.__file__}")


def _banner(title):
    print(f"\n{'═' * 60}\n  {title}\n{'═' * 60}")


def _check(label, got, expected):
    ok = got == expected
    print(f"  {'[PASS]' if ok else '[FAIL]'} {label}: got={got!r}  expected={expected!r}")
    return ok


async def _run():
    # ── STEP 1: Import ───────────────────────────────────────────────────────
    _banner("STEP 1: Import areas")
    try:
        from warehouse_sim.areas import Area, AreaManager
        from warehouse_sim import config as C
        print("  [PASS] areas imported")
    except Exception as e:
        print(f"  [FAIL] {e}")
        return

    # ── STEP 2: LoadingArea — forklift enters, is_full ───────────────────────
    _banner("STEP 2: LoadingArea capacity=1 — FL0 enters → is_full")
    loading = Area("LoadingArea", 0.0, 4.0, 0.0, 4.0, capacity=1)
    # FL0 inside the area
    loading.update_occupant(0, 2.0, 2.0, sim_time=0.0)
    _check("occupancy",    loading.occupancy,      1)
    _check("is_full",      loading.is_full,         True)
    _check("entry_count",  loading._entry_count,    1)
    _check("exit_count",   loading._exit_count,     0)

    # ── STEP 3: FL1 outside — is_full still True ─────────────────────────────
    _banner("STEP 3: FL1 outside boundary — occupancy unchanged")
    loading.update_occupant(1, 99.0, 99.0, sim_time=1.0)  # outside
    _check("occupancy",  loading.occupancy,  1)
    _check("is_full",    loading.is_full,    True)

    # ── STEP 4: is_blocked override ──────────────────────────────────────────
    _banner("STEP 4: is_blocked override")
    loading.is_blocked = True
    _check("is_blocked",  loading.is_blocked,  True)
    _check("occupancy",   loading.occupancy,   1)   # unaffected
    _check("is_full",     loading.is_full,     True)  # unaffected
    loading.is_blocked = False  # reset

    # ── STEP 5: FL0 exits — counters update ──────────────────────────────────
    _banner("STEP 5: FL0 exits — counters update")
    loading.update_occupant(0, 99.0, 99.0, sim_time=5.0)  # moved outside
    _check("occupancy",         loading.occupancy,         0)
    _check("is_full",           loading.is_full,           False)
    _check("entry_count",       loading._entry_count,      1)
    _check("exit_count",        loading._exit_count,       1)
    _check("transition_count",  loading.transition_count,  2)

    # ── STEP 6: ShelvesArea (capacity=None) — never full ────────────────────
    _banner("STEP 6: ShelvesArea capacity=None — never full with 10 forklifts")
    shelves = Area("ShelvesArea", 0.0, 50.0, 0.0, 50.0, capacity=None)
    for i in range(10):
        shelves.update_occupant(i, float(i), float(i), sim_time=0.0)
    _check("occupancy",  shelves.occupancy,  10)
    _check("is_full",    shelves.is_full,    False)

    # ── STEP 7: pallet_count field ───────────────────────────────────────────
    _banner("STEP 7: pallet_count external assignment")
    staging = Area("StagingArea", 0.0, 20.0, 0.0, 20.0, capacity=6)
    _check("pallet_count default",  staging.pallet_count,  0)
    staging.pallet_count = 3
    _check("pallet_count = 3",      staging.pallet_count,  3)
    staging.pallet_count -= 1
    _check("pallet_count -= 1",     staging.pallet_count,  2)

    # ── STEP 8: StagingArea capacity=6, dwell tracking ───────────────────────
    _banner("STEP 8: StagingArea capacity=6 — fill to max, check dwell")
    staging2 = Area("StagingArea", 0.0, 20.0, 0.0, 20.0, capacity=6)
    for i in range(6):
        staging2.update_occupant(i, float(i), float(i), sim_time=0.0)
    _check("occupancy",         staging2.occupancy,         6)
    _check("is_full",           staging2.is_full,           True)
    _check("transition_count",  staging2.transition_count,  6)
    # Advance sim time and check dwell
    for i in range(6):
        dwell = staging2.dwell_time(i, sim_time=10.0)
        ok = dwell > 0
        print(f"  {'[PASS]' if ok else '[FAIL]'} FL{i} dwell={dwell:.1f}s")

    # ── STEP 9: AreaManager.area_of() ────────────────────────────────────────
    _banner("STEP 9: AreaManager.area_of()")
    mgr = AreaManager()
    mgr.add("LoadingArea",  0.0, 4.0,  0.0, 4.0,  capacity=C.LOADING_AREA_CAPACITY)
    mgr.add("StagingArea",  0.0, 20.0, 5.0, 20.0, capacity=C.STAGING_AREA_CAPACITY)
    mgr.add("ShelvesArea",  0.0, 50.0, 21.0, 50.0, capacity=None)

    result = mgr.area_of(2.0, 2.0)
    print(f"  area_of(2,2) = {result.name if result else None}")
    _check("area_of inside LoadingArea",  result.name if result else None, "LoadingArea")

    result2 = mgr.area_of(99.0, 99.0)
    _check("area_of open floor",  result2, None)

    # ── STEP 10: print_status() ───────────────────────────────────────────────
    _banner("STEP 10: AreaManager.print_status()")
    # Put one forklift in LoadingArea
    mgr.update(0, 2.0, 2.0, sim_time=0.0)
    print("  --- print_status output below ---")
    mgr.print_status(sim_time=5.0)
    print("  --- end print_status ---")
    print("  [PASS] print_status ran without error")

    _banner("ALL STEPS COMPLETE — review [PASS]/[FAIL] lines above")


asyncio.ensure_future(_run())
