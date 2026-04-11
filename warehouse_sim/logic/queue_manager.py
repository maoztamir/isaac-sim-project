"""
QueueManager: deterministic slot assignment for dock and staging-hold positions.

One QueueManager is owned by the Scenario. It holds QueueSlot objects built
from config waypoints and hands them out to forklifts first-come/first-served.
Slots are released when a forklift transitions out of the waiting state.
"""

from __future__ import annotations

from ..models.queue_slot import QueueSlot, SLOT_DOCK, SLOT_STAGING_HOLD
from .. import config as C
from .. import waypoints as wp
from ..shelves import ShelfMap


class QueueManager:
    """Manages dock-queue and staging-hold slots."""

    def __init__(self, shelf_map: ShelfMap):
        self._slots: list[QueueSlot] = []
        self._build_slots(shelf_map)

    # ── Setup ────────────────────────────────────────────────────────────────

    def _build_slots(self, shelf_map: ShelfMap) -> None:
        dock_spots    = wp.get_dock_queue_spots()
        staging_spots = wp.get_staging_hold_positions()

        for i, pos in enumerate(dock_spots):
            self._slots.append(QueueSlot(i, pos, SLOT_DOCK))

        for i, pos in enumerate(staging_spots):
            self._slots.append(
                QueueSlot(len(dock_spots) + i, pos, SLOT_STAGING_HOLD)
            )

    # ── Queries ──────────────────────────────────────────────────────────────

    def slots_of_type(self, slot_type: str) -> list[QueueSlot]:
        return [s for s in self._slots if s.slot_type == slot_type]

    def slot_for(self, forklift_id: int) -> QueueSlot | None:
        """Return the slot currently held by this forklift, or None."""
        for s in self._slots:
            if s.occupied_by == forklift_id:
                return s
        return None

    def free_count(self, slot_type: str) -> int:
        return sum(1 for s in self._slots
                   if s.slot_type == slot_type and s.is_free)

    # ── Slot assignment ──────────────────────────────────────────────────────

    def request_slot(self, forklift_id: int,
                     slot_type: str,
                     preferred_gate: int | None = None) -> QueueSlot | None:
        """Try to reserve a free slot of *slot_type* for *forklift_id*.

        If *preferred_gate* is given, the slot closest to that gate index is
        tried first (dock slots are ordered gate-left→right matching
        C.GATE_OFFSETS order).  Falls back to any free slot.

        Returns the reserved QueueSlot, or None if all slots are full.
        """
        # If already holds a slot of this type, return it
        existing = self.slot_for(forklift_id)
        if existing and existing.slot_type == slot_type:
            return existing

        candidates = [s for s in self._slots
                      if s.slot_type == slot_type and s.is_free]
        if not candidates:
            return None

        if preferred_gate is not None and preferred_gate < len(candidates):
            slot = candidates[preferred_gate]
        else:
            slot = candidates[0]

        slot.assign(forklift_id)
        return slot

    def release_slot(self, forklift_id: int) -> None:
        """Release whatever slot this forklift currently holds."""
        slot = self.slot_for(forklift_id)
        if slot:
            slot.release()

    def release_all(self) -> None:
        for s in self._slots:
            s.release()

    # ── Debug ────────────────────────────────────────────────────────────────

    def print_status(self) -> None:
        for s in self._slots:
            print(f"  {s}")
