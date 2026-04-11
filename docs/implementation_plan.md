# Implementation Plan: Object-State-Driven Warehouse Scenarios

## Context

The design docs (`Isaac_Sim_5_1_Warehouse_Design_Plan.docx` and `Isaac_Sim_5_1_Claude_Code_Execution_Plan.docx`) define a new architecture: **objects hold state, rules drive behavior, areas measure outcomes**. One reusable scene, multiple scenarios via state and timing changes.

The current codebase has useful pieces (kinematic model, Isaac adapter, area tracking, shelf detection) but the control layer needs restructuring: richer forklift FSM, explicit object models (LoadingDoor, Pallet, QueueSlot), a rule engine, deterministic waypoints, and a monitoring/metrics layer.

### Naming: "Area" not "Zone"

Use "area" terminology throughout (LoadingArea, StagingArea, ShelvesArea). The internal class can stay `Zone`/`ZoneManager` as implementation, but all user-facing names, prim paths, and config keys use "Area".

### Shelves Area has no capacity state

The ShelvesArea does not need a capacity limit or blocked state — forklifts freely enter shelves. Only LoadingArea and StagingArea have capacity/blocking logic.

### Loading door visual: shutter open/close

The gate already has the prims for this (in `isaac_helpers.py:spawn_gate()`):
- **Shutter panels** at `/World/DockingDoors/gate_{idx}/shutter/panel_*` + `floor_seal`
- **Black truck-back patch** at `/World/DockingDoors/gate_{idx}/shutter_open` (hidden by default)

**Door open** = hide shutter panels + floor seal, show `shutter_open` (black background simulating connected truck)
**Door closed** = show shutter panels + floor seal, hide `shutter_open`

Need to add `make_visible(stage, prim_path)` to `isaac_helpers.py` (only `make_invisible` exists currently).

## What to KEEP vs REPLACE

| Current file | Decision |
|---|---|
| `isaac_helpers.py` | KEEP + extend (add make_visible, scan_shelves wrapper, door open/close helpers) |
| `config.py` | KEEP + extend (add area capacities, waypoint maps, thresholds, scenario presets) |
| `forklift.py` | KEEP kinematics (lines 160-214), REPLACE FSM |
| `zones.py` | EXTEND (add capacity, is_blocked, pallet_count, transition counters) |
| `shelves.py` | KEEP logic, move pxr code to isaac_helpers |
| `waypoints.py` | REPLACE (random → explicit waypoint maps) |
| `scenarios/*.py` | REPLACE all (state-driven presets) |

## New architecture

```
warehouse_sim/
├── config.py                  # EXTEND
├── isaac_helpers.py           # EXTEND
├── shelves.py                 # REFACTOR (remove pxr imports)
├── zones.py                   # EXTEND
├── waypoints.py               # REPLACE
├── models/
│   ├── __init__.py
│   ├── loading_door.py        # LoadingDoor(is_open) — controls dock access + visual state
│   ├── forklift.py            # Forklift: 8-state FSM + kinematics (migrated)
│   ├── pallet.py              # Pallet(location, assigned_forklift_id)
│   └── queue_slot.py          # QueueSlot(occupied_by, slot_type) — dock/staging
├── logic/
│   ├── __init__.py
│   ├── forklift_fsm.py        # Transition table for 8 states
│   ├── rule_engine.py         # Central rules (door→dock, capacity→queue, pallet consistency)
│   ├── queue_manager.py       # Deterministic slot assignment/release
│   └── pallet_flow.py         # Pallet-forklift handoff + consistency
├── monitoring/
│   ├── __init__.py
│   ├── zone_monitor.py        # Per-area metrics snapshots
│   ├── event_logger.py        # Typed events (door, queue, proximity, idle, etc.)
│   └── metrics_writer.py      # CSV/JSON dump
├── scenarios/
│   ├── __init__.py
│   ├── base.py                # Async build + rule engine tick loop
│   ├── dock_queue.py
│   ├── loading_pause.py
│   ├── area_buildup.py
│   ├── aisle_congestion.py
│   ├── vehicle_idle.py        # NEW
│   └── safety_proximity.py    # NEW
└── main.py
```

## Implementation steps

### Step 1: isaac_helpers.py — add door visual helpers

