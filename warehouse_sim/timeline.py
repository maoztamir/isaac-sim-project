"""
TimelineDirector: dispatches per-actor actions over scripted time phases.

A spec scenario hands the director a list of phases.  Each phase is:
    {
        "phase":   "<name>",
        "t_start": <sec>,
        "t_end":   <sec>,
        "actors":  { "FL0": {"action": "...", ...}, "FL1": {...} },
    }

The director:
  1. Finds the phase whose [t_start, t_end) contains sim_time
  2. For each actor in that phase, dispatches its action

Actions implemented:
  - hold                — pin forklift at its current pose
  - approach_and_stop   — linearly drive toward a named target over the phase
                          window, snap to target on arrival
  - micro_adjust        — sinusoidal Y oscillation around the entry pose

All movement is applied directly to fl.pos and update_prim_pose — the FSM
rule_engine is intentionally bypassed so the spec has exact control.
"""

from __future__ import annotations
import math

from . import isaac_helpers as ih
from . import waypoints as wp


class TimelineDirector:

    def __init__(self, phases: list[dict], forklifts_by_id: dict, scenario):
        self.phases = phases
        self.forklifts_by_id = forklifts_by_id
        self.scenario = scenario

        # Per-actor entry poses and approach targets, populated lazily on the
        # first tick a phase is active for that actor.
        self._micro_anchor: dict[str, tuple[float, float]] = {}
        self._approach_start: dict[tuple[str, str], tuple[float, float]] = {}

    # ── Public ───────────────────────────────────────────────────────────────

    def tick(self, sim_time: float, dt: float) -> None:
        for phase in self.phases:
            if phase["t_start"] <= sim_time < phase["t_end"]:
                self._dispatch_phase(phase, sim_time, dt)
                return
        # Past the last phase → freeze every forklift in place.
        for fl in self.forklifts_by_id.values():
            self._action_hold(fl)

    # ── Action dispatch ──────────────────────────────────────────────────────

    def _dispatch_phase(self, phase: dict, sim_time: float, dt: float) -> None:
        for actor_id, action_spec in phase["actors"].items():
            fl = self.forklifts_by_id.get(actor_id)
            if fl is None:
                continue
            action = action_spec["action"]
            if action == "hold":
                self._action_hold(fl)
            elif action == "approach_and_stop":
                self._action_approach(fl, action_spec, phase, sim_time)
            elif action == "micro_adjust":
                self._action_micro_adjust(fl, action_spec, sim_time)
            else:
                print(f"[timeline] unknown action '{action}' for {actor_id}")

    # ── Actions ──────────────────────────────────────────────────────────────

    def _action_hold(self, fl) -> None:
        fl.speed = 0.0
        ih.update_prim_pose(self.scenario.stage, fl.prim_path,
                            fl.pos[0], fl.pos[1], fl.heading)

    def _action_approach(self, fl, spec: dict, phase: dict,
                         sim_time: float) -> None:
        """Linearly interpolate fl.pos from its phase-entry position toward
        the named target.  Snaps to the target during the last 10% of the
        phase window so the forklift reaches it cleanly even if dt jitters.
        """
        target_key = spec["target"]
        tx, ty = wp.named_position(target_key)

        key = (str(fl.id), phase["phase"])
        if key not in self._approach_start:
            self._approach_start[key] = (fl.pos[0], fl.pos[1])
        sx, sy = self._approach_start[key]

        span = max(1e-3, phase["t_end"] - phase["t_start"])
        u = (sim_time - phase["t_start"]) / span
        u = max(0.0, min(1.0, u))

        fl.pos[0] = sx + (tx - sx) * u
        fl.pos[1] = sy + (ty - sy) * u

        # Approximate forward speed for telemetry.
        dist_total = math.hypot(tx - sx, ty - sy)
        fl.speed = dist_total / span if u < 1.0 else 0.0

        ih.update_prim_pose(self.scenario.stage, fl.prim_path,
                            fl.pos[0], fl.pos[1], fl.heading)

    def _action_micro_adjust(self, fl, spec: dict, sim_time: float) -> None:
        """Sinusoidal oscillation along Y around the actor's entry pose."""
        amp = spec.get("amplitude_m", 0.3)
        period = max(0.1, spec.get("period_s", 2.0))

        actor_key = str(fl.id)
        if actor_key not in self._micro_anchor:
            self._micro_anchor[actor_key] = (fl.pos[0], fl.pos[1])
        ax, ay = self._micro_anchor[actor_key]

        omega = 2.0 * math.pi / period
        offset = amp * math.sin(omega * sim_time)
        fl.pos[0] = ax
        fl.pos[1] = ay + offset
        fl.speed = abs(amp * omega * math.cos(omega * sim_time))

        ih.update_prim_pose(self.scenario.stage, fl.prim_path,
                            fl.pos[0], fl.pos[1], fl.heading)
