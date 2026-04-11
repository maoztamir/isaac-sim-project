"""
Waypoint generation and path helpers.

Two layers:
  - Explicit deterministic waypoints used by the rule engine (state-driven scenarios).
  - Random/patrol generators kept for backward compatibility with old scenario code.
"""

from __future__ import annotations
import random as _random

from . import config as C
from .shelves import ShelfMap
from .areas import Area


# ── Explicit deterministic waypoints ────────────────────────────────────────

def get_dock_service_position(gate_idx: int) -> tuple[float, float]:
    """Centre of the loading zone directly in front of gate gate_idx.

    This is where a forklift parks to hand off a pallet to the truck.
    """
    cx = C.WAREHOUSE_CX + C.GATE_OFFSETS[gate_idx]
    y  = C.WALL_Y_MIN + C.LOAD_D / 2.0
    return (cx, y)


def get_dock_queue_spots() -> list[tuple[float, float]]:
    """One queue-hold position per gate, just north of the loading zone edge.

    Forklifts wait here when the dock slot is occupied. Ordered LEFT → RIGHT.
    """
    queue_y = C.WALL_Y_MIN + C.LOAD_D + 2.0
    return [(C.WAREHOUSE_CX + offset, queue_y) for offset in C.GATE_OFFSETS]


def get_staging_hold_positions() -> list[tuple[float, float]]:
    """One hold position per gate column inside the staging area.

    Used as intermediate stops when staging is the next destination.
    Ordered LEFT → RIGHT.
    """
    return [(C.WAREHOUSE_CX + offset, C.STAGING_CENTER_Y)
            for offset in C.GATE_OFFSETS]


def get_pickup_points(shelf_map: ShelfMap) -> list[tuple[float, float]]:
    """One pickup point per detected aisle, at the aisle entrance (south end).

    Returns an empty list if shelf_map is not yet initialised.
    """
    if not shelf_map.aisle_xs or shelf_map.area_y_min is None:
        return []
    entrance_y = shelf_map.area_y_min + 2.0
    return [(ax, entrance_y) for ax in shelf_map.aisle_xs]


def get_return_path(gate_idx: int, shelf_map: ShelfMap) -> list[tuple[float, float]]:
    """Waypoints guiding an empty forklift from a dock back toward the shelves.

    Route: dock queue spot → staging hold → nearest aisle entrance.
    Falls back to open floor staging if shelf_map not ready.
    """
    cx = C.WAREHOUSE_CX + C.GATE_OFFSETS[gate_idx]
    path: list[tuple[float, float]] = [
        (cx, C.WALL_Y_MIN + C.LOAD_D + 2.0),   # clear the dock
        (cx, C.STAGING_CENTER_Y),               # staging midpoint
    ]
    if shelf_map.aisle_xs and shelf_map.area_y_min is not None:
        nearest_ax = min(shelf_map.aisle_xs, key=lambda ax: abs(ax - cx))
        path.append((nearest_ax, shelf_map.area_y_min + 2.0))
    else:
        path.append((cx, C.WALL_Y_MAX - 4.0))
    return path


def rand_floor_point(shelf_map: ShelfMap, rng: _random.Random,
                     prefer_aisle=False) -> tuple[float, float]:
    """Random navigable point on the warehouse floor."""
    if (prefer_aisle and shelf_map.aisle_xs and
            shelf_map.area_y_min is not None):
        ax = rng.choice(shelf_map.aisle_xs)
        ay = rng.uniform(shelf_map.area_y_min + 1.0,
                         shelf_map.area_y_max - 1.0)
        return (ax, ay)
    for _ in range(30):
        x = rng.uniform(C.NAV_X_MIN + 1.0, C.NAV_X_MAX - 1.0)
        y = rng.uniform(C.NAV_Y_MIN + 1.0, C.NAV_Y_MAX - 1.0)
        if not shelf_map.inside_shelf(x, y, margin=1.5):
            return (x, y)
    return (x, y)


def rand_zone_point(zone: Area, shelf_map: ShelfMap,
                    rng: _random.Random) -> tuple[float, float]:
    """Random navigable point inside a specific zone.

    When the zone falls in the shelf Y range the X coordinate is snapped to
    the nearest detected aisle so the returned point is always in a corridor,
    never inside a rack.
    """
    for _ in range(30):
        x, y = zone.random_point(rng)
        if shelf_map.in_shelf_area(y) and shelf_map.aisle_xs:
            x = shelf_map.nearest_aisle(x)
        if not shelf_map.inside_shelf(x, y, margin=1.5):
            return (x, y)
    # Fallback: aisle centre if in shelf area, else zone centre
    if shelf_map.in_shelf_area(zone.center[1]) and shelf_map.aisle_xs:
        return (shelf_map.nearest_aisle(zone.center[0]), zone.center[1])
    return zone.center


def aisle_route(origin: tuple[float, float], dest: tuple[float, float],
                shelf_map: ShelfMap) -> list[tuple[float, float]]:
    """Return waypoints that cross the shelf area via the correct aisle.

    Entering shelves: pre-aligns to the destination aisle 1.5 m south of the
    shelf boundary before proceeding north — ensures the forklift is in the
    right corridor before shelf rects appear.

    Exiting shelves: exits south via the origin aisle before heading to the
    open-floor destination.

    If shelf_map is not ready or the route stays outside the shelf area the
    function returns [dest] unchanged.
    """
    if not shelf_map.aisle_xs or shelf_map.area_y_min is None:
        return [dest]

    ox, oy = origin
    dx, dy = dest

    orig_in = shelf_map.in_shelf_area(oy)
    dest_in = shelf_map.in_shelf_area(dy)
    approach_y = shelf_map.area_y_min - 1.5   # open floor just south of shelves

    if dest_in and not orig_in:
        # Entering shelves: align to dest aisle south of boundary, then proceed
        ax = shelf_map.nearest_aisle(dx)
        return [(ax, approach_y), (ax, dy)]

    if orig_in and not dest_in:
        # Exiting shelves: drive to aisle exit first, then open floor
        ax = shelf_map.nearest_aisle(ox)
        return [(ax, approach_y), dest]

    if dest_in and orig_in:
        # Both ends inside shelves — route via aisle columns only
        ax = shelf_map.nearest_aisle(dx)
        return [(ax, dy)]

    return [dest]


def gen_patrol(shelf_map: ShelfMap, rng: _random.Random,
               n=8) -> list[tuple[float, float]]:
    """Mixed open-floor and aisle waypoints for full-warehouse patrol."""
    return [rand_floor_point(shelf_map, rng, prefer_aisle=(i % 3 == 0))
            for i in range(n)]


def gen_zone_route(zones: list[Area], shelf_map: ShelfMap,
                   rng: _random.Random,
                   points_per_zone=2) -> list[tuple[float, float]]:
    """Route that visits each zone in order with multiple waypoints per zone."""
    pts = []
    for z in zones:
        for _ in range(points_per_zone):
            pts.append(rand_zone_point(z, shelf_map, rng))
    return pts
