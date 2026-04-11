"""
Pallet: tracked pallet object with its own USD prim.

Each Pallet owns one USD prim and holds the state needed by the rule engine
(Task #6) to drive pallet flow through the warehouse.
"""

from __future__ import annotations

from .. import config as C
from .. import isaac_helpers as ih


# Valid location values
LOC_SHELVES  = "shelves"
LOC_STAGING  = "staging"
LOC_FORKLIFT = "forklift"
LOC_DOCK     = "dock"
LOC_HIDDEN   = "hidden"


class Pallet:
    def __init__(self, pallet_id: int, prim_path: str,
                 location: str = LOC_HIDDEN,
                 xy: tuple[float, float] | None = None):
        self.id = pallet_id
        self.prim_path = prim_path
        self.location = location
        self.xy = xy
        self.assigned_forklift_id: int | None = None

    # ── Spawn / lifecycle ────────────────────────────────────────────────────

    def spawn(self, stage, assets_root: str,
              x: float, y: float, z: float = 0.0, yaw_deg: float = 0.0,
              box_usd: str | None = None) -> None:
        """Create the pallet USD prim at the given position.

        If *box_usd* is provided (a path relative to assets_root), a cargo box
        prim is also spawned as a child of the pallet prim, sitting on top of
        the pallet at z + PALLET_H.  USD visibility inheritance ensures the box
        hides / shows automatically whenever the parent pallet prim is toggled.
        """
        ih.spawn_asset(stage, self.prim_path,
                       C.PALLET_USD,
                       x, y, z, yaw_deg,
                       scale=C.PALLET_SCALE)
        self.xy = (x, y)

        if box_usd is not None:
            ih.spawn_asset(stage, self.prim_path + "/box",
                           assets_root + box_usd,
                           x, y, z + C.PALLET_H, yaw_deg)

    # ── Visibility ───────────────────────────────────────────────────────────

    def show(self, stage) -> None:
        ih.make_visible(stage, self.prim_path)

    def hide(self, stage) -> None:
        ih.make_invisible(stage, self.prim_path)

    # ── Position / location updates ──────────────────────────────────────────

    def set_xy(self, stage, x: float, y: float) -> None:
        """Move the pallet prim on the floor."""
        ih.set_prim_translate_xy(stage, self.prim_path, x, y)
        self.xy = (x, y)

    def set_location(self, location: str) -> None:
        """Update the logical location string. Caller is responsible for
        moving the prim if the location change implies a position change."""
        self.location = location

    def __repr__(self) -> str:
        fl = f" fl={self.assigned_forklift_id}" if self.assigned_forklift_id is not None else ""
        xy = f" xy={self.xy}" if self.xy else ""
        return f"Pallet(id={self.id}, loc={self.location}{fl}{xy})"
