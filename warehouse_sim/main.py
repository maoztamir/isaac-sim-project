#!/usr/bin/env python3
"""
Warehouse simulation entry point.

Run inside Isaac Sim Script Editor:
    Window > Script Editor > Open this file > Ctrl+Enter

Change SCENARIO below to switch presets:
    "dock_queue"       — forklifts queue at loading dock
    "loading_pause"    — one forklift stalls, others reroute
    "area_buildup"     — all converge on staging area
    "aisle_congestion" — forklifts funnel through one aisle
"""

# ── Select scenario here ────────────────────────────────────────────────────
SCENARIO = "dock_queue"
SEED = 42
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Force-reload all warehouse_sim modules so re-running in Script Editor
# picks up code changes without restarting Isaac Sim.
_to_remove = [k for k in sys.modules if k.startswith("warehouse_sim")]
for k in _to_remove:
    del sys.modules[k]

print(f"[main] Loading scenario: {SCENARIO}")

from warehouse_sim.scenarios import PRESETS
from warehouse_sim import config as C
print(f"[main] STAGING_CENTER_Y = {C.STAGING_CENTER_Y:.2f} (expect ~ -7.65)")


async def _run():
    if SCENARIO not in PRESETS:
        print(f"[main] Unknown scenario '{SCENARIO}'. Available: {list(PRESETS.keys())}")
        return
    scenario = PRESETS[SCENARIO](seed=SEED)
    await scenario.build()
    scenario.start()

asyncio.ensure_future(_run())
