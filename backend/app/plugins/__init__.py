"""Plugin registry. To add a module: subclass Plugin in a new file and list it here."""

from .ball_forecast import BallForecastPlugin
from .base import Insight, MatchState, Plugin
from .director import DirectorPlugin
from .momentum import MomentumPlugin
from .overlays import OverlaysPlugin
from .pass_quality import PassQualityPlugin
from .speed_metrics import SpeedMetricsPlugin
from .stats import StatsPlugin

PLUGIN_CLASSES: dict[str, type[Plugin]] = {
    cls.name: cls
    for cls in (StatsPlugin, PassQualityPlugin, SpeedMetricsPlugin, BallForecastPlugin, MomentumPlugin, DirectorPlugin, OverlaysPlugin)
}


def describe_plugins() -> list[dict]:
    return [
        {"name": c.name, "description": c.description, "default_enabled": c.default_enabled}
        for c in PLUGIN_CLASSES.values()
    ]


__all__ = ["PLUGIN_CLASSES", "Insight", "MatchState", "Plugin", "describe_plugins"]