- Add `make_visible(stage, prim_path)` using `UsdGeom.Imageable(prim).MakeVisible()`
- Add `open_gate(stage, gate_idx)`: hide shutter panels + floor seal, show `shutter_open`
- Add `close_gate(stage, gate_idx)`: show shutter panels + floor seal, hide `shutter_open`
- Add `scan_shelves_for_rects(stage, keywords, ...)` wrapper (move pxr code from shelves.py)

### Step 2: config.py — extend with new constants

- **Forklift 8-state ladder**: `STATE_IDLE, STATE_PICKUP_AT_SHELVES, STATE_MOVE_TO_STAGING, STATE_WAIT_IN_STAGING, STATE_MOVE_TO_LOADING, STATE_WAIT_AT_DOCK_QUEUE, STATE_LOADING, STATE_RETURNING`
- **Area capacities**: `LOADING_AREA_CAPACITY = 1`, `STAGING_AREA_CAPACITY = 6` (no shelves capacity)
- **Detection thresholds**: `QUEUE_SUSTAINED_SECS = 15.0`, `IDLE_WARN_SECS = 20.0`, `NEAR_MISS_DIST = 2.5`, `NEAR_MISS_SPEED_MIN = 0.5`, `CONGESTION_SPEED_RATIO = 0.3`
- **Scenario presets**: dict per scenario with lever values

### Step 3: zones.py — extend Zone class

- Add `capacity: int | None` and `is_blocked: bool` to `__init__`
- Add `pallet_count: int`
- Add `_entry_count`, `_exit_count` — incremented in `update_occupant()`
- Add `is_full` property
- No capacity for ShelvesArea (pass `capacity=None`)

### Step 4: models/ — object-state data classes

**`models/loading_door.py`**
- `LoadingDoor(gate_idx, is_open=False)`
- `open(stage)` → calls `ih.open_gate()`, sets `self.is_open = True`
- `close(stage)` → calls `ih.close_gate()`, sets `self.is_open = False`

**`models/pallet.py`**
- `Pallet(id, location, assigned_forklift_id)`

**`models/queue_slot.py`**
- `QueueSlot(slot_id, position, slot_type, occupied_by)`
- Types: `"dock"`, `"staging_hold"`

**`models/forklift.py`** — migrate from current `forklift.py`
- KEEP kinematic model (steering, speed, collision avoidance, wall clamp, shelf push-out)
- Replace 4-state FSM with 8-state ladder
- Add: `has_pallet`, `assigned_task`, `current_zone`
- Movement stays here; state *decisions* move to rule engine

### Step 5: waypoints.py — explicit maps

- `get_pickup_points(shelf_map)` — one per aisle at shelf entrance Y
- `get_staging_hold_positions()` — fixed grid in staging area
- `get_dock_queue_spots()` — near each gate, ordered
- `get_dock_service_position(gate_idx)` — service point at gate
- `get_return_path(gate_idx, shelf_map)` — route back to shelves

### Step 6: logic/ — rule engine + state machine

**`logic/forklift_fsm.py`**
- Transition table: `{state: [(condition_fn, next_state), ...]}`
- `evaluate_transition(forklift, door, areas, queue_mgr) -> new_state | None`

**`logic/rule_engine.py`**
- Per physics step, before movement:
  - Door closed → no LOADING transition
  - Dock slot occupied → queue or wait in staging
  - Staging full → upstream waits
  - Has pallet + legal downstream → may advance
  - Pallet/forklift location must agree

**`logic/queue_manager.py`**
- Owns QueueSlot list
- `request_slot(fl_id, slot_type) -> QueueSlot | None`
- `release_slot(fl_id)`

**`logic/pallet_flow.py`**
- `assign_pallet(forklift, pallet)` / `release_pallet(forklift, pallet)`
- Consistency validation

### Step 7: monitoring/ — metrics and events

**`monitoring/zone_monitor.py`**
- Per-area: forklift_count, pallet_count, avg_speed, occupancy_over_time, dwell, transitions

**`monitoring/event_logger.py`**
- Events: `door_open/close`, `queue_formed`, `buildup_threshold`, `state_hold_too_long`, `pallet_transfer`, `proximity_alert`, `idle_alert`

