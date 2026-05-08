"""
Spec: Dock Queue Forming.

Camera focuses on the centre door (label "2").  FL0 is mid-loading at this
dock with one pallet beside it in the loading zone.  FL1 arrives from the
LEFT staging area (door label "1") in the first 2 s and stops in the queue.
Nothing moves between 2-6 s except FL0's micro-adjustments.  At 6-8 s FL2
drives south from the centre staging area heading for door "2"'s loading
zone, but stops at the back of the queue (3 m behind FL1) — completing
the three-deep queue.
"""

SPEC = {
    "name": "dock_queue_forming",
    "description": (
        "One forklift loading at the centre dock; two more arriving from the "
        "side staging areas in succession. Demonstrates a dock queue forming."
    ),

    # ── Focus camera (scenario-specific) ────────────────────────────────────
    "focus_camera": {
        "name":     "cam_dock_queue",
        "eye":      (-10.4, 5.0, 6.0),       # inside warehouse, north of staging
        "target":   (-10.4, -22.0, 0.5),     # centre door loading zone, near floor
        "fov_deg":  65.0,                    # wide enough to see both side staging areas
        "activate": True,
    },

    # ── Initial scene state ─────────────────────────────────────────────────
    "scene_init": {
        "doors": [
            {"index": 0, "state": "closed"},
            {"index": 1, "state": "open"},     # centre door — FL0's dock + queue
            {"index": 2, "state": "closed"},
        ],

        "forklifts": [
            # FL0: parked mid-loading at the centre dock, facing south into
            # the door.  state_timer kept large so the FSM never "completes"
            # its load cycle during the 8 s window.
            {"id": "FL0",
             "position": "dock_service_1",
             "state": "loading",
             "load":  "loaded",
             "heading_deg": 0.0,              # facing south (toward door)
             "state_timer": 999.0},

            # FL1: starts in the LEFT staging area (door label "1").  Will
            # drive south-east to the centre dock queue spot during phase 1.
            {"id": "FL1",
             "position": "staging_hold_0",
             "state": "idle",
             "load":  "loaded",
             "heading_deg": 45.0,             # facing south-east
             "state_timer": 999.0},

            # FL2: starts in the CENTRE staging area (door label "2").  Will
            # drive south to the centre loading zone during phase 3.
            {"id": "FL2",
             "position": "staging_hold_1",
             "state": "idle",
             "load":  "loaded",
             "heading_deg": 0.0,              # facing south (toward dock)
             "state_timer": 999.0},
        ],

        # Single pallet sitting in the centre door's loading zone, offset to
        # the left of FL0 so it doesn't visually overlap with the forklift.
        "pallets": [
            {"position": "dock_service_1_left"},
        ],
    },

    # ── Timeline ────────────────────────────────────────────────────────────
    "timeline": [
        {
            "phase":   "arrive_fl1",
            "t_start": 0.0,
            "t_end":   2.0,
            "actors": {
                "FL0": {"action": "hold"},
                "FL1": {"action": "approach_and_stop",
                        "target": "dock_queue_1"},
                "FL2": {"action": "hold"},
            },
        },
        {
            "phase":   "micro_adjust",
            "t_start": 2.0,
            "t_end":   6.0,
            "actors": {
                "FL0": {"action": "micro_adjust",
                        "amplitude_m": 0.3,
                        "period_s":    2.0},
                "FL1": {"action": "hold"},
                "FL2": {"action": "hold"},
            },
        },
        {
            "phase":   "arrive_fl2",
            "t_start": 6.0,
            "t_end":   8.0,
            "actors": {
                "FL0": {"action": "micro_adjust",
                        "amplitude_m": 0.3,
                        "period_s":    2.0},
                "FL1": {"action": "hold"},
                "FL2": {"action": "approach_and_stop",
                        "target": "dock_queue_back_1"},
            },
        },
    ],
}
