"""
QueueSlot: a reservable position in the dock queue or staging hold.

Used by the queue manager (Task #6) to deterministically assign waiting
positions to forklifts as they arrive.
"""

from __future__ import annotations


SLOT_DOCK         = "dock"          # one forklift at the loading dock
SLOT_STAGING_HOLD = "staging_hold"  # waiting position inside staging area


class QueueSlot:
    def __init__(self, slot_id: int, position: tuple[float, float],
                 slot_type: str = SLOT_DOCK):
        self.slot_id = slot_id
        self.position = position
        self.slot_type = slot_type
        self.occupied_by: int | None = None  # forklift id

    @property
    def is_free(self) -> bool:
        return self.occupied_by is None

    def assign(self, forklift_id: int) -> bool:
        """Reserve the slot for a forklift. Returns True on success."""
        if self.occupied_by is not None and self.occupied_by != forklift_id:
            return False
        self.occupied_by = forklift_id
        return True

    def release(self) -> None:
        self.occupied_by = None

    def __repr__(self) -> str:
        state = f"FL{self.occupied_by}" if self.occupied_by is not None else "free"
        return f"QueueSlot({self.slot_type}#{self.slot_id}, {state})"
