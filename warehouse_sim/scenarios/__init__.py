from .base import Scenario
from .dock_queue import DockQueueScenario
from .loading_pause import LoadingPauseScenario
from .area_buildup import AreaBuildUpScenario
from .aisle_congestion import AisleCongestionScenario

PRESETS = {
    "dock_queue":       DockQueueScenario,
    "loading_pause":    LoadingPauseScenario,
    "area_buildup":     AreaBuildUpScenario,
    "aisle_congestion": AisleCongestionScenario,
}
