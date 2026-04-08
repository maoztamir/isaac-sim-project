"""
Shelf detection and aisle computation.

Scans the warehouse USD on first physics step for shelf/rack prims,
builds bounding-box collision rects, and derives aisle centre lines.
"""

from __future__ import annotations
from pxr import Usd, UsdGeom

from . import config as C
from . import isaac_helpers as ih


class ShelfMap:
    """Immutable after init(): holds shelf rects and aisle X centres."""

    def __init__(self):
        self.rects: list[tuple[float, float, float, float]] = []  # (x0, x1, y0, y1)
        self.aisle_xs: list[float] = []
        self.area_y_min: float | None = None
        self.area_y_max: float | None = None
        self.ready = False

    # ── Queries ──────────────────────────────────────────────────────────

    def inside_shelf(self, x, y, margin=0.0) -> bool:
        for rx0, rx1, ry0, ry1 in self.rects:
            if rx0 - margin < x < rx1 + margin and ry0 - margin < y < ry1 + margin:
                return True
        return False

    def in_shelf_area(self, y) -> bool:
        return (self.area_y_min is not None and
                self.area_y_min - 1.0 < y < self.area_y_max + 1.0)

    def nearest_aisle(self, x) -> float:
        if not self.aisle_xs:
            return x
        return min(self.aisle_xs, key=lambda ax: abs(ax - x))

    # ── Initialisation (call once, on first physics step) ────────────────

    def init(self, stage):
        if self.ready:
            return
        self._scan_shelves(stage)
        self._compute_aisles()
        self.ready = True
        print(f"[ShelfMap] {len(self.rects)} shelf rects, "
              f"{len(self.aisle_xs)} aisles detected.")

    def _scan_shelves(self, stage):
        wh = stage.GetPrimAtPath("/World/Warehouse")
        if not wh.IsValid():
            return
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
        seen = []
        for prim in Usd.PrimRange(wh):
            if not any(k in prim.GetName().lower() for k in C.SHELF_KEYWORDS):
                continue
            if not prim.IsA(UsdGeom.Xformable):
                continue
            try:
                rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                mn, mx = rng.GetMin(), rng.GetMax()
                w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
                if w < 0.5 or d < 0.5 or h < 0.5:
                    continue
                cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
                if any(abs(cx-s[0]) < 0.5 and abs(cy-s[1]) < 0.5 for s in seen):
                    continue
                seen.append((cx, cy))
                self.rects.append((mn[0], mx[0], mn[1], mx[1]))
            except Exception:
                pass

        # Fallback: large structures if no keywords matched
        if not self.rects:
            for prim in Usd.PrimRange(wh):
                if not prim.IsA(UsdGeom.Xformable):
                    continue
                try:
                    rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                    mn, mx = rng.GetMin(), rng.GetMax()
                    w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
                    if w > 4.0 and d > 0.8 and h > 1.5:
                        cx = (mn[0]+mx[0])/2
                        cy = (mn[1]+mx[1])/2
                        if any(abs(cx-s[0]) < 1.0 and abs(cy-s[1]) < 1.0 for s in seen):
                            continue
                        seen.append((cx, cy))
                        self.rects.append((mn[0], mx[0], mn[1], mx[1]))
                except Exception:
                    pass

    def _compute_aisles(self):
        if not self.rects:
            return
        self.area_y_min = min(r[2] for r in self.rects)
        self.area_y_max = max(r[3] for r in self.rects)

        intervals = sorted((r[0], r[1]) for r in self.rects)
        merged = []
        for a, b in intervals:
            if merged and a < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        for i in range(len(merged) - 1):
            gx0, gx1 = merged[i][1], merged[i + 1][0]
            if gx1 - gx0 > 1.0:
                self.aisle_xs.append((gx0 + gx1) / 2.0)
        if merged:
            if merged[0][0] - C.NAV_X_MIN > 2.0:
                self.aisle_xs.append((C.NAV_X_MIN + merged[0][0]) / 2.0)
            if C.NAV_X_MAX - merged[-1][1] > 2.0:
                self.aisle_xs.append((merged[-1][1] + C.NAV_X_MAX) / 2.0)
        self.aisle_xs.sort()
        print(f"[ShelfMap] Shelf Y: {self.area_y_min:.1f} -> {self.area_y_max:.1f}")
        print(f"[ShelfMap] Aisles X: {[round(x, 1) for x in self.aisle_xs]}")
