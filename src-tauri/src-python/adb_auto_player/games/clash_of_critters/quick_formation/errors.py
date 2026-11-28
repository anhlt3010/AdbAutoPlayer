"""Exceptions raised by the quick formation module."""


class QuickDeployError(RuntimeError):
    """Base class: the quick deploy cannot be used; callers may fall back to dragging."""


class GameNotRunning(QuickDeployError):
    """The game process was not found."""


class RootUnavailable(QuickDeployError):
    """The device shell has no root (su) or /proc/<pid>/mem is not accessible."""


class UnsupportedBuild(QuickDeployError):
    """The game build does not look like the one this module was verified against."""


class UnsupportedLayout(QuickDeployError):
    """The battle preparation screen is not one this module has verified."""


class UnknownTatari(QuickDeployError):
    """A formation unit has no game species id (see the mapping override file)."""
