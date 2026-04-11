"""
MetricsWriter — periodic CSV / JSON dump of zone metrics and events.

Output files are written to the directory specified at construction
(default: <project_root>/tests/output/).

Files produced:
  metrics_<timestamp>.csv   — one row per (sim_time, zone_name) snapshot
  events_<timestamp>.json   — all logged events as a JSON array

Usage
-----
    writer = MetricsWriter(zone_monitor, event_logger, output_dir="/path/to/tests/output")
    # each physics step:
    writer.tick(sim_time, dt)
    # at end or on demand:
    writer.flush()
"""

from __future__ import annotations
import csv
import json
import os
import time as wall_time
from dataclasses import asdict

from .zone_monitor import ZoneMonitor
from .event_logger import EventLogger


class MetricsWriter:
    """
    Aggregates ZoneMonitor snapshots and EventLogger entries, then writes
    them to disk on demand or at a configurable interval.

    Parameters
    ----------
    zone_monitor : ZoneMonitor
    event_logger : EventLogger
    output_dir : str
        Directory where output files are written. Created if absent.
    flush_interval : float
        Minimum seconds of sim time between automatic flushes (0 = manual only).
    snapshot_interval : float
        Minimum seconds of sim time between zone snapshot rows in the CSV.
    """

    def __init__(
        self,
        zone_monitor: ZoneMonitor,
        event_logger: EventLogger,
        output_dir: str = "/home/ubuntu/isaac_sim_samples/isaac-sim-project/tests/output",
        flush_interval: float = 30.0,
        snapshot_interval: float = 1.0,
    ):
        self._zm = zone_monitor
        self._el = event_logger
        self._output_dir = output_dir
        self._flush_interval = flush_interval
        self._snapshot_interval = snapshot_interval

        os.makedirs(output_dir, exist_ok=True)

        # Unique timestamp suffix shared across both files for this run
        self._ts = wall_time.strftime("%Y%m%d_%H%M%S")

        # Pending CSV rows: list of dicts
        self._pending_rows: list[dict] = []
        self._last_snapshot_t: float = -999.0
        self._last_flush_t: float = -999.0

    # ── Public API ────────────────────────────────────────────────────────────

    def tick(self, sim_time: float, dt: float) -> None:
        """
        Call each physics step after ZoneMonitor.tick().

        Appends snapshot rows at the configured interval and auto-flushes
        if flush_interval has elapsed.
        """
        if sim_time - self._last_snapshot_t >= self._snapshot_interval:
            self._capture_snapshot(sim_time)
            self._last_snapshot_t = sim_time

        if (self._flush_interval > 0 and
                sim_time - self._last_flush_t >= self._flush_interval):
            self.flush()
            self._last_flush_t = sim_time

    def flush(self) -> tuple[str, str]:
        """
        Write pending CSV rows and all events to disk.

        Returns
        -------
        (csv_path, json_path)
        """
        csv_path = self._write_csv()
        json_path = self._write_json()
        return csv_path, json_path

    # ── Internal ─────────────────────────────────────────────────────────────

    def _capture_snapshot(self, sim_time: float) -> None:
        for name, snap in self._zm.all_snapshots().items():
            row = {
                "sim_time": round(sim_time, 3),
                "zone": name,
                "forklift_count": snap.forklift_count,
                "avg_speed": round(snap.avg_speed, 4),
                "entry_count": snap.entry_count,
                "exit_count": snap.exit_count,
                "max_occupancy": snap.max_occupancy,
                "occupancy_seconds": round(snap.occupancy_seconds, 2),
                "max_dwell": round(snap.max_dwell, 2),
            }
            self._pending_rows.append(row)

    def _csv_path(self) -> str:
        return os.path.join(self._output_dir, f"metrics_{self._ts}.csv")

    def _json_path(self) -> str:
        return os.path.join(self._output_dir, f"events_{self._ts}.json")

    def _write_csv(self) -> str:
        path = self._csv_path()
        if not self._pending_rows:
            return path
        fieldnames = list(self._pending_rows[0].keys())
        file_exists = os.path.isfile(path)
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerows(self._pending_rows)
        self._pending_rows.clear()
        return path

    def _write_json(self) -> str:
        path = self._json_path()
        events = self._el.all_events()
        data = [
            {
                "type": e.type,
                "sim_time": round(e.sim_time, 3),
                "payload": e.payload,
            }
            for e in events
        ]
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return path
