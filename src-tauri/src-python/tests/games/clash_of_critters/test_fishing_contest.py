from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters.main import (
    fishing_button_state,
    plan_tap,
    read_tension_bar,
    seconds_to_reach,
    smoothed_speed,
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


TEMPLATES = (
    Path(__file__).parents[3] / "adb_auto_player/games/clash_of_critters/templates"
)


def _result_match(screen: np.ndarray) -> float:
    template = cv2.imread(str(TEMPLATES / "fishing_contest_result.png"))
    return cv2.minMaxLoc(cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED))[1]


def test_result_template_matches_the_record_screen():
    # Rows 1300-1460 of the "Kỷ lục cá nhân mới!" catch result screen.
    assert (
        _result_match(cv2.imread(str(DATA / "fishing_personal_record_text.png"))) > 0.9
    )


def test_result_template_survives_the_wrapped_line():
    # "Đánh bại 100,00% ..." (new server record) pushes "máy chủ!" to the next
    # line: the template must not need the word "máy".
    screen = cv2.imread(str(DATA / "fishing_personal_record_text.png"))
    screen[:, 920:] = 0
    assert _result_match(screen) > 0.9


_LOW, _HIGH = 380, 800


def test_seconds_to_reach_moving_toward_target():
    assert seconds_to_reach(400, 300, 700, _LOW, _HIGH) == pytest.approx(1.0)


def test_seconds_to_reach_moving_away_bounces_once():
    assert seconds_to_reach(500, 300, 400, _LOW, _HIGH) == pytest.approx(700 / 300)


def test_seconds_to_reach_moving_left_bounces_off_the_left_end():
    # left end (120 px), then right until 600 (220 px)
    assert seconds_to_reach(500, -300, 600, _LOW, _HIGH) == pytest.approx(340 / 300)


def test_seconds_to_reach_negative_velocity_toward_target():
    assert seconds_to_reach(700, -300, 400, _LOW, _HIGH) == pytest.approx(1.0)


def test_seconds_to_reach_slow_speed_is_none():
    assert seconds_to_reach(500, 10, 600, _LOW, _HIGH) is None


def test_plan_tap_small_zone_aims_at_centre():
    # centre 600 is reached in 0.17 s: tap 0.02 s from now (lead 0.15 s)
    delay = plan_tap(549, 300, (596, 604), 0.15)
    assert delay == pytest.approx(0.02)


def test_plan_tap_not_close_yet_is_none():
    assert plan_tap(400, 300, (596, 604), 0.15) is None


def test_plan_tap_passed_the_centre_is_none():
    assert plan_tap(610, 300, (596, 604), 0.15) is None


def test_plan_tap_wide_zone_taps_once_per_crossing():
    assert plan_tap(560, 300, (450, 750), 0.15) == 0.0


def test_smoothed_speed():
    assert smoothed_speed([(100, 0.0), (130, 0.1)]) == pytest.approx(300.0)
    assert smoothed_speed([(100, 0.0)]) == 0.0
    assert smoothed_speed([(100, 1.0), (130, 1.0)]) == 0.0
