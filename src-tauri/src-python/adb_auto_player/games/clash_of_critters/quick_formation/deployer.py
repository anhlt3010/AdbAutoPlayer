"""High level quick deploy of a formation (drop-in replacement for drag and drop)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .errors import QuickDeployError, UnsupportedLayout
from .mapping import TatariMap
from .memory import PACKAGE, DeviceMemory, Shell
from .patcher import MAX_CELLS, FormationPatcher

# Verified on the normal battle preparation screen (5 x 5 field): the game's grid has
# x = column (1 = left) and y = 6 - row (y 5 is the top row).
BATTLE = "battle"
_FIELD = 5


@dataclass(frozen=True)
class DeployResult:
    """What a deployment left on the field (same fields as the drag and drop result).

    Attributes:
        count: Tatari on the field according to the on-screen counter; 0 when the counter
            could not be read (``verified`` is then False).
        needed: Cells of the formation.
        blocked: Never set by the quick deploy; kept so the old result type can be replaced.
        verified: The counter was read after the deploy. Without a counter reader the
            result can only say that the patch was installed and the button pressed.
    """

    count: int
    needed: int
    blocked: bool = False
    verified: bool = True

    @property
    def complete(self) -> bool:
        """Whether every cell has a tatari (False when the result is not verified)."""
        return self.verified and not self.blocked and self.count >= self.needed


def cell_for(row: int, col: int, layout: str = BATTLE) -> tuple[int, int]:
    """Game grid ``(x, y)`` of a formation cell (1-based row from the top, col from the left)."""
    if layout != BATTLE:
        raise UnsupportedLayout(
            f"layout {layout!r} has not been verified (only {BATTLE!r})"
        )
    if not (1 <= row <= _FIELD and 1 <= col <= _FIELD):
        raise ValueError(f"cell ({row}, {col}) is outside the field")
    return col, _FIELD + 1 - row


def _field(unit, name: str):
    return unit[name] if isinstance(unit, dict) else getattr(unit, name)


class QuickDeployer:
    """Deploys a whole formation with one press of the game's Quick Deploy button.

    Args:
        shell: Runs a device shell command and returns its output, for example
            ``lambda cmd: game.device.d.shell(cmd, encoding=None)``.
        press_quick_deploy: Taps the game's "Triển Khai Nhanh" button.
        read_deployed_count: Optional; returns the "Đã triển khai: n/15" counter (or None).
        mapping: Tatari id to game species id (default: the bundled table + override file).
        state_dir: Where the original code is remembered (default: not saved to disk).
        restore_after: Put the original Quick Deploy back after each deploy (recommended: the
            real button then behaves as the game intended).
        settle_seconds: Wait after the press before the counter is read.
        su: Command prefix that runs a command as root.
    """

    def __init__(
        self,
        shell: Shell,
        press_quick_deploy: Callable[[], None],
        read_deployed_count: Callable[[], int | None] | None = None,
        mapping: TatariMap | None = None,
        state_dir: Path | None = None,
        restore_after: bool = True,
        settle_seconds: float = 0.5,
        su: str = "su -c",
        package: str = PACKAGE,
    ) -> None:
        self._memory = DeviceMemory(shell, package=package, su=su)
        self._patcher = FormationPatcher(self._memory, state_dir)
        self._press = press_quick_deploy
        self._read_count = read_deployed_count
        self.mapping = mapping or TatariMap()
        self._restore_after = restore_after
        self._settle = settle_seconds

    def cells(
        self, units: Iterable, layout: str = BATTLE
    ) -> list[tuple[int, int, int]]:
        """``(tid, x, y)`` for each formation unit (raises UnknownTatari / UnsupportedLayout)."""
        cells = []
        for unit in units:
            x, y = cell_for(int(_field(unit, "row")), int(_field(unit, "col")), layout)
            cells.append((self.mapping.tid(str(_field(unit, "tatari_id"))), x, y))
        if len(cells) > MAX_CELLS:
            cells = cells[:MAX_CELLS]
        if len({tid for tid, _, _ in cells}) != len(cells):
            raise QuickDeployError("a species appears twice in the formation")
        return cells

    def deploy(self, units: Iterable, layout: str = BATTLE) -> DeployResult:
        """Put the formation on the field.

        Args:
            units: Objects (or dicts) with ``row``, ``col`` and ``tatari_id``, for example
                ``Formation.units``.
            layout: Screen kind; only ``"battle"`` is supported so far.

        Returns:
            The deployment result.

        Raises:
            QuickDeployError: The quick deploy cannot be used (callers can fall back to
                dragging); the original Quick Deploy is restored first.
        """
        cells = self.cells(units, layout)
        started = time.monotonic()
        logging.info(f"Quick deploy: chuẩn bị xếp {len(cells)} quân vào sân.")
        self._patcher.install(cells)
        logging.info("Quick deploy: đã ghi đội hình vào game, bấm Triển Khai Nhanh.")
        try:
            self._press()
            time.sleep(self._settle)
        finally:
            if self._restore_after:
                try:
                    self._patcher.restore()
                except Exception as error:
                    logging.warning(
                        f"Could not restore the original Quick Deploy: {error!r}"
                    )
        count = self._read_count() if self._read_count else None
        logging.info(
            f"Quick deploy of {len(cells)} units in {time.monotonic() - started:.1f} s, counter {count}."
        )
        if count is None:
            return DeployResult(0, len(cells), verified=False)
        return DeployResult(count, len(cells))

    def restore(self) -> bool:
        """Put the original Quick Deploy back (True if an original was known)."""
        return self._patcher.restore()

    def is_original(self) -> bool:
        """True when the game's Quick Deploy currently has its original code."""
        return self._patcher.is_original()
