"""
ZoneMonitor — per-area metrics snapshot updated each physics step.

Tracks for each named zone:
  - forklift_count         current number of forklifts inside
  - avg_speed              mean speed of occupants (m/s)
  - entry_count            cumulative entries since reset
  - exit_count             cumulative exits since reset
  - max_occupancy          peak occupancy seen since reset
  - occupancy_seconds      total forklift-seconds spent inside (area under curve)
  - max_dwell              longest continuous dwell of any forklift (seconds)
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ZoneSnapshot:
    """Metrics for one zone at the time of the last tick."""
    name: str
    forklift_count: int = 0
    avg_speed: float = 0.0
    entry_count: int = 0
    exit_count: int = 0
    max_occupancy: int = 0
    occupancy_seconds: float = 0.0
    max_dwell: float = 0.0


class ZoneMonitor:
    """
    Wraps an AreaManager and accumulates per-area metrics each physics step.

    Parameters
    ----------
    zone_manager : AreaManager
        The AreaManager instance (from warehouse_sim/areas.py).
    """

    def __init__(self, zone_manager):
        self._zm = zone_manager
        self._areas_attr = "areas"
        # Per-zone snapshots — built from zone names on first tick
        self._snapshots: dict[str, ZoneSnapshot] = {}
        # Previous occupancy sets to detect enter/exit events
        self._prev_occupants: dict[str, set[int]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def tick(self, forklifts: list, sim_time: float, dt: float) -> None:
        """
        Update all zone metrics for the current physics step.

        Parameters
        ----------
        forklifts : list
            List of forklift objects that have .id, .pos, .speed attributes.
        sim_time : float
            Current simulation time in seconds.
        dt : float
            Physics step duration in seconds.
        """
        # Build speed lookup: fl_id -> speed
        speed_by_id: dict[int, float] = {}
        for fl in forklifts:
            speed_by_id[fl.id] = getattr(fl, "speed", 0.0)

        for name, zone in getattr(self._zm, self._areas_attr).items():
            snap = self._snapshots.setdefault(name, ZoneSnapshot(name=name))
            prev = self._prev_occupants.setdefault(name, set())

            current = zone.occupant_ids  # returns a copy

            # Entry / exit delta
            entered = current - prev
            exited = prev - current
            snap.entry_count += len(entered)
            snap.exit_count += len(exited)

            # Current count + peak
            snap.forklift_count = len(current)
            if snap.forklift_count > snap.max_occupancy:
                snap.max_occupancy = snap.forklift_count

            # Average speed of occupants
            if current:
                speeds = [speed_by_id.get(fid, 0.0) for fid in current]
                snap.avg_speed = sum(speeds) / len(speeds)
            else:
                snap.avg_speed = 0.0

            # Area under occupancy curve (forklift-seconds)
            snap.occupancy_seconds += snap.forklift_count * dt

            # Max dwell — longest any occupant has been continuously inside
            for fid in current:
                dwell = zone.dwell_time(fid, sim_time)
                if dwell > snap.max_dwell:
                    snap.max_dwell = dwell

            self._prev_occupants[name] = current

    def snapshot(self, zone_name: str) -> ZoneSnapshot | None:
        """Return the latest snapshot for a named zone, or None."""
        return self._snapshots.get(zone_name)

    def all_snapshots(self) -> dict[str, ZoneSnapshot]:
        """Return a dict copy of all current snapshots."""
        return dict(self._snapshots)

    def reset(self) -> None:
        """Reset all cumulative counters (entry/exit/max/dwell) but keep zone names."""
        for snap in self._snapshots.values():
            snap.entry_count = 0
            snap.exit_count = 0
            snap.max_occupancy = snap.forklift_count  # carry current count as new baseline
            snap.occupancy_seconds = 0.0
            snap.max_dwell = 0.0
        self._prev_occupants.clear()

    def areas(self) -> dict:
        """Return the underlying areas dict from the AreaManager."""
        return self._zm.areas

    def print_summary(self) -> None:
        """Print a one-line summary per zone to stdout."""
        for snap in self._snapshots.values():
            print(
                f"  [ZoneMonitor] {snap.name:20s}  "
                f"cnt={snap.forklift_count}  "
                f"avg_spd={snap.avg_speed:.2f}m/s  "
                f"entries={snap.entry_count}  exits={snap.exit_count}  "
                f"peak={snap.max_occupancy}  "
                f"occ-s={snap.occupancy_seconds:.1f}  "
                f"max_dwell={snap.max_dwell:.1f}s"
            )
