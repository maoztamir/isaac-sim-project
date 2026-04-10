"""
LoadingDoor: wraps one dock gate with open/close state and visual updates.

Owns no USD prims of its own — the gate is spawned by ih.spawn_gate() at
scene-build time. This class only drives the panel visibility state.
"""

from __future__ import annotations

from .. import config as C
from .. import isaac_helpers as ih


class LoadingDoor:
    def __init__(self, gate_idx: int, is_open: bool = False):
        self.gate_idx = gate_idx
        self.is_open = is_open

    # ── Instant open/close ───────────────────────────────────────────────────

    def open(self, stage) -> None:
        ih.open_gate(stage, self.gate_idx, C.PANEL_N)
        self.is_open = True

    def close(self, stage) -> None:
        ih.close_gate(stage, self.gate_idx, C.PANEL_N)
        self.is_open = False

    # ── Animated variants (async) ────────────────────────────────────────────

    async def open_animated(self, stage, duration: float = 1.2) -> None:
        await ih.open_gate_animated(stage, self.gate_idx, C.PANEL_N, duration=duration)
        self.is_open = True

    async def close_animated(self, stage, duration: float = 1.2) -> None:
        await ih.close_gate_animated(stage, self.gate_idx, C.PANEL_N, duration=duration)
        self.is_open = False

    def __repr__(self) -> str:
        return f"LoadingDoor(gate={self.gate_idx}, {'OPEN' if self.is_open else 'CLOSED'})"
