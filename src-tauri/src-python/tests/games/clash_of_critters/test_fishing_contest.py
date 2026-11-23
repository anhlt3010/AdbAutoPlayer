from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters.main import (
    fishing_button_state,
    read_tension_bar,
)


def _screen(bgr: tuple[int, int, int]) -> np.ndarray:
    screen = np.zeros((1920, 1080, 3), dtype=np.uint8)
    screen[1500:1700, 380:700] = bgr
    return screen


# BGR colours measured on the device at the left edge of the fishing button.
@pytest.mark.parametrize(
    ("bgr", "expected"),
    [
        ((40, 190, 84), "cast"),
        ((113, 113, 113), "wait"),
        ((235, 79, 186), "bite"),
        ((14, 10, 12), None),  # dark overlay of the reward popup
        ((40, 60, 220), None),  # some other screen (red)
    ],
)
def test_fishing_button_state(bgr, expected):
    assert fishing_button_state(_screen(bgr)) == expected


DATA = Path(__file__).parent / "data"


def _band_screen(name: str) -> np.ndarray:
    """Paste a saved crop of the tension bar band (x 270-850, y 1230-1340)."""
    screen = np.zeros((1920, 1080, 3), dtype=np.uint8)
    screen[1230:1340, 270:850] = cv2.imread(str(DATA / name))
    return screen


def test_read_tension_bar_finds_bobber_and_zone():
    bobber, zone = read_tension_bar(_band_screen("fishing_tension_bar.png"))
    assert abs(bobber - 642) <= 5
    assert zone is not None
    assert abs(zone[0] - 446) <= 5


def test_read_tension_bar_ignores_the_bite_timer_bar():
    # "Ngay! Kéo cần đi!" timer bar: yellow but no bobber.
    assert read_tension_bar(_band_screen("fishing_bite_timer.png")) is None
