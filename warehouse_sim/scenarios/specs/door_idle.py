"""
Spec: Door Idle While Open — WAREHOUSE_DOOR_IDLE_003.

Door 2 (gate index 1) is open with a trailer attached and two unattended
pallets near the entrance. No forklift enters the loading zone.

Background forklifts and IRA pedestrians are spawned directly by
DoorIdleScenario.setup_forklifts() / setup_pedestrians() — not from this
spec. The timeline is empty; the scene is fully FSM-free for the forklifts.
"""

SPEC = {
    "name": "door_idle",
    "description": (
        "Dock door open, two pallets near entrance — background forklifts "
        "and pedestrians ignore it. Door-idle anomaly."
    ),

    # ── Focus camera ─────────────────────────────────────────────────────────
    "focus_camera": {
        "name":    "cam_door_idle",
        "eye":     (-10.4, 2.0, 4.5),     # north of staging, gate 1 column
        "target":  (-10.4, -22.0, 0.0),   # dock entrance near floor
        "fov_deg": 60.0,
        "activate": True,
    },

    # ── Initial scene state ──────────────────────────────────────────────────
    "scene_init": {
        "doors": [
            {"index": 0, "state": "closed"},
            {"index": 1, "state": "open"},    # centre door — idle but open
            {"index": 2, "state": "closed"},
        ],

        # Forklifts spawned by DoorIdleScenario.setup_forklifts() directly.
        "forklifts": [],

        # Two pallets near the door entrance.
        "pallets": [
            {"position": "dock_service_1_left"},
            {"position": "dock_service_1"},
        ],
    },

    # No scripted timeline — background forklifts move via waypoint patrol.
    "timeline": [],
}
