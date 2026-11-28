"""Instant formation deploy for Clash of Critters (see README.md)."""

from .deployer import BATTLE, DeployResult, QuickDeployer, cell_for
from .errors import (
    GameNotRunning,
    QuickDeployError,
    RootUnavailable,
    UnknownTatari,
    UnsupportedBuild,
    UnsupportedLayout,
)
from .mapping import TatariMap

__all__ = [
    "BATTLE",
    "DeployResult",
    "GameNotRunning",
    "QuickDeployError",
    "QuickDeployer",
    "RootUnavailable",
    "TatariMap",
    "UnknownTatari",
    "UnsupportedBuild",
    "UnsupportedLayout",
    "cell_for",
]
