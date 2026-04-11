"""
RuleEngine: per-step orchestrator for FSM transitions and constraint enforcement.

Called once per physics step BEFORE forklift movement. It:
  1. Evaluates FSM transitions for every forklift
  2. On transition, sets new waypoints appropriate for the next state
  3. Enforces hard constraints (door closed → block LOADING entry)
  4. Handles pallet pickup/drop side-effects
  5. Emits print-based events (monitoring layer hooks in here later)
"""

from __future__ import annotations

from .. import config as C
from .. import waypoints as wp
from ..models.forklift    import Forklift
from ..models.loading_door import LoadingDoor
from ..models.pallet      import Pallet, LOC_FORKLIFT, LOC_DOCK
from ..areas              import AreaManager
from ..shelves            import ShelfMap
from .forklift_fsm        import evaluate_transition
from .queue_manager       import QueueManager
from .pallet_flow         import assign_pallet, release_pallet


class RuleEngine:
    """Stateless per-step rule evaluator owned by the Scenario."""

    def __init__(self,
                 forklifts:   list[Forklift],
                 doors:       list[LoadingDoor],
                 pallets:     list[Pallet],
                 area_mgr:    AreaManager,
                 queue_mgr:   QueueManager,
                 shelf_map:   ShelfMap,
                 stage,
                 assets_root: str | None = None):
        self.forklifts  = forklifts
        self.doors      = doors
        self.pallets    = pallets
        self.area_mgr   = area_mgr
        self.queue_mgr  = queue_mgr
        self.shelf_map  = shelf_map
        self.stage       = stage
        self.assets_root = assets_root

        # One pallet per forklift (index = forklift id); None when unloaded
        # Populated lazily as forklifts pick up pallets
        self._fl_pallet: dict[int, Pallet | None] = {
            fl.id: None for fl in forklifts
        }

    # ── Public API ───────────────────────────────────────────────────────────

    def tick(self, dt: float) -> None:
        """Evaluate transitions for all forklifts and apply side-effects."""
        for fl in self.forklifts:
            new_state = evaluate_transition(
                fl, self.doors, self.area_mgr, self.queue_mgr
            )
            if new_state is not None and new_state != fl.state:
                self._apply_transition(fl, fl.state, new_state)

    # ── Transition side-effects ───────────────────────────────────────────────

    def _apply_transition(self, fl: Forklift,
                          old_state: str, new_state: str) -> None:
        print(f"[RuleEngine] FL{fl.id}: {old_state} → {new_state}")
        fl.state = new_state
        fl.state_timer = self._timer_for(new_state)
        self._set_waypoints(fl, new_state)
        self._handle_load_change(fl, old_state, new_state)

    def _timer_for(self, state: str) -> float:
        if state == C.STATE_PICKUP_AT_SHELVES:
            return C.PICKUP_DURATION
        if state == C.STATE_LOADING:
            return C.LOADING_DURATION
        return 0.0

    def _set_waypoints(self, fl: Forklift, state: str) -> None:
        """Assign waypoints appropriate for the new state."""
        sm = self.shelf_map

        if state == C.STATE_PICKUP_AT_SHELVES:
            pts = wp.get_pickup_points(sm)
            if pts:
                # Nearest pickup point to current forklift position
                target = min(pts, key=lambda p: abs(p[0] - fl.pos[0]))
                route = wp.aisle_route(
                    (fl.pos[0], fl.pos[1]), target, sm
                )
                fl.set_waypoints(route)

        elif state == C.STATE_MOVE_TO_STAGING:
            gate = self._preferred_gate(fl)
            pts = wp.get_staging_hold_positions()
            dest = pts[gate] if gate < len(pts) else pts[0]
            fl.set_waypoints([dest])

        elif state == C.STATE_WAIT_IN_STAGING:
            gate = self._preferred_gate(fl)
            pts = wp.get_staging_hold_positions()
            dest = pts[gate] if gate < len(pts) else pts[0]
            fl.set_waypoints([dest])
            fl.speed = 0.0

        elif state == C.STATE_MOVE_TO_LOADING:
            gate = self._preferred_gate(fl)
            dest = wp.get_dock_service_position(gate)
            fl.set_waypoints([dest])

        elif state == C.STATE_WAIT_AT_DOCK_QUEUE:
            gate = self._preferred_gate(fl)
            pts = wp.get_dock_queue_spots()
            dest = pts[gate] if gate < len(pts) else pts[0]
            fl.set_waypoints([dest])
            fl.speed = 0.0

        elif state == C.STATE_LOADING:
            fl.speed = 0.0

        elif state == C.STATE_RETURNING:
            gate = self._preferred_gate(fl)
            route = wp.get_return_path(gate, sm)
            fl.set_waypoints(route)

        elif state == C.STATE_IDLE:
            fl.speed = 0.0
            fl.set_waypoints([])

    def _handle_load_change(self, fl: Forklift,
                            old_state: str, new_state: str) -> None:
        """Handle pallet pickup/drop on specific state transitions."""
        stage = self.stage

        # Pickup complete: assign a pallet to the forklift
        if (old_state == C.STATE_PICKUP_AT_SHELVES and
                new_state == C.STATE_MOVE_TO_STAGING):
            pallet = self._find_free_pallet()
            if pallet:
                assign_pallet(fl, pallet, stage, assets_root=self.assets_root)
                self._fl_pallet[fl.id] = pallet

        # Loading complete: drop the pallet at the dock
        if (old_state == C.STATE_LOADING and
                new_state == C.STATE_RETURNING):
            pallet = self._fl_pallet.get(fl.id)
            if pallet:
                drop_xy = wp.get_dock_service_position(
                    self._preferred_gate(fl)
                )
                release_pallet(fl, pallet, stage,
                               drop_location=LOC_DOCK, drop_xy=drop_xy)
                self._fl_pallet[fl.id] = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _preferred_gate(self, fl: Forklift) -> int:
        """Gate index whose X is nearest to the forklift's current X."""
        gate_xs = [C.WAREHOUSE_CX + off for off in C.GATE_OFFSETS]
        return min(range(len(gate_xs)), key=lambda i: abs(gate_xs[i] - fl.pos[0]))

    def _find_free_pallet(self) -> Pallet | None:
        """Return the first pallet not currently assigned to any forklift."""
        for p in self.pallets:
            if p.assigned_forklift_id is None and p.location != LOC_FORKLIFT:
                return p
        return None