**`monitoring/metrics_writer.py`**
- CSV/JSON periodic dump

### Step 8: scenarios/base.py — rewrite

- `async build()`: scene construction + instantiate models (doors, pallets, queue slots)
- Instantiate rule_engine, queue_manager, monitoring
- `_on_physics_step()` flow:
  1. Rule engine evaluates transitions
  2. Forklifts execute movement
  3. Area occupancy update
  4. Monitoring tick
  5. Scenario `on_step()`

### Step 9: scenario presets — state-driven

Each scenario is thin: sets object states + timing, no custom movement logic.

| Scenario | Primary levers |
|---|---|
| `dock_queue` | Long loading_duration, dock capacity=1, fast arrivals |
| `loading_pause` | At time T: `door.close(stage)` → forklifts stop advancing, queues form |
| `area_buildup` | Staging outflow < inflow (slower release timing) |
| `aisle_congestion` | Multiple forklifts routed through same aisle, low speed |
| `vehicle_idle` | Remove tasks from 1-2 forklifts (no assigned_task) |
| `safety_proximity` | Crossing paths, distance threshold monitoring |

### Step 10: Clean up

- Delete old `warehouse_sim/forklift.py` (migrated to `models/forklift.py`)
- Update `shelves.py` to remove pxr imports, use `ih.scan_shelves_for_rects()`
- Update `scenarios/__init__.py` with all 6 PRESETS

## Files summary

| File | Action |
|------|--------|
| `warehouse_sim/config.py` | Extend |
| `warehouse_sim/isaac_helpers.py` | Extend (make_visible, open/close_gate, scan_shelves) |
| `warehouse_sim/shelves.py` | Refactor imports |
| `warehouse_sim/zones.py` | Extend (capacity, blocked, counters) |
| `warehouse_sim/waypoints.py` | Replace |
| `warehouse_sim/forklift.py` | Delete (migrated) |
| `warehouse_sim/models/*.py` | New (4 files) |
| `warehouse_sim/logic/*.py` | New (4 files) |
| `warehouse_sim/monitoring/*.py` | New (3 files) |
| `warehouse_sim/scenarios/base.py` | Rewrite |
| `warehouse_sim/scenarios/dock_queue.py` | Rewrite |
| `warehouse_sim/scenarios/loading_pause.py` | Rewrite |
| `warehouse_sim/scenarios/area_buildup.py` | Rewrite |
| `warehouse_sim/scenarios/aisle_congestion.py` | Rewrite |
| `warehouse_sim/scenarios/vehicle_idle.py` | New |
| `warehouse_sim/scenarios/safety_proximity.py` | New |
| `warehouse_sim/scenarios/__init__.py` | Update |

### Step 11: Aisle navigation — fix forklift entry into shelf corridors

The waypoint-skip loop in `_tick_drive` uses `margin=1.5` which bleeds into narrow
aisle corridors (< 3 m wide) and causes aisle waypoints to be skipped, so forklifts
never enter the shelves.

- Reduce waypoint-skip margin from `1.5` to `C.FORKLIFT_BODY_HALF` in both
  `warehouse_sim/forklift.py` and `warehouse_sim/models/forklift.py`
- Verify `AISLE_HALF_WIDTH = 0.1` hard-clamp keeps forklifts on centreline
- Run `main.py` (dock_queue) and confirm forklifts visibly enter and exit aisles
- Update `tests/test_shelf_detection_visual.py` expected outcomes if needed

## Verification

1. Run each scenario in Script Editor — change `SCENARIO` in `main.py`
2. Verify per scenario:
   - `dock_queue`: queue forms at dock, peak queue size logged, bottleneck door identified
   - `loading_pause`: door closes visually (shutters appear, black truck-back hidden), forklifts stop advancing
   - `area_buildup`: staging fills up, dwell warnings fire, flow imbalance detected
   - `aisle_congestion`: density + speed drop logged for target aisle
   - `vehicle_idle`: idle forklift detected in non-designated area after threshold
   - `safety_proximity`: near-miss events logged with distances, positions, speeds
3. Confirm one scene — scenarios only change state/timing, not geometry
4. Confirm door open/close is visually correct (shutters hide/show, black background toggles)
5. Check metrics output (console + CSV/JSON if enabled)
