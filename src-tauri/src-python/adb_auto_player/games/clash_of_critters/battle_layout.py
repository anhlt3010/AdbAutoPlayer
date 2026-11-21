"""Pixel layout of the Clash of Critters battle preparation screen (1080x1920).

Measured on real captures (``docs/superpowers/specs/assets/prep_screen_*.png``).
Boxes are ``(left, top, right, bottom)``.
"""

from collections.abc import Collection

import numpy as np
from adb_auto_player.models.geometry import Point

# Player field, 5 rows x 5 columns, cell centres.
FIELD_COLUMNS_X = (300, 420, 540, 660, 780)
FIELD_ROWS_Y = (490, 610, 730, 850, 970)
MAX_DEPLOYED = 15
# A drag from the tray is taken for a scroll of the tray when it is too sideways;
# it only works reliably when |dx| <= DRAG_MAX_RATIO * |dy|.
DRAG_MAX_RATIO = 0.5

# Tray of owned tatari cards (2 rows, 6 visible columns, scrolls horizontally).
TRAY_COLUMNS_X = (110, 288, 466, 644, 822, 1000)
TRAY_ROWS_Y = (1285, 1480)
CARD_SIZE = (160, 190)
# Inside one card, relative to its top-left corner.
ELEMENT_ICON_BOX = (2, 2, 58, 50)
CARD_ART_BOX = (50, 52, 158, 162)
TRAY_BOX = (20, 1180, 1040, 1590)
# Rows of the first tray row used to find the gaps between cards, and what counts as
# a gap (the light tray background) and as a whole card (cards clipped by the tray
# edges are narrower).
_CARD_BAND_ROWS = (1200, 1370)
_GAP_MIN_BRIGHTNESS = 200
_GAP_MIN_FRACTION = 0.9
_CARD_WIDTH_RANGE = (154, 166)

# Element filter buttons under the tray: show only the cards of one element.
ALL_FILTER_POINT = Point(90, 1665)
ELEMENT_FILTER_POINTS = {
    "water": Point(240, 1665),
    "fire": Point(360, 1665),
    "grass": Point(480, 1665),
    "rock": Point(600, 1665),
    "lightning": Point(720, 1665),
}

# Right-edge button (download-style icon) that clears the whole field.
CLEAR_FIELD_POINT = Point(1000, 880)

# Text regions on the preparation screen.
STAGE_LABEL_BOX = (380, 25, 550, 95)
COUNTER_BOX = (300, 1110, 500, 1170)


def cell_center(row: int, col: int) -> Point:
    """Return the centre of a field cell.

    Args:
        row: Row 1-5, top to bottom.
        col: Column 1-5, left to right.

    Returns:
        The centre of the cell in screen pixels.

    Raises:
        ValueError: The row or column is outside 1-5.
    """
    if not 1 <= row <= len(FIELD_ROWS_Y) or not 1 <= col <= len(FIELD_COLUMNS_X):
        raise ValueError(f"Cell ({row}, {col}) is outside the 5x5 field.")
    return Point(FIELD_COLUMNS_X[col - 1], FIELD_ROWS_Y[row - 1])


def tray_slots() -> list[Point]:
    """Return the centres of the visible tray cards, row by row."""
    return [Point(x, y) for y in TRAY_ROWS_Y for x in TRAY_COLUMNS_X]


def card_box(center: Point) -> tuple[int, int, int, int]:
    """Return the screen box of the card centred on a tray slot."""
    width, height = CARD_SIZE
    left = center.x - width // 2
    top = center.y - height // 2
    return left, top, left + width, top + height


def find_card_lefts(screenshot_bgr: np.ndarray) -> list[int]:
    """Find the left edge of every whole card in the tray.

    The tray scrolls with some momentum, so cards are not always on the slots of
    ``tray_slots()``; the light gaps between the cards show where they are.

    Args:
        screenshot_bgr: A full 1080x1920 screenshot (BGR).

    Returns:
        The left edges, left to right, of the cards that are fully visible.
    """
    top, bottom = _CARD_BAND_ROWS
    bright = screenshot_bgr[top:bottom].min(axis=2) > _GAP_MIN_BRIGHTNESS
    is_gap = bright.mean(axis=0) > _GAP_MIN_FRACTION
    lefts: list[int] = []
    x = 0
    while x < len(is_gap):
        if is_gap[x]:
            x += 1
            continue
        start = x
        while x < len(is_gap) and not is_gap[x]:
            x += 1
        if _CARD_WIDTH_RANGE[0] <= x - start <= _CARD_WIDTH_RANGE[1]:
            lefts.append(start)
    return lefts


def cell_at(point: Point) -> tuple[int, int] | None:
    """Return the (row, col) of the cell whose centre is exactly ``point``."""
    if point.x in FIELD_COLUMNS_X and point.y in FIELD_ROWS_Y:
        return FIELD_ROWS_Y.index(point.y) + 1, FIELD_COLUMNS_X.index(point.x) + 1
    return None


def _is_steep(start: Point, end: Point) -> bool:
    return abs(end.x - start.x) <= DRAG_MAX_RATIO * abs(end.y - start.y)


def plan_drag(
    card: Point, row: int, col: int, occupied: Collection[tuple[int, int]]
) -> list[Point]:
    """Plan the path of a unit from its tray card to a field cell.

    A drag that is mostly sideways scrolls the tray instead of lifting the card.
    In that case the card is first dropped on a free cell that is steep enough
    from the card (the one closest to the target), and the unit is then moved to
    its cell inside the field, where there is no such limit.

    Args:
        card: The centre of the card in the tray.
        row: Target row 1-5.
        col: Target column 1-5.
        occupied: Cells that already hold a unit.

    Returns:
        ``[card, target]``, or ``[card, intermediate_cell, target]``.
    """
    target = cell_center(row, col)
    if _is_steep(card, target):
        return [card, target]
    best: tuple[tuple[int, int], Point] | None = None
    for r in range(1, len(FIELD_ROWS_Y) + 1):
        for c in range(1, len(FIELD_COLUMNS_X) + 1):
            if (r, c) == (row, col) or (r, c) in occupied:
                continue
            middle = cell_center(r, c)
            if not _is_steep(card, middle):
                continue
            distance = (abs(middle.x - target.x), abs(middle.y - target.y))
            if best is None or distance < best[0]:
                best = (distance, middle)
    if best is None:
        return [card, target]
    return [card, best[1], target]
