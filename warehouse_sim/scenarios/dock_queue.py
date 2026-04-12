"""
Dock Queue scenario.

Long loading duration (20 s) with a single dock slot causes forklifts to
queue up in staging while waiting their turn. Demonstrates queue formation
and dock-capacity bottleneck detection.

Levers (from C.SCENARIO_PRESETS["dock_queue"]):
  num_forklifts    = 4
  loading_duration = 20.0   — long dock time drives queue build-up
  dock_capacity    = 1      — one slot at a time (LOADING_AREA_CAPACITY)
"""

from __future__ import annotations
from .base import Scenario
from .. import config as C


class DockQueueScenario(Scenario):
    name = "dock_queue"
    num_forklifts = 4

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self.loading_duration = 20.0   # long → queue builds naturally

    def _assign_initial_waypoints(self):
        """Open all doors; FSM routes forklifts through the full cycle."""
        self.open_all_doors()
        print(f"[{self.name}] doors open — {self.num_forklifts} forklifts "
              f"cycling with {self.loading_duration}s loading duration")
