"""
Shelf detection and aisle computation.

Scans the warehouse USD on first physics step for shelf/rack prims,
builds bounding-box collision rects, and derives aisle centre lines.

Detection strategy (tried in order):
  1. Keyword scan — matches prim names against C.SHELF_KEYWORDS
  2. Decal scan   — uses floor decal prims as layout markers:
       SM_FloorDecal_RecRed        → aisle X centres + shelf Y span
       SM_FloorDecal_StripeFull_4m → shelf block X boundaries
  3. Size-based fallback — bbox size heuristics
"""

from __future__ import annotations
from pxr import Usd, UsdGeom

from . import config as C
from . import isaac_helpers as ih


def _cluster_values(values: list[float], gap: float = 1.0) -> list[float]:
    """Merge values within `gap` of each other; return cluster centres."""
    if not values:
        return []
    sorted_vals = sorted(values)
    clusters: list[list[float]] = [[sorted_vals[0]]]
    for v in sorted_vals[1:]:
        if v - clusters[-1][-1] <= gap:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


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
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])

        # ── Strategy 1: decal-based scan (most reliable for this warehouse) ──
        print("[ShelfMap] trying decal-based scan first")
        self._scan_shelves_from_decals(stage, cache)
        if self.rects:
            return

        # ── Strategy 2: keyword scan ─────────────────────────────────────────
        print("[ShelfMap] decal scan found nothing — trying keyword scan")
        wh_img = UsdGeom.Imageable.Get(stage, "/World/Warehouse")
        if not wh_img or not wh_img.GetPrim().IsValid():
            return
        wh = wh_img.GetPrim()

        # Anything wider than 60 % of the navigable X span is structural (wall,
        # roof truss, etc.) — not a shelf rack.
        max_shelf_w = (C.NAV_X_MAX - C.NAV_X_MIN) * 0.6

        # Track matched prim paths so we skip their descendants and avoid
        # producing duplicate rects for parent + child prims of the same rack.
        matched_paths: set = set()

        for prim in Usd.PrimRange(wh):
            if not prim.IsA(UsdGeom.Xformable):
                continue
            ppath = str(prim.GetPath())
            # Skip if already covered by an ancestor match
            if any(ppath.startswith(mp + '/') for mp in matched_paths):
                continue
            if not any(k in prim.GetName().lower() for k in C.SHELF_KEYWORDS):
                continue
            try:
                bbox = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                mn, mx = bbox.GetMin(), bbox.GetMax()
                w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
                if w < 0.5 or d < 0.5 or h < 0.5:
                    continue
                if w > max_shelf_w:
                    continue
                cx, cy = (mn[0]+mx[0])/2.0, (mn[1]+mx[1])/2.0
                # Must sit inside the navigable floor area
                if not (C.NAV_X_MIN < cx < C.NAV_X_MAX and
                        C.NAV_Y_MIN < cy < C.NAV_Y_MAX):
                    continue
                matched_paths.add(ppath)
                self.rects.append((mn[0], mx[0], mn[1], mx[1]))
                print(f"[ShelfMap]   shelf: {prim.GetName()!r:30s} "
                      f"x=({mn[0]:.1f},{mx[0]:.1f}) y=({mn[1]:.1f},{mx[1]:.1f}) "
                      f"size={w:.1f}×{d:.1f}×{h:.1f}m")
            except Exception:
                pass

        # ── Strategy 3: size-based fallback ──────────────────────────────────
        if not self.rects:
            print("[ShelfMap] keyword scan found nothing — trying size-based fallback")
            matched_paths.clear()
            for prim in Usd.PrimRange(wh):
                if not prim.IsA(UsdGeom.Xformable):
                    continue
                ppath = str(prim.GetPath())
                if any(ppath.startswith(mp + '/') for mp in matched_paths):
                    continue
                try:
                    bbox = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                    mn, mx = bbox.GetMin(), bbox.GetMax()
                    w, d, h = mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]
                    if not (4.0 < w < max_shelf_w and d > 0.8 and h > 1.5):
                        continue
                    cx, cy = (mn[0]+mx[0])/2.0, (mn[1]+mx[1])/2.0
                    if not (C.NAV_X_MIN < cx < C.NAV_X_MAX and
                            C.NAV_Y_MIN < cy < C.NAV_Y_MAX):
                        continue
                    matched_paths.add(ppath)
                    self.rects.append((mn[0], mx[0], mn[1], mx[1]))
                    print(f"[ShelfMap]   fallback: {prim.GetName()!r} "
                          f"x=({mn[0]:.1f},{mx[0]:.1f}) y=({mn[1]:.1f},{mx[1]:.1f})")
                except Exception:
                    pass

    def _scan_shelves_from_decals(self, stage, cache):
        """Derive shelf rects from floor-decal layout prims.

        SM_FloorDecal_RecRed        — rectangular red markers placed at the
            front AND back of every aisle entrance.  Their X centres cluster
            to give aisle_xs; their Y extent gives the shelf block Y range.

        SM_FloorDecal_StripeFull_4m — long stripe decals placed along the
            LEFT and RIGHT edges of each shelf block (parallel to the aisles).
            Their X centres cluster to give shelf-block boundary X values.

        Shelf blocks are then the X-axis intervals between adjacent boundary
        values whose midpoint does NOT coincide with a known aisle X.
        """
        # Search under /World/Warehouse first; fall back to the full stage root
        # so decals placed outside the warehouse prim hierarchy are still found.
        wh_img = UsdGeom.Imageable.Get(stage, "/World/Warehouse")
        if wh_img and wh_img.GetPrim().IsValid():
            search_root = wh_img.GetPrim()
        else:
            search_root = stage.GetPseudoRoot()
            print("[ShelfMap] decal scan: /World/Warehouse not found, "
                  "scanning full stage")

        red_xs: list[float] = []
        red_ys: list[float] = []   # all Y positions of red decals
        stripe_xs: list[float] = []

        for prim in Usd.PrimRange(search_root):
            name = prim.GetName()
            if not prim.IsA(UsdGeom.Xformable):
                continue
            is_red    = "SM_FloorDecal_RecRed"         in name
            is_stripe = "SM_FloorDecal_StripeFull_4m"  in name
            if not (is_red or is_stripe):
                continue
            try:
                bbox = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                mn, mx = bbox.GetMin(), bbox.GetMax()
                cx = (mn[0] + mx[0]) / 2.0
                cy = (mn[1] + mx[1]) / 2.0
                # Must sit inside the navigable floor area
                if not (C.NAV_X_MIN < cx < C.NAV_X_MAX and
                        C.NAV_Y_MIN < cy < C.NAV_Y_MAX):
                    continue
                if is_red:
                    red_xs.append(cx)
                    red_ys.append(mn[1])
                    red_ys.append(mx[1])
                    print(f"[ShelfMap]   decal RecRed    {name!r:40s} "
                          f"cx={cx:.2f} cy={cy:.2f}")
                else:
                    stripe_xs.append(cx)
                    print(f"[ShelfMap]   decal Stripe4m  {name!r:40s} "
                          f"cx={cx:.2f} cy={cy:.2f}")
            except Exception:
                pass

        # If nothing found under /World/Warehouse, retry from the full stage root
        if not red_xs and search_root != stage.GetPseudoRoot():
            print("[ShelfMap] decal scan: no decals under /World/Warehouse, "
                  "retrying from stage root")
            for prim in Usd.PrimRange(stage.GetPseudoRoot()):
                name = prim.GetName()
                if not prim.IsA(UsdGeom.Xformable):
                    continue
                is_red    = "SM_FloorDecal_RecRed"        in name
                is_stripe = "SM_FloorDecal_StripeFull_4m" in name
                if not (is_red or is_stripe):
                    continue
                try:
                    bbox = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                    mn, mx = bbox.GetMin(), bbox.GetMax()
                    cx = (mn[0] + mx[0]) / 2.0
                    cy = (mn[1] + mx[1]) / 2.0
                    if not (C.NAV_X_MIN < cx < C.NAV_X_MAX and
                            C.NAV_Y_MIN < cy < C.NAV_Y_MAX):
                        continue
                    if is_red:
                        red_xs.append(cx)
                        red_ys.append(mn[1])
                        red_ys.append(mx[1])
                        print(f"[ShelfMap]   decal RecRed    {name!r:40s} "
                              f"cx={cx:.2f} cy={cy:.2f}")
                    else:
                        stripe_xs.append(cx)
                        print(f"[ShelfMap]   decal Stripe4m  {name!r:40s} "
                              f"cx={cx:.2f} cy={cy:.2f}")
                except Exception:
                    pass

        if not red_xs:
            print("[ShelfMap] decal scan: no SM_FloorDecal_RecRed found anywhere")
            return

        # ── Derive aisle X centres from red decals ───────────────────────────
        aisle_xs = _cluster_values(red_xs, gap=1.5)
        print(f"[ShelfMap] decal scan: aisle Xs = {[round(x, 2) for x in aisle_xs]}")

        # ── Shelf Y range from min/max of all red-decal Y extents ────────────
        shelf_y_min = min(red_ys)
        shelf_y_max = max(red_ys)
        print(f"[ShelfMap] decal scan: shelf Y {shelf_y_min:.2f} → {shelf_y_max:.2f}")

        if not stripe_xs:
            print("[ShelfMap] decal scan: no SM_FloorDecal_StripeFull_4m found; "
                  "cannot build shelf block rects")
            return

        # ── Derive shelf-block boundary X values from stripe decals ──────────
        boundary_xs = _cluster_values(stripe_xs, gap=0.5)
        print(f"[ShelfMap] decal scan: boundary Xs = "
              f"{[round(x, 2) for x in boundary_xs]}")

        # Add nav-area edges as outer boundaries
        all_bounds = sorted([C.NAV_X_MIN] + boundary_xs + [C.NAV_X_MAX])

        # ── Build shelf rects: gaps between boundaries not centred on an aisle
        AISLE_TOL = 1.2   # metres — a gap midpoint this close to an aisle X is an aisle
        for i in range(len(all_bounds) - 1):
            x0, x1 = all_bounds[i], all_bounds[i + 1]
            gap_w = x1 - x0
            if gap_w < 0.5:
                continue
            mid_x = (x0 + x1) / 2.0
            near_aisle = any(abs(mid_x - ax) < AISLE_TOL for ax in aisle_xs)
            if near_aisle:
                continue   # this gap is an aisle corridor — skip
            self.rects.append((x0, x1, shelf_y_min, shelf_y_max))
            print(f"[ShelfMap]   shelf block: x=({x0:.2f},{x1:.2f}) "
                  f"y=({shelf_y_min:.2f},{shelf_y_max:.2f}) "
                  f"w={gap_w:.2f}m")

        if self.rects:
            # Pre-populate aisle_xs and Y range so _compute_aisles can skip
            # the interval-merge step and use these directly
            self.aisle_xs  = sorted(aisle_xs)
            self.area_y_min = shelf_y_min
            self.area_y_max = shelf_y_max
            print(f"[ShelfMap] decal scan complete: "
                  f"{len(self.rects)} rects, {len(self.aisle_xs)} aisles")
        else:
            print("[ShelfMap] decal scan: boundary gaps all map to aisles — "
                  "check AISLE_TOL or stripe positions")

    def _compute_aisles(self):
        if not self.rects:
            return
        # Decal scan already populated aisle_xs and Y range — skip re-derivation
        if self.aisle_xs and self.area_y_min is not None:
            print(f"[ShelfMap] Shelf Y: {self.area_y_min:.1f} -> {self.area_y_max:.1f}")
            print(f"[ShelfMap] Aisles X: {[round(x, 1) for x in self.aisle_xs]}")
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
