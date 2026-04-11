#!/usr/bin/env python3
"""
Visual test — forklift loaded / unloaded state while moving.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Uses the forklifts spawned by the dock_queue scenario. Starts the simulation
so forklifts drive their patrol routes, then attaches / detaches a pallet prim
as a child of each forklift prim so it rides on the forks.

Pallet local-frame offset (calibrated in test_pallet_position_visual.py):
    X = C.PALLET_FORK_LOCAL_X  (+0.072 m — centred left/right on forks)
    Y = C.PALLET_FORK_LOCAL_Y  (-1.196 m — forward to the fork tines)
    Z = C.PALLET_FORK_LOCAL_Z  (+0.194 m — fork tine travel height)

A child prim inherits the parent's world transform automatically — no per-frame
sync needed. show/hide toggles between LOADED and UNLOADED states.

══════════════════════════════════════════════════════════════
EXPECTED VISUAL OUTCOMES  (N = number of forklifts in scenario)
══════════════════════════════════════════════════════════════

STEP 0: Build scene
  EXPECT: Warehouse USD loads, loading gates (closed), zebra tape visible.
          N forklifts spawned at their start positions.
  PASS IF: Scene settles, no errors in console.
  FAIL SIGN: Errors in console, black screen, missing geometry.

STEP 1: Start simulation — ALL UNLOADED — hold 30s
  EXPECT: All N forklifts begin their patrol routes. No pallets visible.
  PASS IF: All forklifts move, no pallet prim visible on any of them.
  FAIL SIGN: Forklifts stationary, or pallet already visible.

STEP 2 … N+1: Load forklifts one by one — hold 30s each
  EXPECT: Each step adds one more pallet on the newly loaded forklift's
          forks (offset ~1.2 m forward, centred left/right, ~0.19 m high),
          riding with it as it moves. Previously loaded forklifts keep
          their pallets; forklifts not yet loaded remain empty.
  PASS IF: Exactly i forklifts carry visible pallets after step i+1,
           each pallet tracks its forklift and sits on the fork tines
           (not buried in the body or floating above the forks).
  FAIL SIGN: Pallet centred on forklift body, below floor, floating,
             not tracking its forklift, or wrong count of pallets visible.

STEP N+2: ALL LOADED — hold 30s
  EXPECT: All N forklifts carry a raised pallet that moves with them.
  PASS IF: N pallet prims visible, all tracking their forklifts.
  FAIL SIGN: Any forklift missing its pallet, or pallets not tracking.

STEP N+3 … 2N+2: Unload forklifts one by one — hold 30s each
  EXPECT: Each step removes one pallet. Remaining loaded forklifts keep
          their pallets.
  PASS IF: Count of visible pallets decreases by 1 each step.
  FAIL SIGN: Wrong forklift unloaded, or pallet count doesn't drop.

STEP 2N+3: Final stable pause — 5s
  EXPECT: All N forklifts drive empty. No pallet visible on any fork.
  PASS IF: Console reports all forklifts unloaded, scene stable.
══════════════════════════════════════════════════════════════
"""

# ── Knobs ───────────────────────────────────────────────────────────────────
SLOT_HOLD_SEC  = 30.0
FINAL_HOLD_SEC =  5.0
SCENARIO       = "dock_queue"
SEED           = 42
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import importlib
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


def _pallet_prim(fl_prim_path: str) -> str:
    return fl_prim_path + "/carried_pallet"


def _banner(title):
    print(f"\n{'═' * 60}\n  {title}\n{'═' * 60}")


async def _hold(label: str, seconds: float):
    print(f"   ⏸  {label} — holding {seconds:.0f}s")
    steps = max(1, int(seconds * 60))
    for _ in range(steps):
        await ih.next_update()


async def _run():
    # ── STEP 0: Build scene ──────────────────────────────────────────────────
    _banner("STEP 0: Build scene (dock_queue preset)")
    if SCENARIO not in PRESETS:
        print(f"  [FAIL] unknown scenario '{SCENARIO}'")
        return

    scenario = PRESETS[SCENARIO](seed=SEED)
    await scenario.build()
    stage = scenario.stage
    assets_root = scenario.assets_root

    # Pre-spawn a carried-pallet prim as a CHILD of each forklift prim.
    # Local-frame offset (X, Y, Z) = calibrated C.PALLET_FORK_LOCAL_* values
    # so the pallet sits centred on the forks at travel height.
    # USD parent-child transform inheritance makes it follow the forklift
    # automatically with no per-frame sync required.
    pallet_paths = []
    for fl in scenario.forklifts:
        pp = _pallet_prim(fl.prim_path)
        # Local-frame offset so pallet sits on the forks.
        # Child prim inherits forklift world transform — pallet follows automatically.
        ih.spawn_asset(stage, pp, C.PALLET_USD,
                       C.PALLET_FORK_LOCAL_X,
                       C.PALLET_FORK_LOCAL_Y,
                       C.PALLET_FORK_LOCAL_Z,
                       0.0,
                       scale=C.PALLET_SCALE)
        ih.make_invisible(stage, pp)   # start UNLOADED
        pallet_paths.append(pp)
        print(f"  pallet prim spawned (hidden): {pp}")

    n = len(scenario.forklifts)
    await _hold("scene settled", 2.0)
    print(f"  [PASS] scene built, all {n} forklifts UNLOADED")

    # ── STEP 1: Start simulation — ALL UNLOADED ──────────────────────────────
    _banner("STEP 1: Start simulation — ALL UNLOADED")
    scenario.start()
    print("  [INFO] simulation started — forklifts driving patrol routes")
    await _hold(f"all {n} forklifts moving, no pallets", SLOT_HOLD_SEC)

    # ── STEPS 2 … N+1: Load forklifts one by one ─────────────────────────────
    for i, pp in enumerate(pallet_paths):
        step = i + 2
        _banner(f"STEP {step}: Load forklift {i}  ({i+1}/{n} loaded)")
        ih.make_visible(stage, pp)
        for j, p2 in enumerate(pallet_paths):
            tag = "LOADED  " if j <= i else "unloaded"
            print(f"  FL{j} {tag} — {p2}")
        await _hold(f"FL{i} carrying pallet", SLOT_HOLD_SEC)

    # ── ALL LOADED banner ─────────────────────────────────────────────────────
    all_loaded_step = n + 2
    _banner(f"STEP {all_loaded_step}: ALL LOADED — hold {SLOT_HOLD_SEC:.0f}s")
    for i, pp in enumerate(pallet_paths):
        print(f"  FL{i} LOADED — {pp}")
    await _hold(f"all {n} forklifts carrying pallets", SLOT_HOLD_SEC)

    # ── STEPS N+3 … 2N+2: Unload forklifts one by one ────────────────────────
    for i, pp in enumerate(pallet_paths):
        step = n + 3 + i
        _banner(f"STEP {step}: Unload forklift {i}  ({i+1}/{n} unloaded)")
        ih.make_invisible(stage, pp)
        for j, p2 in enumerate(pallet_paths):
            tag = "unloaded" if j <= i else "LOADED  "
            print(f"  FL{j} {tag} — {p2}")
        await _hold(f"FL{i} empty", SLOT_HOLD_SEC)

    # ── Final pause ───────────────────────────────────────────────────────────
    final_step = 2 * n + 3
    _banner(f"STEP {final_step}: Final stable scene — ALL UNLOADED")
    await _hold("final", FINAL_HOLD_SEC)
    _banner("ALL STEPS COMPLETE — review [PASS] lines above")


asyncio.ensure_future(_run())
