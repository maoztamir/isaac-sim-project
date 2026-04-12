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
import os
import sys

_project_root = "/home/ubuntu/isaac_sim_samples/isaac-sim-project"

# ── Output log ───────────────────────────────────────────────────────────────
_output_dir = os.path.join(_project_root, "tests", "output")
os.makedirs(_output_dir, exist_ok=True)
_log_path = os.path.join(_output_dir, "main.log")

class _Tee:
    def __init__(self, stream, path):
        self._stream = stream
        self._file   = open(path, "w", buffering=1)
    def write(self, data):
        self._stream.write(data)
        self._file.write(data)
    def flush(self):
        self._stream.flush()
        self._file.flush()
    def __getattr__(self, name):
        return getattr(self._stream, name)

sys.stdout = _Tee(sys.stdout, _log_path)
sys.stderr = _Tee(sys.stderr, _log_path)
print(f"[main] logging to {_log_path}")

# Evict any sys.path entry that exposes a conflicting `warehouse_sim` sibling
# — either a directory OR a single-file `warehouse_sim.py` module that would
# be loaded instead of our package.
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
    print(f"[main] evicted conflicting sys.path entry: {p}")

if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

# Force-reload all warehouse_sim modules so re-running in Script Editor
# picks up code changes without restarting Isaac Sim.
_to_remove = [k for k in sys.modules if k.startswith("warehouse_sim")]
for k in _to_remove:
    del sys.modules[k]

# Drop any None-valued `warehouse_sim*` entries (negative import cache from
# earlier broken runs in the persistent Script Editor interpreter).
for k in list(sys.modules):
    if k.startswith("warehouse_sim") and sys.modules.get(k) is None:
        sys.modules.pop(k, None)

import importlib
importlib.invalidate_caches()

print(f"[main] Loading scenario: {SCENARIO}")

import warehouse_sim
print(f"[main] warehouse_sim loaded from: {warehouse_sim.__file__}")

from warehouse_sim.scenarios import PRESETS, get_scenario_class
from warehouse_sim import config as C
_preset_names = list(PRESETS.keys())
_config_names = list(C.CONFIG_SCENARIOS.keys())
print(f"[main] Preset scenarios:  {_preset_names}")
print(f"[main] Config scenarios:  {_config_names}")
print(f"[main] STAGING_CENTER_Y = {C.STAGING_CENTER_Y:.2f} (expect ~ -7.65)")


async def _run():
    try:
        cls = get_scenario_class(SCENARIO)
    except KeyError as e:
        print(f"[main] {e}")
        return
    print(f"[main] Instantiating {cls.__name__} ...")
    scenario = cls(seed=SEED)
    await scenario.build()
    scenario.start()

asyncio.ensure_future(_run())
