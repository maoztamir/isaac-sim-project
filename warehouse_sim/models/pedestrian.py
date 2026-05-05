"""
Pedestrian: thin data class for an IRA-animated character.

Movement is driven by omni.anim.people's CharacterBehavior script via
isaacsim.replicator.agent.core — no per-frame kinematic update.

Waypoints stored here are serialised to an IRA command file by
isaac_helpers.generate_ira_command_file() before playback starts.
"""

from __future__ import annotations

STATE_WALKING = "walking"
STATE_IDLE    = "idle"
STATE_STOPPED = "stopped"


class Pedestrian:
    """Handle for one IRA-animated character prim."""

    def __init__(self, ped_id: int, prim_path: str, character_name: str):
        self.id             = ped_id
        self.prim_path      = prim_path
        self.character_name = character_name
        self.state          = STATE_WALKING
        self.waypoints: list[tuple[float, float]] = []
        self.loop           = True

    # ── Stubbed state transitions (IRA command injection — future work) ───────

    def stop(self) -> None:
        self.state = STATE_STOPPED

    def resume(self) -> None:
        self.state = STATE_WALKING

    # ── No-op update — IRA CharacterBehavior script drives movement ──────────

    def update(self, dt: float, stage) -> None:
        pass

    def __repr__(self) -> str:
        return (f"Pedestrian(id={self.id}, name={self.character_name}, "
                f"state={self.state}, wps={len(self.waypoints)})")
