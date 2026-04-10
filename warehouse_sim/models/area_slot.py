"""
AreaSlot: one sub-slot of a LoadingArea or StagingArea (3 per area type).

Each slot owns a list of Pallets and can be toggled active/inactive to
simulate "this bay has work / is idle". Active slots show their pallets;
inactive slots hide them.
"""

from __future__ import annotations
import random

from .. import config as C
from .pallet import Pallet, LOC_STAGING, LOC_DOCK


TYPE_LOADING = "loading"
TYPE_STAGING = "staging"


class AreaSlot:
    def __init__(self, slot_id: int, area_type: str,
                 center: tuple[float, float],
                 width: float, depth: float,
                 is_active: bool = True):
        assert area_type in (TYPE_LOADING, TYPE_STAGING)
        self.slot_id = slot_id
        self.area_type = area_type
        self.center = center
        self.width = width
        self.depth = depth
        self.is_active = is_active
        self.pallets: list[Pallet] = []

    # ── Activity control ─────────────────────────────────────────────────────

    def activate(self, stage) -> None:
        """Mark slot as active and show all contained pallets."""
        self.is_active = True
        for p in self.pallets:
            p.show(stage)

    def deactivate(self, stage) -> None:
        """Mark slot as inactive and hide all contained pallets."""
        self.is_active = False
        for p in self.pallets:
            p.hide(stage)

    # ── Pallet management ────────────────────────────────────────────────────

    def add_pallet(self, pallet: Pallet) -> None:
        self.pallets.append(pallet)

    def spawn_pallets(self, stage, assets_root: str, count: int,
                      rng: random.Random,
                      prim_root: str = "/World/AreaSlots") -> None:
        """Create `count` pallet prims scattered inside the slot bounds."""
        cx, cy = self.center
        hw = self.width  / 2.0 - 0.8
        hd = self.depth  / 2.0 - 0.8
        location = LOC_STAGING if self.area_type == TYPE_STAGING else LOC_DOCK
        base = f"{prim_root}/{self.area_type}_{self.slot_id}"

        for i in range(count):
            px  = cx + rng.uniform(-hw, hw)
            py  = cy + rng.uniform(-hd, hd)
            yaw = rng.choice([0.0, 90.0, 180.0, -90.0])
            pid = len(self.pallets)
            prim_path = f"{base}/pallet_{pid}"
            pallet = Pallet(pallet_id=pid, prim_path=prim_path, location=location)
            pallet.spawn(stage, assets_root, px, py, z=0.0, yaw_deg=yaw)
            self.pallets.append(pallet)

        # Respect the initial is_active flag
        if not self.is_active:
            for p in self.pallets:
                p.hide(stage)

    def __repr__(self) -> str:
        st = "ACTIVE" if self.is_active else "inactive"
        return f"AreaSlot({self.area_type}#{self.slot_id}, {st}, {len(self.pallets)} pallets)"


# ── Factory helpers ──────────────────────────────────────────────────────────

def build_loading_slots() -> list[AreaSlot]:
    """Create the 3 loading-door slots from config geometry."""
    slots = []
    load_cy = C.WALL_Y_MIN + C.LOAD_D / 2.0
    for i, offset in enumerate(C.GATE_OFFSETS):
        cx = C.WAREHOUSE_CX + offset
        slots.append(AreaSlot(
            slot_id=i, area_type=TYPE_LOADING,
            center=(cx, load_cy),
            width=C.LOAD_W, depth=C.LOAD_D,
        ))
    return slots


def build_staging_slots() -> list[AreaSlot]:
    """Create the 3 staging-bay slots from config geometry."""
    slots = []
    for i, offset in enumerate(C.GATE_OFFSETS):
        cx = C.WAREHOUSE_CX + offset
        slots.append(AreaSlot(
            slot_id=i, area_type=TYPE_STAGING,
            center=(cx, C.STAGING_CENTER_Y),
            width=C.STAGING_W, depth=C.STAGING_D,
        ))
    return slots
