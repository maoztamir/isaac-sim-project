"""
Zone definitions, occupancy monitoring, and dwell-time tracking.
"""

from __future__ import annotations
import time


class Zone:
    """An axis-aligned rectangular area on the warehouse floor."""

    def __init__(self, name: str, x_min: float, x_max: float,
                 y_min: float, y_max: float):
        self.name = name
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        # Occupancy: set of forklift IDs currently inside
        self._occupants: set[int] = set()
        # Dwell tracking: forklift_id -> entry_sim_time
        self._entry_times: dict[int, float] = {}

    def contains(self, x: float, y: float) -> bool:
        return (self.x_min <= x <= self.x_max and
                self.y_min <= y <= self.y_max)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x_min + self.x_max) / 2.0,
                (self.y_min + self.y_max) / 2.0)

    @property
    def occupancy(self) -> int:
        return len(self._occupants)

    @property
    def occupant_ids(self) -> set[int]:
        return set(self._occupants)

    def update_occupant(self, fl_id: int, x: float, y: float, sim_time: float):
        """Call each frame per forklift. Tracks enter/exit and dwell time."""
        inside = self.contains(x, y)
        was_inside = fl_id in self._occupants

        if inside and not was_inside:
            self._occupants.add(fl_id)
            self._entry_times[fl_id] = sim_time
        elif not inside and was_inside:
            self._occupants.discard(fl_id)
            self._entry_times.pop(fl_id, None)

    def dwell_time(self, fl_id: int, sim_time: float) -> float:
        """Seconds this forklift has been continuously inside the zone."""
        entry = self._entry_times.get(fl_id)
        if entry is None:
            return 0.0
        return sim_time - entry

    def random_point(self, rng) -> tuple[float, float]:
        """Return a random (x, y) inside the zone using the given RNG."""
        x = rng.uniform(self.x_min + 0.5, self.x_max - 0.5)
        y = rng.uniform(self.y_min + 0.5, self.y_max - 0.5)
        return (x, y)


class ZoneManager:
    """Holds all zones; updates occupancy each frame."""

    def __init__(self):
        self.zones: dict[str, Zone] = {}

    def add(self, name: str, x_min: float, x_max: float,
            y_min: float, y_max: float) -> Zone:
        z = Zone(name, x_min, x_max, y_min, y_max)
        self.zones[name] = z
        return z

    def get(self, name: str) -> Zone | None:
        return self.zones.get(name)

    def update(self, fl_id: int, x: float, y: float, sim_time: float):
        """Update all zones for one forklift's position."""
        for z in self.zones.values():
            z.update_occupant(fl_id, x, y, sim_time)

    def zone_of(self, x: float, y: float) -> Zone | None:
        """Return the first zone that contains (x, y), or None."""
        for z in self.zones.values():
            if z.contains(x, y):
                return z
        return None

    def print_status(self, sim_time: float):
        for z in self.zones.values():
            ids = sorted(z.occupant_ids)
            dwells = [f"FL{i}={z.dwell_time(i, sim_time):.1f}s" for i in ids]
            print(f"  [{z.name}] occupancy={z.occupancy}  {' '.join(dwells)}")
