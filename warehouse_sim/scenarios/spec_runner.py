"""
SpecScenario: runs a Python-dict scenario spec on top of the Scenario base.

The spec dict (see scenarios/specs/*.py) declares:
  - focus_camera : optional camera spawned and activated after build
  - scene_init   : doors, forklifts, pallets initial placement & state
  - timeline     : list of phases handled by TimelineDirector

The rule_engine is intentionally disabled — TimelineDirector is the sole
driver of forklift motion so the scripted scenario plays out exactly.
"""

from __future__ import annotations

from .base import Scenario
from .. import config as C
from .. import isaac_helpers as ih
from .. import waypoints as wp
from ..models.forklift import Forklift
from ..models.pallet import Pallet
from ..timeline import TimelineDirector


class SpecScenario(Scenario):

    def __init__(self, spec: dict, seed: int = 42):
        super().__init__(seed)
        self.spec = spec
        self.name = spec.get("name", "spec_scenario")
        self.num_forklifts = len(spec.get("scene_init", {}).get("forklifts", []))

        self.forklifts_by_id: dict[str, Forklift] = {}
        self.timeline_director: TimelineDirector | None = None

    # ── Build ────────────────────────────────────────────────────────────────

    async def build(self):
        await super().build()

        # Disable rule engine — timeline drives everything.
        self.rule_engine = None

        # Apply door states now so the scene looks correct during the
        # pre-start countdown (doors would otherwise stay closed until
        # the first physics step fires _assign_initial_waypoints).
        self._apply_door_states()

        self._spawn_focus_camera()
        self._spawn_pallets()

        phases = self.spec.get("timeline", [])
        self.timeline_director = TimelineDirector(
            phases, self.forklifts_by_id, self
        )

        print(f"[{self.name}] Spec loaded — "
              f"{len(self.forklifts_by_id)} forklifts, "
              f"{len(phases)} timeline phases.")

    # ── Override points ──────────────────────────────────────────────────────

    def setup_forklifts(self):
        """Spawn forklifts from spec.scene_init.forklifts."""
        for i, fspec in enumerate(self.spec["scene_init"]["forklifts"]):
            actor_id = fspec["id"]
            x, y = wp.named_position(fspec["position"])
            x += fspec.get("position_offset_x", 0.0)
            y += fspec.get("position_offset_y", 0.0)
            heading = fspec.get("heading_deg", 90.0)

            path = f"/World/Forklifts/forklift_{i}"
            ih.spawn_asset(self.stage, path,
                           self.assets_root + C.FORKLIFT_USD,
                           x, y, 0.0, heading)
            fl = Forklift(i, path, x, y, heading=heading)
            fl.state = fspec.get("state", C.STATE_IDLE)
            fl.state_timer = fspec.get("state_timer", 999.0)

            if fspec.get("load") == C.LOAD_LOADED:
                fl.set_load(self.stage, C.LOAD_LOADED, self.assets_root)

            self.forklifts.append(fl)
            self.forklifts_by_id[actor_id] = fl

    def _apply_door_states(self) -> None:
        """Open/close doors according to spec.scene_init.doors."""
        door_specs = {d["index"]: d["state"]
                      for d in self.spec["scene_init"].get("doors", [])}
        for i, door in enumerate(self.doors):
            state = door_specs.get(i, "closed")
            if state == "open":
                door.open(self.stage)
            else:
                door.close(self.stage)
        print(f"[{self.name}] doors: "
              f"{[(i, 'open' if d.is_open else 'closed') for i, d in enumerate(self.doors)]}")

    def _assign_initial_waypoints(self):
        self._apply_door_states()

    def on_step(self, dt: float):
        if self.timeline_director is not None:
            self.timeline_director.tick(self.sim_time, dt)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _spawn_focus_camera(self):
        cam_spec = self.spec.get("focus_camera")
        if not cam_spec:
            return
        cam_name = cam_spec.get("name", "cam_focus")
        path = f"/World/Cameras/{cam_name}"
        ih.spawn_camera(self.stage, path,
                        cam_spec["eye"], cam_spec["target"],
                        fov_deg=cam_spec.get("fov_deg", 70.0))
        print(f"[{self.name}] focus camera spawned at {path}")
        if cam_spec.get("activate", False):
            ih.set_active_camera(path)

    def _spawn_pallets(self):
        for i, pspec in enumerate(self.spec["scene_init"].get("pallets", [])):
            x, y = wp.named_position(pspec["position"])
            path = f"/World/SpecPallets/pallet_{i}"
            pallet = Pallet(i, path)
            pallet.spawn(self.stage, self.assets_root, x, y, z=0.0)
            self.pallets.append(pallet)
        print(f"[{self.name}] {len(self.pallets)} spec pallets spawned.")
