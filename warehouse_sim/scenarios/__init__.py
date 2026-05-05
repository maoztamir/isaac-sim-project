from .base                     import Scenario
from .dock_queue               import DockQueueScenario
from .dock_queue_pedestrian    import DockQueuePedestrianScenario
from .loading_pause            import LoadingPauseScenario
from .area_buildup             import AreaBuildUpScenario
from .aisle_congestion         import AisleCongestionScenario
from .showcase                 import ShowcaseScenario
from .door_cycle               import DoorCycleScenario
from .mixed_floor              import MixedFloorScenario

PRESETS = {
    "dock_queue":              DockQueueScenario,
    "dock_queue_pedestrian":   DockQueuePedestrianScenario,
    "loading_pause":           LoadingPauseScenario,
    "area_buildup":            AreaBuildUpScenario,
    "aisle_congestion":        AisleCongestionScenario,
    "showcase":                ShowcaseScenario,
    "door_cycle":              DoorCycleScenario,
    "mixed_floor":             MixedFloorScenario,
}


def get_scenario_class(name):
    """Return a callable(seed) -> Scenario for the given scenario name.

    Resolution order:
      1. Python subclasses in PRESETS (existing behaviour — unchanged)
      2. Config-dict entries in config.CONFIG_SCENARIOS (new in Task 11)
      3. KeyError with a helpful message listing both sets

    For PRESETS entries the return value is the class itself.
    For CONFIG_SCENARIOS entries it is a thin factory function so callers
    can use it the same way: ``cls = get_scenario_class(name); s = cls(seed=42)``.
    """
    if name in PRESETS:
        return PRESETS[name]

    from .. import config as C
    if name in C.CONFIG_SCENARIOS:
        cfg = C.CONFIG_SCENARIOS[name]
        from .config_scenario import ConfigScenario

        def _factory(seed=42):
            return ConfigScenario(cfg, seed=seed)

        _factory.__name__ = f"ConfigScenario[{name}]"
        return _factory

    all_names = list(PRESETS.keys()) + list(C.CONFIG_SCENARIOS.keys())
    raise KeyError(
        f"Unknown scenario '{name}'. Available: {all_names}"
    )
