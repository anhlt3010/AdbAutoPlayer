"""Pixel layout of the Clash of Critters battle preparation screen (1080x1920).

Measured on real captures (``docs/superpowers/specs/assets/prep_screen_*.png``).
Boxes are ``(left, top, right, bottom)``.
"""

from adb_auto_player.models.geometry import Point

# Player field, 5 rows x 5 columns, cell centres.
FIELD_COLUMNS_X = (300, 420, 540, 660, 780)
FIELD_ROWS_Y = (490, 610, 730, 850, 970)
MAX_DEPLOYED = 15

# Tray of owned tatari cards (2 rows, 6 visible columns, scrolls horizontally).
TRAY_COLUMNS_X = (110, 288, 466, 644, 822, 1000)
TRAY_ROWS_Y = (1285, 1480)
CARD_SIZE = (160, 190)
# Inside one card, relative to its top-left corner.
ELEMENT_ICON_BOX = (2, 2, 58, 50)
CARD_ART_BOX = (50, 52, 158, 162)
TRAY_BOX = (20, 1180, 1040, 1590)

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
