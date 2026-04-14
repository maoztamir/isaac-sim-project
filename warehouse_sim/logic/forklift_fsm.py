"""
Forklift FSM transition table.

evaluate_transition() is called once per forklift per physics step, BEFORE
movement. It returns the next state if a transition is valid, or None if the
forklift should stay in its current state.

Transition conditions are pure functions — they read forklift state, door
state, area occupancy, and queue slots. They never mutate anything.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .. import config as C

if TYPE_CHECKING:
    from ..models.forklift   import Forklift
    from ..models.loading_door import LoadingDoor
    from ..areas             import AreaManager
    from .queue_manager      import QueueManager


# ── Condition helpers ────────────────────────────────────────────────────────

def _arrived(fl: "Forklift") -> bool:
    """True when the forklift has reached its final waypoint and stopped.

    Requires waypoints to be depleted so a forklift blocked mid-route
    (speed=0 but still en-route) does not falsely trigger arrival.
    """
    return fl.speed < 0.05 and fl.state_timer <= 0.0 and not fl.waypoints


def _pickup_done(fl: "Forklift") -> bool:
    return fl.state_timer <= 0.0


def _loading_done(fl: "Forklift") -> bool:
    return fl.state_timer <= 0.0


# ── Transition table ─────────────────────────────────────────────────────────
# Each entry: (condition_fn, next_state)
# Evaluated in order; first match wins.

def evaluate_transition(
    fl: "Forklift",
    doors: list["LoadingDoor"],
    area_mgr: "AreaManager",
    queue_mgr: "QueueManager",
) -> str | None:
    """Return the next FSM state for *fl*, or None to keep current state."""

    state = fl.state

    # ── IDLE → PICKUP_AT_SHELVES ─────────────────────────────────────────────
    # An idle forklift with no task and no pallet should head to shelves.
    # state_timer > 0 means a stagger hold-off is in effect — stay idle.
    if state == C.STATE_IDLE:
        if fl.state_timer > 0.0:
            return None
        if fl.load == C.LOAD_UNLOADED:
            return C.STATE_PICKUP_AT_SHELVES
        # Idle but loaded: edge case — go straight to staging
        return C.STATE_MOVE_TO_STAGING

    # ── PICKUP_AT_SHELVES → MOVE_TO_STAGING ──────────────────────────────────
    # Pickup timer expired → pallet is on forks, head to staging.
    if state == C.STATE_PICKUP_AT_SHELVES:
        if _pickup_done(fl):
            return C.STATE_MOVE_TO_STAGING

    # ── MOVE_TO_STAGING → WAIT_IN_STAGING  (if staging full or dock blocked) ─
    # ── MOVE_TO_STAGING → MOVE_TO_LOADING  (if dock available) ──────────────
    if state == C.STATE_MOVE_TO_STAGING:
        if _arrived(fl):
            # Forklift must be carrying a pallet before occupying a dock slot
            any_door_open = any(d.is_open for d in doors)
            if any_door_open and fl.load == C.LOAD_LOADED:
                slot = queue_mgr.request_slot(fl.id, "dock")
                if slot:
                    return C.STATE_MOVE_TO_LOADING
            return C.STATE_WAIT_IN_STAGING

    # ── WAIT_IN_STAGING → MOVE_TO_LOADING  (when dock becomes available) ─────
    if state == C.STATE_WAIT_IN_STAGING:
        dock_available = (any(d.is_open for d in doors) and
                          queue_mgr.free_count("dock") > 0 and
                          fl.load == C.LOAD_LOADED)
        if dock_available:
            return C.STATE_MOVE_TO_LOADING

    # ── MOVE_TO_LOADING → LOADING  (arrived at dock, slot was claimed earlier) ─
    if state == C.STATE_MOVE_TO_LOADING:
        if _arrived(fl):
            slot = queue_mgr.slot_for(fl.id)
            if slot and slot.slot_type == "dock":
                return C.STATE_LOADING
            return C.STATE_WAIT_AT_DOCK_QUEUE

    # ── WAIT_AT_DOCK_QUEUE → MOVE_TO_LOADING  (slot freed) ───────────────────
    if state == C.STATE_WAIT_AT_DOCK_QUEUE:
        slot = queue_mgr.request_slot(fl.id, "dock")
        if slot:
            return C.STATE_MOVE_TO_LOADING

    # ── LOADING → RETURNING ──────────────────────────────────────────────────
    if state == C.STATE_LOADING:
        if _loading_done(fl):
            queue_mgr.release_slot(fl.id)
            return C.STATE_RETURNING

    # ── RETURNING → IDLE  (arrived back near shelves) ─────────────────────
    if state == C.STATE_RETURNING:
        if _arrived(fl):
            return C.STATE_IDLE

    return None  # no transition
