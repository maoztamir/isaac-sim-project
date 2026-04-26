"""
DoorCycleScenario — periodic door open/close to test door-status detection.

Three loading dock gates cycle independently with staggered phase offsets.
Three forklifts run the normal FSM: they queue when a door closes mid-approach
and proceed when it re-opens.

"Empty open" mode
-----------------
When a door transitions from CLOSED → OPEN there is a EMPTY_OPEN_CHANCE
probability that the gate opens but its dock slot is blocked (sentinel -1).
Forklifts see the door as open but cannot claim that slot, so the dock stays
empty.  This exercises the detection case: door open, no forklift present.

Knobs
-----
OPEN_DURATION      seconds each door stays open
CLOSED_DURATION    seconds each door stays closed
EMPTY_OPEN_CHANCE  0.0 – 1.0 probability a CLOSED→OPEN transition is "empty"
"""

from __future__ import annotations

from .base import Scenario
from .. import config as C

OPEN_DURATION     = 20.0   # seconds door stays open
CLOSED_DURATION   = 10.0   # seconds door stays closed
EMPTY_OPEN_CHANCE = 0.4    # probability a newly-opened door stays unserviced
LOG_INTERVAL      = 5.0    # seconds between telemetry lines


class DoorCycleScenario(Scenario):
    name = "door_cycle"
    num_forklifts = 3

    def __init__(self, seed: int = 42):
        super().__init__(seed)
        self._door_timers: list[float] = []
        self._log_timer:   float       = 0.0
        # Gates currently in "empty open" state (door open, dock slot blocked)
        self._empty_gates: set[int]    = set()

    # ── Initial state ────────────────────────────────────────────────────────

    def _assign_initial_waypoints(self):
        """Stagger phases so the three gates are never all in the same state."""
        initial = [
            (True,  OPEN_DURATION),           # door 0: open now
            (False, CLOSED_DURATION * 0.5),   # door 1: closed, toggles first
            (True,  OPEN_DURATION   * 0.7),   # door 2: open, toggles second
        ]
        self._door_timers = []
        for i, (is_open, timer) in enumerate(initial):
            if is_open:
                self.doors[i].open(self.stage)
                if self.rng.random() < EMPTY_OPEN_CHANCE:
                    if self._block_dock_slot(i):
                        self._empty_gates.add(i)
                        print(f"[{self.name}] door {i} → OPEN (EMPTY)"
                              f"  (next toggle in {timer:.1f} s)")
                    else:
                        print(f"[{self.name}] door {i} → OPEN"
                              f"  (next toggle in {timer:.1f} s)")
                else:
                    print(f"[{self.name}] door {i} → OPEN"
                          f"  (next toggle in {timer:.1f} s)")
            else:
                self.doors[i].close(self.stage)
                print(f"[{self.name}] door {i} → CLOSED"
                      f"  (next toggle in {timer:.1f} s)")
            self._door_timers.append(timer)

    # ── Per-frame logic ───────────────────────────────────────────────────────

    def on_step(self, dt: float):
        self._tick_doors(dt)
        self._tick_status_log(dt)

    def _tick_doors(self, dt: float):
        for i, door in enumerate(self.doors):
            self._door_timers[i] -= dt
            if self._door_timers[i] > 0.0:
                continue

            if door.is_open:
                self._close_door(i, door)
            else:
                self._open_door(i, door)

    def _open_door(self, i: int, door) -> None:
        door.open(self.stage)
        self._door_timers[i] = OPEN_DURATION

        if self.rng.random() < EMPTY_OPEN_CHANCE and self._block_dock_slot(i):
            self._empty_gates.add(i)
            print(f"[{self.name}] t={self.sim_time:.1f}s  "
                  f"door {i}  CLOSED → OPEN (EMPTY — dock slot blocked, "
                  f"no forklift for {OPEN_DURATION:.0f} s)")
        else:
            print(f"[{self.name}] t={self.sim_time:.1f}s  "
                  f"door {i}  CLOSED → OPEN  (stays open {OPEN_DURATION:.0f} s)")

    def _close_door(self, i: int, door) -> None:
        door.close(self.stage)
        self._door_timers[i] = CLOSED_DURATION

        if i in self._empty_gates:
            self._empty_gates.discard(i)
            self._unblock_dock_slot(i)
            print(f"[{self.name}] t={self.sim_time:.1f}s  "
                  f"door {i}  OPEN (EMPTY) → CLOSED  "
                  f"(stays closed {CLOSED_DURATION:.0f} s)")
        else:
            print(f"[{self.name}] t={self.sim_time:.1f}s  "
                  f"door {i}  OPEN → CLOSED  "
                  f"(stays closed {CLOSED_DURATION:.0f} s)")

    # ── Dock-slot helpers ─────────────────────────────────────────────────────

    def _block_dock_slot(self, gate_idx: int) -> bool:
        """Reserve gate's dock slot with sentinel -1 so no forklift can claim it.

        Returns False (and leaves the slot untouched) if a forklift already
        occupies it — in that case the door opens normally instead of empty.
        """
        dock_slots = self.queue_mgr.slots_of_type("dock")
        if gate_idx < len(dock_slots) and dock_slots[gate_idx].is_free:
            dock_slots[gate_idx].assign(-1)
            return True
        return False

    def _unblock_dock_slot(self, gate_idx: int) -> None:
        """Release the sentinel -1 reservation so forklifts can use the slot again."""
        dock_slots = self.queue_mgr.slots_of_type("dock")
        if gate_idx < len(dock_slots):
            slot = dock_slots[gate_idx]
            if slot.occupied_by == -1:
                slot.release()

    # ── Telemetry ─────────────────────────────────────────────────────────────

    def _tick_status_log(self, dt: float):
        self._log_timer += dt
        if self._log_timer < LOG_INTERVAL:
            return
        self._log_timer = 0.0

        door_states = "  ".join(
            f"door_{i}={'OPEN(E)' if i in self._empty_gates else 'OPEN   ' if d.is_open else 'CLOSED '}"
            for i, d in enumerate(self.doors)
        )
        fl_states = "  ".join(
            f"FL{fl.id}={fl.state}" for fl in self.forklifts
        )
        print(f"[{self.name}] t={self.sim_time:.0f}s | {door_states} | {fl_states}")
