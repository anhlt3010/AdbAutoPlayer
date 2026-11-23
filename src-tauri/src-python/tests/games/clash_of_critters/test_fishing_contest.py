from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from pydantic import ValidationError
from adb_auto_player.games.clash_of_critters.settings import (
    FishingContestSettings,
    Settings,
)
from adb_auto_player.games.clash_of_critters import main as coc_main
from adb_auto_player.games.clash_of_critters.main import (
    ClashOfCritters,
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


def test_fishing_contest_settings_default():
    assert FishingContestSettings().tap_lead_seconds == 0.15
    assert "fishing_contest" in Settings.model_fields


@pytest.mark.parametrize("value", [-0.01, 0.51])
def test_fishing_contest_tap_lead_out_of_range_is_rejected(value):
    with pytest.raises(ValidationError):
        FishingContestSettings(tap_lead_seconds=value)


@pytest.mark.parametrize("value", [0.0, 0.5])
def test_fishing_contest_tap_lead_range_ends_are_accepted(value):
    assert FishingContestSettings(tap_lead_seconds=value).tap_lead_seconds == value


_SPEED = 300  # px/s, like the real bobber
_BAR_END_SECONDS = 2.4


def _bobber_x(seconds: float) -> int:
    """Bobber that starts at x 400 and bounces between 380 and 800."""
    width = _HIGH - _LOW
    folded = (400 - _LOW + _SPEED * seconds) % (2 * width)
    return _LOW + int(min(folded, 2 * width - folded))


def _tap_times(
    monkeypatch: pytest.MonkeyPatch,
    zone: tuple[int, int] | None,
    lead: float,
    end: float = _BAR_END_SECONDS,
) -> list[float]:
    """Run `_play_tension_bar` on a fake clock; return the clock of every tap."""
    clock = [0.0]
    taps: list[float] = []
    monkeypatch.setattr(coc_main, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        coc_main, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    monkeypatch.setattr(
        coc_main,
        "read_tension_bar",
        lambda _screenshot: (_bobber_x(clock[0]), zone) if clock[0] < end else None,
    )
    fake = SimpleNamespace(
        settings=SimpleNamespace(
            fishing_contest=SimpleNamespace(tap_lead_seconds=lead)
        ),
        get_screenshot=lambda: None,
        tap=lambda *_args, **_kwargs: taps.append(clock[0]),
    )
    ClashOfCritters._play_tension_bar(fake)
    return taps


def test_tension_bar_small_zone_taps_once_near_the_centre(monkeypatch):
    # The bobber reaches the centre (x 600) at 2/3 s; the tap leaves 0.15 s before.
    taps = _tap_times(monkeypatch, (596, 604), 0.15, end=1.2)
    assert len(taps) == 1
    assert taps[0] == pytest.approx(2 / 3 - 0.15, abs=0.04)


def test_tension_bar_wide_zone_is_tapped_once_per_crossing(monkeypatch):
    taps = _tap_times(monkeypatch, (450, 750), 0.15)
    assert len(taps) >= 1
    assert all(later - earlier > 1.0 for earlier, later in pairwise(taps))


def test_tension_bar_uses_the_lead_setting(monkeypatch):
    late = _tap_times(monkeypatch, (596, 604), 0.1, end=1.2)
    early = _tap_times(monkeypatch, (596, 604), 0.3, end=1.2)
    assert late[0] - early[0] == pytest.approx(0.2, abs=0.05)


def test_tension_bar_no_tap_without_a_zone(monkeypatch):
    assert _tap_times(monkeypatch, None, 0.15) == []
