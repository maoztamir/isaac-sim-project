# Isaac Sim Warehouse Simulation

A scenario-driven warehouse simulation framework built on NVIDIA Isaac Sim. Forklifts navigate a warehouse with loading docks, staging areas, and shelf aisles using kinematic movement and FSM-based behaviour. Each scenario exercises a different operational condition designed to generate ground-truth data for external vision and alert systems.

---

## Requirements

- NVIDIA Isaac Sim (tested on 4.x)
- The project checked out to `/home/ubuntu/isaac_sim_samples/isaac-sim-project`
  - If you check out elsewhere, update `_project_root` at the top of `warehouse_sim/main.py`

No external Python packages are required. Everything runs inside Isaac Sim's embedded Python.

---

## Running a Scenario

### Step 1 — Open the Script Editor

In Isaac Sim: **Window → Script Editor**

### Step 2 — Open `main.py`

In the Script Editor toolbar: **File → Open**, navigate to:

```
warehouse_sim/main.py
```

### Step 3 — Select a scenario

Near the top of `main.py`, change the `SCENARIO` variable:

```python
SCENARIO = "dock_queue"   # ← change this
SEED     = 42             # ← change for a different random layout
```

Available values: `dock_queue`, `loading_pause`, `area_buildup`, `aisle_congestion`

### Step 4 — Run

Press **Ctrl+Enter** (or click the Run button).

The simulation builds the scene, spawns forklifts, and starts automatically. Console output and a copy of all logs are written to `tests/output/main.log`.

### Step 5 — Stop

Press **Stop** in the Isaac Sim timeline toolbar. To re-run (with or without code changes), press **Ctrl+Enter** again — the module hot-reload block at the top of `main.py` picks up any edits without restarting Isaac Sim.

---

## Scenarios

### `dock_queue`

**What it shows:** Queue formation at the loading dock.

Four forklifts cycle through the full route — shelves → staging → dock → back to shelves. Loading at the dock takes **20 seconds**, which is long enough that a second forklift arrives before the first has finished. A queue builds up in the staging area, and the dock-capacity bottleneck is detected and logged.

**What to watch for in the viewport:**
- Forklifts stacking up in the staging lane
- One forklift stationary at the dock for ~20 s while others wait

**Key lever:** `loading_duration = 20.0` in `warehouse_sim/scenarios/dock_queue.py`

---

### `loading_pause`

**What it shows:** Door-closure event and its downstream effect on flow.

Three forklifts cycle normally for the first 30 seconds. At **T = 30 s** all three loading dock doors close simultaneously (shutters lower, black truck-back patch hides). The FSM condition `any door open` becomes False, so no forklift can advance from staging to loading — they queue up in staging. At **T = 50 s** the doors reopen and flow resumes.

**What to watch for in the viewport:**
- Shutter panels visible on the dock doors at T = 30 s
- Forklifts holding in the staging area during the pause
- Movement resuming once doors reopen at T = 50 s

**Key levers** (top of `warehouse_sim/scenarios/loading_pause.py`):
```python
PAUSE_AT_SEC   = 30.0
PAUSE_DURATION = 20.0
```

---

### `area_buildup`

**What it shows:** Staging area congestion caused by slow dock release.

Five forklifts all cycle through the same route. Loading takes **12 seconds** and dock capacity is 1, so forklifts arrive in staging faster than they are released to the dock. Staging fills up, dwell-time warnings are printed when a forklift has been waiting more than 15 s, and buildup-threshold events are logged by the monitoring layer.

**What to watch for in the viewport:**
- Three or more forklifts holding in the staging lane simultaneously
- Console output: `FL{n} in StagingArea for {t}s — build-up`

**Key lever:** `loading_duration = 12.0` in `warehouse_sim/scenarios/area_buildup.py`

---

### `aisle_congestion`

**What it shows:** Multiple forklifts sharing a narrow shelf aisle.

Six forklifts are spawned clustered near the centre-aisle X coordinate (~−10.45 m). Because the rule engine assigns each forklift the pickup point at its nearest aisle, most forklifts are directed to the same corridor. The scenario logs whenever two or more forklifts are simultaneously in the shelf area.

**What to watch for in the viewport:**
- Forklifts queuing at the entrance to the middle aisle
- Console output: `{n} forklifts in shelf area (congestion active)` every 10 s

**Key lever:** spawning cluster in `warehouse_sim/scenarios/aisle_congestion.py` → `setup_forklifts()`

---

## Output files

