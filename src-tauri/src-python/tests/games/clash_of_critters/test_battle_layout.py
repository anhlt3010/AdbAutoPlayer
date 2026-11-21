"""Tests for the battle preparation screen layout."""

import pytest
from adb_auto_player.games.clash_of_critters.battle_layout import (
    cell_center,
    tray_slots,
)
from adb_auto_player.models.geometry import Point


def test_cell_center_corners() -> None:
    assert cell_center(1, 1) == Point(300, 490)
    assert cell_center(5, 5) == Point(780, 970)


@pytest.mark.parametrize("row, col", [(0, 1), (1, 6), (6, 1), (1, 0)])
def test_cell_center_out_of_range(row: int, col: int) -> None:
    with pytest.raises(ValueError):
        cell_center(row, col)


def test_tray_slots_count_and_order() -> None:
    slots = tray_slots()
    assert len(slots) == 12
    assert slots[0] == Point(110, 1285)
    assert slots[6] == Point(110, 1480)
