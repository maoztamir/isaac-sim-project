"""
Waypoint generation and path helpers.

Generates random navigable points that respect shelf collision rects,
prefer aisle lanes, and can target specific zones.
"""

from __future__ import annotations
import random as _random

from . import config as C
from .shelves import ShelfMap
from .zones import Zone


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


def rand_zone_point(zone: Zone, shelf_map: ShelfMap,
                    rng: _random.Random) -> tuple[float, float]:
    """Random navigable point inside a specific zone."""
    for _ in range(30):
        x, y = zone.random_point(rng)
        if not shelf_map.inside_shelf(x, y, margin=1.5):
            return (x, y)
    return zone.center


def gen_patrol(shelf_map: ShelfMap, rng: _random.Random,
               n=8) -> list[tuple[float, float]]:
    """Mixed open-floor and aisle waypoints for full-warehouse patrol."""
    return [rand_floor_point(shelf_map, rng, prefer_aisle=(i % 3 == 0))
            for i in range(n)]


def gen_zone_route(zones: list[Zone], shelf_map: ShelfMap,
                   rng: _random.Random,
                   points_per_zone=2) -> list[tuple[float, float]]:
    """Route that visits each zone in order with multiple waypoints per zone."""
    pts = []
    for z in zones:
        for _ in range(points_per_zone):
            pts.append(rand_zone_point(z, shelf_map, rng))
    return pts
