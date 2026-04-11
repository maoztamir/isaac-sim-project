"""
Pallet-forklift handoff and location consistency.

assign_pallet  — link a Pallet to a Forklift and move pallet prim onto forks
release_pallet — unlink and place the pallet at a target position
validate_pallet_consistency — logs warnings when pallet location and forklift
                              load state disagree (for monitoring / alerts)
"""

from __future__ import annotations

from ..models.pallet  import Pallet, LOC_FORKLIFT, LOC_STAGING, LOC_DOCK
from ..models.forklift import Forklift
from .. import config as C


def assign_pallet(forklift: Forklift, pallet: Pallet, stage,
                  assets_root: str | None = None) -> None:
    """Mount *pallet* onto *forklift*.

    - Sets pallet.assigned_forklift_id
    - Sets pallet.location = LOC_FORKLIFT
    - Calls forklift.set_load(LOAD_LOADED) to raise forks + show carried prim
    """
    pallet.assigned_forklift_id = forklift.id
    pallet.set_location(LOC_FORKLIFT)
    forklift.set_load(stage, C.LOAD_LOADED, assets_root=assets_root)
    print(f"[pallet_flow] Pallet {pallet.id} → FL{forklift.id} (pickup)")


def release_pallet(forklift: Forklift, pallet: Pallet, stage,
                   drop_location: str = LOC_DOCK,
                   drop_xy: tuple[float, float] | None = None) -> None:
    """Unmount *pallet* from *forklift* and place it at a floor position.

    - Lowers forks (LOAD_UNLOADED)
    - Moves pallet prim to *drop_xy* (if provided)
    - Sets pallet.location = *drop_location*
    - Clears pallet.assigned_forklift_id
    """
    forklift.set_load(stage, C.LOAD_UNLOADED)

    if drop_xy is not None:
        pallet.set_xy(stage, drop_xy[0], drop_xy[1])
    pallet.set_location(drop_location)
    pallet.assigned_forklift_id = None
    print(f"[pallet_flow] Pallet {pallet.id} dropped at {drop_location} "
          f"by FL{forklift.id}")


def validate_pallet_consistency(forklifts: list[Forklift],
                                pallets: list[Pallet]) -> list[str]:
    """Return a list of human-readable inconsistency warnings.

    Checks:
    - A LOAD_LOADED forklift should have exactly one pallet assigned to it.
    - A pallet with location=LOC_FORKLIFT should be assigned to a loaded forklift.
    - No pallet should be assigned to more than one forklift.
    """
    warnings: list[str] = []

    fl_map = {fl.id: fl for fl in forklifts}
    assigned_to: dict[int, int] = {}  # pallet_id → forklift_id

    for p in pallets:
        if p.assigned_forklift_id is not None:
            if p.assigned_forklift_id in assigned_to.values():
                warnings.append(
                    f"Pallet {p.id}: duplicate assignment to FL{p.assigned_forklift_id}"
                )
            assigned_to[p.id] = p.assigned_forklift_id

    for fl in forklifts:
        carried = [p for p in pallets if p.assigned_forklift_id == fl.id]
        if fl.load == C.LOAD_LOADED and len(carried) == 0:
            warnings.append(
                f"FL{fl.id}: state=LOADED but no pallet assigned"
            )
        if fl.load == C.LOAD_UNLOADED and len(carried) > 0:
            warnings.append(
                f"FL{fl.id}: state=UNLOADED but pallet {carried[0].id} still assigned"
            )

    for p in pallets:
        if p.location == LOC_FORKLIFT and p.assigned_forklift_id is None:
            warnings.append(
                f"Pallet {p.id}: location=FORKLIFT but no assigned_forklift_id"
            )
        if p.location == LOC_FORKLIFT and p.assigned_forklift_id is not None:
            fl = fl_map.get(p.assigned_forklift_id)
            if fl and fl.load == C.LOAD_UNLOADED:
                warnings.append(
                    f"Pallet {p.id}: location=FORKLIFT but FL{fl.id} is UNLOADED"
                )

    return warnings