Every run writes to `tests/output/`:

| File | Contents |
|---|---|
| `main.log` | Full console output for the run |
| `metrics_<timestamp>.csv` | Per-area snapshots: forklift count, avg speed, dwell, peak occupancy — one row per area per second |
| `events_<timestamp>.json` | All typed events: door open/close, queue formed, buildup threshold, proximity alert, idle alert, pallet transfer |

---

## Appendix: Adding a New Scenario

### Option A — Python subclass (full control)

This is the right choice when you need custom waypoint geometry, coordinated multi-forklift logic, or anything not expressible as simple timing.

#### 1. Create `warehouse_sim/scenarios/my_scenario.py`

```python
from __future__ import annotations
from .base import Scenario
from .. import config as C

class MyScenario(Scenario):
    name = "my_scenario"
    num_forklifts = 4

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = 10.0   # seconds at dock per cycle

    def _assign_initial_waypoints(self):
        """Called once on the first physics step, after ShelfMap is ready."""
        # Open the doors you want active
        self.open_all_doors()            # or: self.doors[1].open(self.stage)

        # Optionally force a forklift into a specific starting state:
        # self.forklifts[0].state = C.STATE_WAIT_IN_STAGING

    def on_step(self, dt: float):
        """Per-frame hook — fires every physics step after movement."""
        # Example: close a door at T=20 s
        if abs(self.sim_time - 20.0) < dt:
            self.doors[1].close(self.stage)
            self.evt_log.log_door_close(self.sim_time, gate_idx=1)
```

**What the base class handles for you (don't re-implement these):**
- Scene construction (warehouse USD, physics, gates, floor markings)
- Forklift spawning at default grid positions
- FSM transitions via the rule engine (idle → pickup → staging → loading → return)
- Area occupancy tracking
- Proximity, idle, buildup, and queue event logging
- Metrics CSV / JSON writing
- Telemetry every 10 s

**Override points:**

| Method | When to override |
|---|---|
| `num_forklifts` | Change how many forklifts spawn |
| `loading_duration` | Change how long loading takes |
| `pickup_duration` | Change how long shelf pickup takes |
| `_assign_initial_waypoints()` | Open/close doors at start; force initial FSM states |
| `on_step(dt)` | Timed events (door close, print, log) |
| `setup_forklifts()` | Custom spawn positions (rarely needed) |

#### 2. Register it in `warehouse_sim/scenarios/__init__.py`

```python
from .my_scenario import MyScenario

PRESETS = {
    ...
    "my_scenario": MyScenario,
}
```

#### 3. Select it in `main.py`

```python
SCENARIO = "my_scenario"
```

---

### Option B — Dict entry only (coming in Task 11)

A `ConfigScenario` mechanism is planned that lets you define a scenario entirely as a Python dict in `warehouse_sim/config.py` — no subclass needed. Supported levers will include forklift count, loading/pickup timing, door open/close schedules, idle forklift IDs, and threshold overrides. Until that is implemented, use Option A.

---

## Project structure

```
warehouse_sim/
├── main.py                    # Entry point — set SCENARIO here
├── config.py                  # All constants and scenario preset levers
├── isaac_helpers.py           # Isolation layer for all omni.* / pxr.* calls
├── shelves.py                 # Shelf detection and aisle computation
├── areas.py                   # Area definitions and occupancy tracking
├── waypoints.py               # Waypoint generators (deterministic + random)
├── models/
│   ├── forklift.py            # Forklift: 8-state FSM + kinematic model
│   ├── loading_door.py        # LoadingDoor: open/close with visual update
│   ├── pallet.py              # Pallet: location + assigned forklift
│   └── queue_slot.py          # QueueSlot: dock / staging-hold slot
├── logic/
│   ├── forklift_fsm.py        # FSM transition table
│   ├── rule_engine.py         # Per-step orchestrator
│   ├── queue_manager.py       # Slot assignment / release
│   └── pallet_flow.py        # Pallet pickup / deposit
├── monitoring/
│   ├── zone_monitor.py        # Per-area metric snapshots
│   ├── event_logger.py        # Typed event log
│   └── metrics_writer.py      # CSV / JSON output
└── scenarios/
    ├── base.py                # Scenario base class
    ├── dock_queue.py
    ├── loading_pause.py
    ├── area_buildup.py
    └── aisle_congestion.py

tests/
├── test_*_visual.py           # Per-module visual tests (run in Script Editor)
└── output/                    # Runtime logs and metrics output
```
