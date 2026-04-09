"""
Area definitions, occupancy monitoring, and dwell-time tracking.

An Area is an axis-aligned rectangular region on the warehouse floor.
Areas have optional capacity limits and a blockable flag used by the
rule engine (Task #6) to gate forklift entry.
"""

from __future__ import annotations


class Area:
    """An axis-aligned rectangular area on the warehouse floor."""

    def __init__(self, name: str, x_min: float, x_max: float,
                 y_min: float, y_max: float, capacity: int | None = None):
        self.name = name
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max

        # Capacity: max forklifts allowed simultaneously. None = unlimited (ShelvesArea).
        self.capacity: int | None = capacity

        # Manual block override — rule engine sets this (e.g. door closed → LoadingArea blocked).
        self.is_blocked: bool = False

        # Pallet count — set externally by pallet flow logic (Task #6).
        self.pallet_count: int = 0

        # Occupancy: forklift IDs currently inside.
        self._occupants: set[int] = set()

        # Dwell tracking: forklift_id → entry sim_time.
        self._entry_times: dict[int, float] = {}

        # Cumulative traffic counters.
        self._entry_count: int = 0
        self._exit_count: int = 0

    # ── Geometry ─────────────────────────────────────────────────────────────

    def contains(self, x: float, y: float) -> bool:
        return (self.x_min <= x <= self.x_max and
                self.y_min <= y <= self.y_max)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x_min + self.x_max) / 2.0,
                (self.y_min + self.y_max) / 2.0)

    def random_point(self, rng) -> tuple[float, float]:
        """Return a random (x, y) inside the area using the given RNG."""
        x = rng.uniform(self.x_min + 0.5, self.x_max - 0.5)
        y = rng.uniform(self.y_min + 0.5, self.y_max - 0.5)
        return (x, y)

    # ── Occupancy ────────────────────────────────────────────────────────────

    @property
    def occupancy(self) -> int:
        return len(self._occupants)

    @property
    def occupant_ids(self) -> set[int]:
        return set(self._occupants)

    @property
    def is_full(self) -> bool:
        """True if capacity is set and current occupancy has reached it."""
        if self.capacity is None:
            return False
        return len(self._occupants) >= self.capacity

    # ── Traffic counters ─────────────────────────────────────────────────────

    @property
    def transition_count(self) -> int:
        """Total entries + exits since simulation start."""
        return self._entry_count + self._exit_count

    def update_occupant(self, fl_id: int, x: float, y: float, sim_time: float):
        """Call each frame per forklift. Tracks enter/exit, dwell, and counters."""
        inside = self.contains(x, y)
        was_inside = fl_id in self._occupants

        if inside and not was_inside:
            self._occupants.add(fl_id)
            self._entry_times[fl_id] = sim_time
            self._entry_count += 1
        elif not inside and was_inside:
            self._occupants.discard(fl_id)
            self._entry_times.pop(fl_id, None)
            self._exit_count += 1

    def dwell_time(self, fl_id: int, sim_time: float) -> float:
        """Seconds this forklift has been continuously inside the area."""
        entry = self._entry_times.get(fl_id)
        if entry is None:
            return 0.0
        return sim_time - entry


class AreaManager:
    """Holds all areas; updates occupancy each frame."""

    def __init__(self):
        self.areas: dict[str, Area] = {}

    def add(self, name: str, x_min: float, x_max: float,
            y_min: float, y_max: float,
            capacity: int | None = None) -> Area:
        a = Area(name, x_min, x_max, y_min, y_max, capacity=capacity)
        self.areas[name] = a
        return a

    def get(self, name: str) -> Area | None:
        return self.areas.get(name)

    def update(self, fl_id: int, x: float, y: float, sim_time: float):
        """Update all areas for one forklift's position."""
        for a in self.areas.values():
            a.update_occupant(fl_id, x, y, sim_time)

    def area_of(self, x: float, y: float) -> Area | None:
        """Return the first area that contains (x, y), or None."""
        for a in self.areas.values():
            if a.contains(x, y):
                return a
        return None

    def print_status(self, sim_time: float):
        for a in self.areas.values():
            ids = sorted(a.occupant_ids)
            dwells = [f"FL{i}={a.dwell_time(i, sim_time):.1f}s" for i in ids]
            cap = str(a.capacity) if a.capacity is not None else "∞"
            print(f"  [{a.name}] occupancy={a.occupancy}/{cap} "
                  f"full={a.is_full} blocked={a.is_blocked} "
                  f"pallets={a.pallet_count} "
                  f"transitions={a.transition_count}  {' '.join(dwells)}")
