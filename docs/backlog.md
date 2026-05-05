# Warehouse Sim — Project Backlog

Tasks are ordered roughly by value / dependency. Each entry describes the
feature, the current state of the code, and the concrete implementation notes
needed to build it.

---

## 1. Isaac Sim Extension — Scenario Launcher UI

**Goal**: replace the "edit SCENARIO constant and Ctrl+Enter" workflow with a
dockable UI panel inside Isaac Sim.

**Current state**: scenarios are launched by editing `warehouse_sim/main.py`
and running it from the Script Editor.

**Implementation**

Structure — new top-level folder `warehouse_sim_ext/`:
```
warehouse_sim_ext/
  config/extension.toml      ← extension manifest
  warehouse_sim_ext/
    __init__.py               ← on_startup / on_shutdown hooks
    window.py                 ← omni.ui panel
```

`extension.toml` minimum fields:
```toml
[package]
title   = "Warehouse Sim Launcher"
version = "0.1.0"

[[python.module]]
name = "warehouse_sim_ext"

[dependencies]
"omni.ui" = {}
"omni.kit.app" = {}
```

`window.py` — `omni.ui.Window` subclass:
- `omni.ui.ComboBox` populated from `warehouse_sim.scenarios.PRESETS` keys
- `omni.ui.IntField` for seed
- **Build** button → `asyncio.ensure_future(scenario.build())`
- **Start / Stop** buttons → `scenario.start()` / `ih.stop_timeline()`
- Status label that shows the last console line (subscribe to
  `omni.kit.app.get_app().get_message_bus_event_stream()`)

Load the extension in Isaac Sim:
  `Window → Extensions → gear icon → Add path` pointing at the repo root,
  then enable "Warehouse Sim Launcher".

**Files**: new `warehouse_sim_ext/` tree (no changes to existing code).

---

## 2. Pedestrians — Per-Character Navigation Area

**Goal**: restrict each IRA pedestrian to its own floor zone so characters
don't wander into each other's areas or into forklift lanes.

**Current state**: `base._open_ira_scene()` writes a single YAML config with
`navigation_area: []` (unrestricted) and `spawn_area: []`. All N characters
share the same config, so no per-character area is possible at the YAML level.

**Implementation**

The IRA `omni.anim.people` CharacterBehavior script reads the command file
and navigates to GoTo waypoints via the navmesh. Area restriction can be
enforced two ways — use **both**:

A. **`spawn_area`** — list of `[x_min, y_min, x_max, y_max]` boxes in the
YAML tells IRA where to place each character at spawn time (avoids characters
spawning in the wrong zone before their first GoTo).

B. **`navigation_area`** per character in the command file — the `GoTo`
command already limits movement to reachable navmesh cells, so keeping
waypoints strictly inside the character's zone is sufficient in practice.

Changes:
- Add `nav_area: tuple[float,float,float,float] | None = None` field to
  `warehouse_sim/models/pedestrian.py`.
- In `base._open_ira_scene()`, collect each pedestrian's `nav_area` and emit
  per-character `spawn_area` entries in the YAML. IRA 0.7 format:
  ```yaml
  character:
    spawn_area:
      - [x_min, y_min, x_max, y_max]   # Character_00
      - [x_min, y_min, x_max, y_max]   # Character_01
  ```
  (one list item per character, in index order)
- In `mixed_floor.setup_pedestrians()` and `dock_queue_pedestrian`, set
  `ped.nav_area` from the bounding box of that pedestrian's waypoints.

**Files**: `warehouse_sim/models/pedestrian.py`, `warehouse_sim/scenarios/base.py`,
`warehouse_sim/scenarios/mixed_floor.py`, `warehouse_sim/scenarios/dock_queue_pedestrian.py`.

---

## 3. Forklifts — Fork Raise / Lower Animation

**Goal**: when a forklift picks up or drops a pallet the fork mast visibly
raises (pallet lifts off the ground) and lowers (pallet touches down).

**Current state**: `RuleEngine._handle_load_change()` calls `assign_pallet()`
and `release_pallet()` which make the carried pallet prim visible/invisible, but
the fork mast Z position is never changed — the pallet just appears/disappears.
`config.py` has the constants `FORK_RAISE_SPEED = 0.25`, `FORK_TRAVEL_HEIGHT = 0.45`,
`FORK_GROUND_HEIGHT = 0.0` and the calibrated `PALLET_FORK_LOCAL_Z = 0.194`.

**Implementation**

- Add `fork_height: float = 0.0` and `_fork_target: float = 0.0` to `Forklift`.
- In `Forklift.update()`, each tick interpolate `fork_height` toward `_fork_target`
  at `C.FORK_RAISE_SPEED` m/s and call `ih.set_fork_height(stage, prim_path, fork_height)`.
- Add `ih.set_fork_height(stage, prim_path, z)` which finds the fork-mast child prim
  (prim name contains `"fork"` or `"mast"`) and sets its translateZ op.
- In `RuleEngine._handle_load_change()`:
  - pickup complete → `fl._fork_target = C.FORK_TRAVEL_HEIGHT`
  - loading complete → `fl._fork_target = C.FORK_GROUND_HEIGHT`

To find the fork prim name: run `ih.iter_prim_descendants(stage, forklift_path)` and
print prim names — the Omniverse forklift USD has a child called `SM_Forklift_Fork`
or similar.

**Files**: `warehouse_sim/models/forklift.py`, `warehouse_sim/isaac_helpers.py`,
`warehouse_sim/logic/rule_engine.py`, `warehouse_sim/config.py`.

