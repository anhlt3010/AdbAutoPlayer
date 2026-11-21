"""Tests for the battle preparation screen layout."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters.battle_layout import (
    ALL_FILTER_POINT,
    ELEMENT_FILTER_POINTS,
    cell_center,
    find_card_lefts,
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


# --- card columns ------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
SPACING_TOLERANCE = 3


def _screen(name: str) -> np.ndarray:
    image = cv2.imread(str(DATA_DIR / name))
    assert image is not None
    return image


def test_find_card_lefts_unscrolled_tray() -> None:
    lefts = find_card_lefts(_screen("prep_screen_cleared.png"))
    # The 6th card is cut off by the tray edge and is not a full card.
    assert len(lefts) == 5
    for found, expected in zip(lefts, (30, 208, 386, 564, 742), strict=True):
        assert abs(found - expected) <= SPACING_TOLERANCE


def test_find_card_lefts_follows_a_scrolled_tray() -> None:
    lefts = find_card_lefts(_screen("prep_screen_scrolled.png"))
    # After scrolling, the cards are no longer on the unscrolled slot grid, and the
    # cards clipped at both tray edges are left out.
    assert len(lefts) == 4
    assert abs(lefts[0] - 170) <= SPACING_TOLERANCE
    steps = [b - a for a, b in zip(lefts, lefts[1:], strict=False)]
    assert all(abs(step - 178) <= SPACING_TOLERANCE for step in steps)


def test_find_card_lefts_empty_on_blank_screen() -> None:
    assert find_card_lefts(np.full((1920, 1080, 3), 255, np.uint8)) == []


def test_element_filter_points() -> None:
    assert set(ELEMENT_FILTER_POINTS) == {"water", "fire", "grass", "rock", "lightning"}
    assert ELEMENT_FILTER_POINTS["water"] == Point(240, 1665)
    assert ELEMENT_FILTER_POINTS["lightning"] == Point(720, 1665)
    assert ALL_FILTER_POINT == Point(90, 1665)
