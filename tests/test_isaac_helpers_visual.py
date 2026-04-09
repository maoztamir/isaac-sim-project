#!/usr/bin/env python3
"""
Visual test runner for new isaac_helpers functions (Task #1).

Lives OUTSIDE warehouse_sim/ so you can edit it freely without touching core code.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Each step pauses for STEP_PAUSE seconds so you can watch the viewport.
Tweak the TESTS list at the bottom to run a subset, or change STEP_PAUSE.

Tests exercised:
    - close_gate / open_gate (per-gate + all gates)
    - make_visible / make_invisible
    - scan_shelves_for_rects (prints rect count + first few rects)
"""

# ── Tweakable knobs ─────────────────────────────────────────────────────────
STEP_PAUSE    = 3.0    # seconds between visual steps
GATE_ANIM_SEC = 2.5    # duration of gate open/close animation
OPEN_HOLD_SEC = 60.0   # how long to hold a gate open before closing it back
BUILD_SCENE   = True  # set False to reuse an already-built scene
SCENARIO      = "dock_queue"  # any preset in warehouse_sim.scenarios.PRESETS
SEED          = 42
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"
if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

# Force-reload warehouse_sim so edits to core code take effect on re-run.
_to_remove = [k for k in sys.modules if k.startswith("warehouse_sim")]
for k in _to_remove:
    del sys.modules[k]

from warehouse_sim import config as C
from warehouse_sim import isaac_helpers as ih
from warehouse_sim.scenarios import PRESETS


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _pause(label: str, seconds: float = None):
    """Print a banner and hold for `seconds` while yielding the event loop."""
    s = STEP_PAUSE if seconds is None else seconds
    print(f"\n── {label} ── (pausing {s:.1f}s)")
    # Yield multiple updates so the viewport actually refreshes.
    t = 0.0
    step = 1.0 / 60.0
    while t < s:
        await ih.next_update()
        t += step


def _banner(title: str):
    line = "═" * 60
    print(f"\n{line}\n  {title}\n{line}")


# ── Individual tests ────────────────────────────────────────────────────────

async def test_close_then_open_single_gate(stage, gate_idx: int = 0):
    _banner(f"TEST: open → hold → close gate {gate_idx}")

    print(f"  → ih.close_gate(stage, {gate_idx}, {C.PANEL_N})  [ensure closed]")
    ih.close_gate(stage, gate_idx, C.PANEL_N)
    await _pause(f"gate {gate_idx} CLOSED")

    print(f"  → ih.open_gate(stage, {gate_idx}, {C.PANEL_N})")
    ih.open_gate(stage, gate_idx, C.PANEL_N)
    await _pause(f"gate {gate_idx} OPEN — holding for {OPEN_HOLD_SEC:.0f}s", seconds=OPEN_HOLD_SEC)

    print(f"  → ih.close_gate(stage, {gate_idx}, {C.PANEL_N})")
    ih.close_gate(stage, gate_idx, C.PANEL_N)
    await _pause(f"gate {gate_idx} CLOSED")


async def test_toggle_all_gates(stage):
    _banner("TEST: cycle each gate one at a time (open → hold → close)")
    n_gates = len(C.GATE_OFFSETS)

    for idx in range(n_gates):
        print(f"  → open gate {idx}")
        ih.open_gate(stage, idx, C.PANEL_N)
        await _pause(f"gate {idx} OPEN — holding for {OPEN_HOLD_SEC:.0f}s", seconds=OPEN_HOLD_SEC)

        print(f"  → close gate {idx}")
        ih.close_gate(stage, idx, C.PANEL_N)
        await _pause(f"gate {idx} CLOSED", seconds=STEP_PAUSE)


async def test_make_visible_invisible(stage):
    _banner("TEST: make_invisible → make_visible (truck_back of gate 1)")
    # Pick a prim that's visible by default
    path = "/World/DockingDoors/gate_1/truck_back"

    print(f"  → ih.make_invisible(stage, {path})")
    ih.make_invisible(stage, path)
    await _pause("truck_back HIDDEN (look behind gate 1's shutter)")

    print(f"  → ih.make_visible(stage, {path})")
    ih.make_visible(stage, path)
    await _pause("truck_back VISIBLE again")


async def test_scan_shelves(stage):
    _banner("TEST: scan_shelves_for_rects")
    rects = ih.scan_shelves_for_rects(stage, C.SHELF_KEYWORDS)
    print(f"  rect count = {len(rects)}")
    for i, r in enumerate(rects[:5]):
        xmin, xmax, ymin, ymax = r
        print(f"  rect[{i}]: x[{xmin:7.2f},{xmax:7.2f}]  y[{ymin:7.2f},{ymax:7.2f}]"
              f"  w={xmax-xmin:5.2f} d={ymax-ymin:5.2f}")
    if len(rects) > 5:
        print(f"  ... and {len(rects) - 5} more")
    if len(rects) == 0:
        print("  ⚠  NO SHELF RECTS FOUND — check SHELF_KEYWORDS or scene build")
    else:
        print(f"  ✓  shelf scan returned {len(rects)} rects")
    await _pause("(shelf scan has no visual; see printout above)")


# ── Test registry (edit this to enable/disable tests) ───────────────────────

TESTS = [
    ("close→open gate 0",  test_close_then_open_single_gate),
    ("toggle all gates",   test_toggle_all_gates),
    ("make_visible/inv.",  test_make_visible_invisible),
    ("scan shelves",       test_scan_shelves),
]


# ── Runner ──────────────────────────────────────────────────────────────────

async def _build_scene_if_needed():
    if not BUILD_SCENE:
        print("[test] BUILD_SCENE=False — using existing stage.")
        return ih.get_stage()

    if SCENARIO not in PRESETS:
        raise RuntimeError(f"Unknown SCENARIO '{SCENARIO}'. "
                           f"Available: {list(PRESETS.keys())}")

    print(f"[test] Building scenario '{SCENARIO}' (this takes a few seconds)...")
    scenario = PRESETS[SCENARIO](seed=SEED)
    await scenario.build()
    # Do NOT call scenario.start() — we want a still scene, not moving forklifts.
    print("[test] Scene built. Letting viewport settle...")
    await _pause("scene settled", seconds=1.5)
    return scenario.stage


async def _run():
    try:
        stage = await _build_scene_if_needed()
        if stage is None:
            print("[test] ERROR: no stage available. Abort.")
            return

        _banner(f"Running {len(TESTS)} visual tests")
        for name, fn in TESTS:
            try:
                # Tests that only need `stage` — dispatch by arg count
                await fn(stage)
            except Exception as exc:
                print(f"[test] ✗ {name} raised: {exc!r}")
                import traceback
                traceback.print_exc()
            else:
                print(f"[test] ✓ {name} done")

        _banner("ALL TESTS COMPLETE")
    except Exception as exc:
        print(f"[test] FATAL: {exc!r}")
        import traceback
        traceback.print_exc()


asyncio.ensure_future(_run())