---

## 4. Forklifts — IRA-Animated Driver in the Cab

**Goal**: a seated human figure visible in the operator cab of each forklift,
animating in sync with forklift movement (idle when stopped, drive pose when
moving).

**Current state**: forklifts are bare USD props with no occupant.

**Implementation**

Option A — Static seated figure (simpler):
- Spawn a character USD at a fixed offset relative to the forklift prim using
  `ih.spawn_asset(stage, forklift_path + "/driver", C.IRA_CHARACTER_USD, ...)`.
  As a child prim it will ride the forklift automatically.
- Calibrate seat offset: spawn one forklift at a known world position, then
  interactively move a character prim until it sits correctly in the cab.
  Record the local-frame X/Y/Z and yaw, add as `DRIVER_LOCAL_*` constants in
  `config.py`.
- Character needs `CharacterUtil.setup_animation_graph_to_character()` called
  on it so it animates — otherwise it will be a static T-pose mesh.

Option B — IRA-driven driver (advanced):
- Register a `Pedestrian` for the driver with a single-waypoint "patrol"
  (GoTo forklift seat → Idle), then re-issue the waypoint each time the
  forklift moves to a new cell. Complex because the seat position changes
  every physics frame.
- Prefer Option A for the initial implementation.

Seat offset calibration procedure:
- Spawn forklift at `(0, 0, 0)` facing `yaw=90°`
- Manually position a character in the viewport until visually seated
- Read world transform: `ih.compute_world_bbox(stage, char_path)`
- Subtract forklift world origin → local offset
- For `yaw=90°` (heading offset = 90), local frame: `local_x = world_dy`,
  `local_y = -world_dx`, `local_z = world_dz` (same transform as pallet)

**Files**: `warehouse_sim/config.py` (seat constants), `warehouse_sim/scenarios/base.py`
(`setup_forklifts` spawns driver child prim), `warehouse_sim/isaac_helpers.py`
(possibly a `spawn_forklift_driver()` helper).

---

## 5. Dock Doors — Loading Dock with Truck Trailer Visual

**Goal**: when a dock door is open it should look like a truck is backed up to
the building — visible trailer floor, walls, and the open rear of the trailer
framing the doorway.

**Current state**: `ih.spawn_gate()` already creates a `truck_back` cube (a
flat black panel at the wall exterior, `tb_y = C.WALL_Y_MIN - 0.02`) that
becomes visible when the door opens. This represents only the rear face of the
trailer. The trailer body and interior are missing.

**Implementation**

Add a `spawn_truck_trailer(stage, idx, door_cx, C)` helper in `isaac_helpers.py`
and call it from `Scenario._spawn_loading_doors()`.

Trailer geometry (all cubes, procedural):
```
trailer_y_near = C.WALL_Y_MIN - C.HOLE_DEPTH        # back of trailer flush with hole
trailer_y_far  = trailer_y_near - 10.0               # trailer length ~10 m
trailer_floor_z = 1.2                                 # standard dock height
trailer_w  = C.OPENING_W + 0.3                        # slightly wider than door
trailer_h  = 2.8                                      # interior height
```

Prims (under `/World/DockingDoors/gate_{idx}/trailer/`):
- `floor`  — flat slab at `trailer_floor_z`, full length, truck width
- `left_wall`, `right_wall` — vertical panels along both sides
- `roof`  — horizontal panel at top
- `rear_face` — same as existing `truck_back`, now move it to `trailer_y_near`

All trailer prims hidden by default; shown/hidden together with the existing
door open/close logic by extending `open_gate()` / `close_gate()` in
`isaac_helpers.py`.

Colours: `floor` = dark grey `(0.25, 0.25, 0.25)`, walls/roof = light grey
`(0.55, 0.55, 0.55)`.

**Files**: `warehouse_sim/isaac_helpers.py` (`spawn_truck_trailer()`,
extend `open_gate()` / `close_gate()`), `warehouse_sim/scenarios/base.py`
(call `spawn_truck_trailer` in `_spawn_loading_doors()`).

---

## 6. Dock Doors — Smoother Roll-Up Animation

**Goal**: the current open/close animation hides/shows shutter panels at a
constant pace. Make it feel like a real industrial roll-up door: slow start,
accelerating through the middle, deceleration at the end.

**Current state**: `ih.open_gate_animated()` and `close_gate_animated()` in
`isaac_helpers.py` use a constant `per_step = duration / panel_n` sleep
between panels.  `C.PANEL_N = 8` slats.

**Implementation**

Replace the uniform sleep with an ease-in-out distribution:
- Use a sine easing: for panel `i` of `n`, the inter-panel delay is
  `per_step * (1 - cos(pi * i / n)) / 2` (half-sine, sums to `duration`).
- This makes the first and last panels move slowly and the middle panels move
  quickly — matches the inertia of a real rolling door.

Optionally add a slight "bounce" on close: after the last panel, call
`make_invisible(floor_seal)` briefly then `make_visible` (1-frame flicker)
to suggest the door settling onto the seal.

Code change is entirely inside `open_gate_animated()` and `close_gate_animated()`
in `isaac_helpers.py` — no callers need updating.

Key constant to add to `config.py`:
```python
DOOR_ANIM_DURATION = 1.5   # seconds — slightly longer than current 1.2 for smoothness
```

**Files**: `warehouse_sim/isaac_helpers.py`, `warehouse_sim/config.py`.
