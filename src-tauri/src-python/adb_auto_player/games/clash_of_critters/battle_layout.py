"""Pixel layout of the Clash of Critters battle preparation screen (1080x1920).

Measured on real captures (``docs/superpowers/specs/assets/prep_screen_*.png``).
Boxes are ``(left, top, right, bottom)``.
"""

from collections.abc import Collection
from dataclasses import dataclass

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


@dataclass(frozen=True)
class PrepLayout:
    """Geometry of one kind of battle preparation screen (1080x1920).

    ``BATTLE_LAYOUT`` is the auto battle screen, ``DOJO_LAYOUT`` the one of the
    Võ Đường Huy Hiệu fights. Boxes are ``(left, top, right, bottom)``.
    """

    field_columns_x: tuple[int, ...]
    field_rows_y: tuple[int, ...]
    max_deployed: int
    tray_columns_x: tuple[int, ...]
    tray_rows_y: tuple[int, ...]
    card_size: tuple[int, int]
    tray_box: tuple[int, int, int, int]
    card_band_rows: tuple[int, int]
    card_width_range: tuple[int, int]
    scroll_y: int
    scroll_from_x: int
    scroll_to_x: int
    clear_field_point: Point
    counter_box: tuple[int, int, int, int]
    stage_label_box: tuple[int, int, int, int]
    has_element_filter: bool


BATTLE_LAYOUT = PrepLayout(
    field_columns_x=FIELD_COLUMNS_X,
    field_rows_y=FIELD_ROWS_Y,
    max_deployed=MAX_DEPLOYED,
    tray_columns_x=TRAY_COLUMNS_X,
    tray_rows_y=TRAY_ROWS_Y,
    card_size=CARD_SIZE,
    tray_box=TRAY_BOX,
    card_band_rows=_CARD_BAND_ROWS,
    card_width_range=_CARD_WIDTH_RANGE,
    scroll_y=1383,
    scroll_from_x=900,
    scroll_to_x=400,
    clear_field_point=CLEAR_FIELD_POINT,
    counter_box=COUNTER_BOX,
    stage_label_box=STAGE_LABEL_BOX,
    has_element_filter=True,
)

# Võ Đường: a 3x4 field with at most 5 units, 5 wider tray columns, no element
# filter (the tray only holds the element of the Võ Đường). Measured on the
# captures ``docs/superpowers/specs/assets/dojo_prep_*.png``.
DOJO_LAYOUT = PrepLayout(
    field_columns_x=(429, 541, 654),
    field_rows_y=(634, 747, 860, 974),
    max_deployed=5,
    tray_columns_x=(132, 337, 554, 771, 989),
    tray_rows_y=(1354, 1598),
    card_size=(194, 232),
    tray_box=(20, 1230, 1050, 1725),
    card_band_rows=(1255, 1420),
    card_width_range=(178, 198),
    scroll_y=1468,
    scroll_from_x=900,
    scroll_to_x=400,
    clear_field_point=Point(1000, 1040),
    counter_box=(100, 1130, 630, 1210),
    stage_label_box=(500, 45, 640, 110),
    has_element_filter=False,
)


def cell_center(row: int, col: int, layout: PrepLayout = BATTLE_LAYOUT) -> Point:
    """Return the centre of a field cell.

    Args:
        row: Row 1-n, top to bottom.
        col: Column 1-n, left to right.
        layout: The preparation screen the cell is on.

    Returns:
        The centre of the cell in screen pixels.

    Raises:
        ValueError: The row or column is outside the field of the layout.
    """
    rows, columns = layout.field_rows_y, layout.field_columns_x
    if not 1 <= row <= len(rows) or not 1 <= col <= len(columns):
        raise ValueError(
            f"Cell ({row}, {col}) is outside the {len(columns)}x{len(rows)} field."
        )
    return Point(columns[col - 1], rows[row - 1])


def tray_slots(layout: PrepLayout = BATTLE_LAYOUT) -> list[Point]:
    """Return the centres of the visible tray cards, row by row."""
    return [Point(x, y) for y in layout.tray_rows_y for x in layout.tray_columns_x]


def card_box(
    center: Point, layout: PrepLayout = BATTLE_LAYOUT
) -> tuple[int, int, int, int]:
    """Return the screen box of the card centred on a tray slot."""
    width, height = layout.card_size
    left = center.x - width // 2
    top = center.y - height // 2
    return left, top, left + width, top + height


def find_card_lefts(
    screenshot_bgr: np.ndarray, layout: PrepLayout = BATTLE_LAYOUT
) -> list[int]:
    """Find the left edge of every whole card in the tray.

    The tray scrolls with some momentum, so cards are not always on the slots of
    ``tray_slots()``; the light gaps between the cards show where they are.

    Args:
        screenshot_bgr: A full 1080x1920 screenshot (BGR).
        layout: The preparation screen the tray is on.

    Returns:
        The left edges, left to right, of the cards that are fully visible.
    """
    top, bottom = layout.card_band_rows
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
        if layout.card_width_range[0] <= x - start <= layout.card_width_range[1]:
            lefts.append(start)
    return lefts


def cell_at(point: Point, layout: PrepLayout = BATTLE_LAYOUT) -> tuple[int, int] | None:
    """Return the (row, col) of the cell whose centre is exactly ``point``."""
    columns, rows = layout.field_columns_x, layout.field_rows_y
    if point.x in columns and point.y in rows:
        return rows.index(point.y) + 1, columns.index(point.x) + 1
    return None


def _is_steep(start: Point, end: Point) -> bool:
    return abs(end.x - start.x) <= DRAG_MAX_RATIO * abs(end.y - start.y)


def plan_drag(
    card: Point,
    row: int,
    col: int,
    occupied: Collection[tuple[int, int]],
    layout: PrepLayout = BATTLE_LAYOUT,
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
        layout: The preparation screen the drag happens on.

    Returns:
        ``[card, target]``, or ``[card, intermediate_cell, target]``.
    """
    target = cell_center(row, col, layout)
    if _is_steep(card, target):
        return [card, target]
    best: tuple[tuple[int, int], Point] | None = None
    for r in range(1, len(layout.field_rows_y) + 1):
        for c in range(1, len(layout.field_columns_x) + 1):
            if (r, c) == (row, col) or (r, c) in occupied:
                continue
            middle = cell_center(r, c, layout)
            if not _is_steep(card, middle):
                continue
            distance = (abs(middle.x - target.x), abs(middle.y - target.y))
            if best is None or distance < best[0]:
                best = (distance, middle)
    if best is None:
        return [card, target]
    return [card, best[1], target]
