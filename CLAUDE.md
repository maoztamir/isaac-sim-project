# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An Isaac Sim warehouse simulation framework. Forklifts navigate a warehouse with loading docks, staging areas, and shelf aisles using kinematic movement and FSM-based behavior. Runs inside NVIDIA Isaac Sim's Script Editor.

## Running

Open `warehouse_sim/main.py` in Isaac Sim's Script Editor (Window > Script Editor), change `SCENARIO` to one of the presets, then Ctrl+Enter. The `_project_root` path in `main.py` must match the actual checkout location.

Available scenarios: `dock_queue`, `loading_pause`, `area_buildup`, `aisle_congestion`.

There are no external build steps, linting, or test commands. Code runs entirely within Isaac Sim's embedded Python.

## Architecture

### `warehouse_sim/` — the reusable framework

- **`config.py`** — All constants: warehouse bounds, gate geometry, forklift kinematics, FSM timing, asset USD paths. Spatial values in metres, angles in degrees.
- **`isaac_helpers.py`** — Isolation layer for all `omni.*` / `pxr.*` calls. The rest of the codebase imports this instead of touching Isaac Sim APIs directly. This keeps scenario code testable and contains version-change impact.
- **`forklift.py`** — Forklift class: kinematic bicycle model + 4-state FSM (`drive`, `idle`, `loading`, `waiting`). Handles steering, speed control, shelf collision avoidance, aisle lane-snapping, and forklift-to-forklift separation.
- **`shelves.py`** — `ShelfMap`: lazily scans the warehouse USD on first physics step for shelf/rack prims by keyword matching, builds bounding-box rects, and derives aisle centre-line X coordinates from gaps between merged shelf intervals.
- **`zones.py`** — `Zone` / `ZoneManager`: axis-aligned rectangular floor areas (LoadingZone, StagingArea, ShelvesArea) with per-forklift occupancy and dwell-time tracking.
- **`waypoints.py`** — Waypoint generators: random navigable floor points, zone-targeted points, patrol routes, and zone-sequence routes. All respect shelf collision rects.
- **`scenarios/base.py`** — `Scenario` base class. Orchestrates scene construction (warehouse USD, physics, dock gates, zebra tape, staging props, zones, forklifts), subscribes to physics step, and runs per-frame update loop. Subclasses override `setup_forklifts()`, `_assign_initial_waypoints()`, and `on_step(dt)`.
- **`scenarios/`** — Each file is one scenario preset inheriting from `Scenario`.

### `generated_scenarios/` — standalone scripts

Self-contained scripts that don't use the framework. They import Isaac Sim APIs directly and inline all parameters. Used for one-off experiments or generated output.

## Key Patterns

- **Isaac API isolation**: Never import `omni.*` or `pxr.*` outside `isaac_helpers.py` (and `shelves.py` for `pxr` scan). Scenario and forklift code goes through `ih.*` helpers.
- **Lazy shelf detection**: `ShelfMap.init()` runs on the first physics step (not at build time) because the warehouse USD needs a frame to fully load.
- **Module hot-reload**: `main.py` force-deletes all `warehouse_sim` modules from `sys.modules` before import so re-running in Script Editor picks up code changes without restarting Isaac Sim.
- **Config-driven geometry**: All spatial constants live in `config.py` and are imported as `C`. Scenario code references `C.WAREHOUSE_CX`, `C.ZONES`, etc.
- **Forklift waypoint loop**: Waypoints are cyclic — `_advance_waypoint()` wraps `wp_idx` modulo the list length.

## Task Workflow (required for every implementation task)

Every task — no matter how small — must follow this four-step sequence:

### Step 1 — Plan (display before touching any code)

Write and show a task plan that covers:
- **What** files will change and why
- **How** — the specific functions, classes, or constants being added/modified
- **Dependencies** — what existing code this builds on or must not break
- **Risks** — anything that could silently fail at runtime inside Isaac Sim

Wait for user confirmation before proceeding.

### Step 2 — Implement

Make only the changes described in the approved plan. Do not add extras.

### Step 3 — Visual test script

Create or update a file in `tests/` that exercises the new code inside Isaac Sim's Script Editor. Rules:
- Script lives in `tests/`, never in `warehouse_sim/`
- Include the module hot-reload block at the top (same pattern as `main.py`)
- Use `asyncio.ensure_future(_run())` as the entry point
- Expose knobs (pause durations, gate indices, etc.) as named constants at the top of the file
- Do **not** call `scenario.start()` in visual tests — keep the scene still unless the test specifically needs movement

### Step 4 — Expected visual outcomes

For every test step in the script, document exactly what the user should observe in the Isaac Sim viewport. Format:

```
STEP <n>: <function or action>
  EXPECT: <what appears or changes in the viewport>
  PASS IF: <concrete observable criterion>
  FAIL SIGN: <what a broken result looks like>
```

Add this documentation as a comment block at the top of the test file, below the module docstring.

## Test file location and naming

| Core framework changes | `tests/test_<module>_visual.py` |
| Scenario-level changes | `tests/test_scenario_<name>_visual.py` |

## Custom Agent

The `/warehouse-scenario` command (`.claude/commands/warehouse-scenario.md`) dispatches to the `isaac-sim-warehouse-scenarios` subagent for design-first scenario generation. That agent searches existing samples before writing new code and follows a spec-then-implementation workflow.
