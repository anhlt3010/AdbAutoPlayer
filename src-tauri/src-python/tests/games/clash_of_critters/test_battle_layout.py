"""Tests for the battle preparation screen layout."""

import itertools
from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters.battle_layout import (
    ALL_FILTER_POINT,
    BATTLE_LAYOUT,
    CARD_SIZE,
    DOJO_LAYOUT,
    ELEMENT_FILTER_POINTS,
    FIELD_COLUMNS_X,
    MAX_DEPLOYED,
    cell_at,
    cell_center,
    find_card_lefts,
    plan_drag,
    tray_slots,
)
from adb_auto_player.models.geometry import Point


def xy(point: Point) -> tuple[int, int]:
    """Coordinates of a point.

    ``Point`` has no dataclass fields, so any two points compare equal; tests
    must compare coordinates instead.
    """
    return point.x, point.y


def test_cell_center_corners() -> None:
    assert xy(cell_center(1, 1)) == (300, 490)
    assert xy(cell_center(5, 5)) == (780, 970)


@pytest.mark.parametrize("row, col", [(0, 1), (1, 6), (6, 1), (1, 0)])
def test_cell_center_out_of_range(row: int, col: int) -> None:
    with pytest.raises(ValueError):
        cell_center(row, col)


def test_tray_slots_count_and_order() -> None:
    slots = tray_slots()
    assert len(slots) == 12
    assert xy(slots[0]) == (110, 1285)
    assert xy(slots[6]) == (110, 1480)


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
    steps = [b - a for a, b in itertools.pairwise(lefts)]
    assert all(abs(step - 178) <= SPACING_TOLERANCE for step in steps)


def test_find_card_lefts_empty_on_blank_screen() -> None:
    assert find_card_lefts(np.full((1920, 1080, 3), 255, np.uint8)) == []


def test_element_filter_points() -> None:
    assert set(ELEMENT_FILTER_POINTS) == {"water", "fire", "grass", "rock", "lightning"}
    assert xy(ELEMENT_FILTER_POINTS["water"]) == (240, 1665)
    assert xy(ELEMENT_FILTER_POINTS["lightning"]) == (720, 1665)
    assert xy(ALL_FILTER_POINT) == (90, 1665)


# --- planning a drag ---------------------------------------------------------------


def _path(card: Point, row: int, col: int, occupied: set) -> list[tuple[int, int]]:
    return [xy(p) for p in plan_drag(card, row, col, occupied)]


def test_steep_drag_goes_straight_to_the_cell() -> None:
    assert _path(Point(110, 1285), 1, 1, set()) == [(110, 1285), (300, 490)]


def test_shallow_drag_goes_through_an_intermediate_cell() -> None:
    # From the left end of the tray to the right of the field the finger would
    # travel almost sideways, which the game takes for a scroll of the tray.
    assert _path(Point(109, 1285), 5, 4, set()) == [
        (109, 1285),
        (420, 610),
        (660, 970),
    ]


def test_intermediate_cell_must_be_empty() -> None:
    assert _path(Point(109, 1285), 5, 4, {(2, 2)}) == [
        (109, 1285),
        (420, 490),
        (660, 970),
    ]


def test_intermediate_cell_is_never_the_target() -> None:
    card = Point(109, 1285)
    for row in range(1, 6):
        for col in range(1, 6):
            path = _path(card, row, col, set())
            assert path[-1] == xy(cell_center(row, col))
            assert xy(cell_center(row, col)) not in path[1:-1]


def test_the_first_leg_from_the_tray_is_always_steep_enough() -> None:
    for x in (109, 466, 822, 1000):
        card = Point(x, 1285)
        for row in range(1, 6):
            for col in range(1, 6):
                path = plan_drag(card, row, col, set())
                if len(path) == 3:  # went through an intermediate cell
                    assert abs(path[1].x - card.x) <= 0.5 * abs(path[1].y - card.y)


def test_no_free_intermediate_cell_falls_back_to_a_direct_drag() -> None:
    everything_else = {(r, c) for r in range(1, 6) for c in range(1, 6)} - {(5, 4)}
    assert _path(Point(109, 1285), 5, 4, everything_else) == [
        (109, 1285),
        (660, 970),
    ]


def test_cell_at_is_the_inverse_of_cell_center() -> None:
    assert cell_at(cell_center(2, 3)) == (2, 3)
    assert cell_at(Point(1, 1)) is None


# --- Võ Đường layout ---------------------------------------------------------------

ASSETS_DIR = Path(__file__).parents[5] / "docs" / "superpowers" / "specs" / "assets"
DOJO_LEFT_TOLERANCE = 6


def test_dojo_cell_center_corners() -> None:
    assert xy(cell_center(1, 1, DOJO_LAYOUT)) == (429, 634)
    assert xy(cell_center(4, 3, DOJO_LAYOUT)) == (654, 974)


@pytest.mark.parametrize("row, col", [(5, 1), (1, 4), (0, 1), (1, 0)])
def test_dojo_cell_center_out_of_range(row: int, col: int) -> None:
    with pytest.raises(ValueError):
        cell_center(row, col, DOJO_LAYOUT)


def test_battle_layout_matches_module_constants() -> None:
    assert BATTLE_LAYOUT.field_columns_x == FIELD_COLUMNS_X
    assert BATTLE_LAYOUT.max_deployed == MAX_DEPLOYED
    assert tuple(CARD_SIZE) == BATTLE_LAYOUT.card_size


def test_dojo_tray_slots() -> None:
    slots = tray_slots(DOJO_LAYOUT)
    assert len(slots) == 10
    assert xy(slots[0]) == (132, 1354)
    assert xy(slots[-1]) == (989, 1598)


def test_dojo_find_card_lefts_on_capture() -> None:
    image = cv2.imread(str(ASSETS_DIR / "dojo_prep_cleared.png"))
    assert image is not None
    lefts = find_card_lefts(image, DOJO_LAYOUT)
    # The fifth card is clipped by the tray edge and is left out.
    assert len(lefts) == 4
    for found, expected in zip(lefts, (35, 240, 457, 674), strict=True):
        assert abs(found - expected) <= DOJO_LEFT_TOLERANCE


def test_dojo_plan_drag_first_leg_is_steep_or_goes_through_a_free_cell() -> None:
    card = Point(132, 1354)
    for row in range(1, 5):
        for col in range(1, 4):
            path = plan_drag(card, row, col, set(), DOJO_LAYOUT)
            assert xy(path[-1]) == xy(cell_center(row, col, DOJO_LAYOUT))
            first = path[1]
            assert abs(first.x - card.x) <= 0.5 * abs(first.y - card.y)
