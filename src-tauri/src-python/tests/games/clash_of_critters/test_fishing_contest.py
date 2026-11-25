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
    BobberClock,
    HeadingTracker,
    TensionBarStats,
    plan_tap,
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


def test_reward_claim_template_matches_the_reward_screen():
    # "Phần Thưởng!" screen after a catch: "Nhận Ngay" sits at y 1656-1731.
    screen = cv2.imread(str(DATA / "fishing_reward_screen.png"))
    template = cv2.imread(str(TEMPLATES / "fishing_reward_claim_button.png"))
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    assert score > 0.9
    assert loc == (385, 1656)


def test_reward_screen_dims_the_fishing_button():
    screen = cv2.imread(str(DATA / "fishing_reward_screen.png"))
    assert fishing_button_state(screen) is None


def test_close_fishing_popup_presses_nhan_ngay_of_the_reward_screen():
    taps = []
    asked = []
    found = SimpleNamespace(template=coc_main.FISHING_REWARD_CLAIM_BUTTON)

    def find_any_template(templates):
        asked.append(templates)
        return found

    bot = SimpleNamespace(
        _tap_common_button=lambda: False,
        find_any_template=find_any_template,
        tap=lambda target, log=True: taps.append(target),
    )
    assert ClashOfCritters._close_fishing_popup(bot) is True
    assert coc_main.FISHING_REWARD_CLAIM_BUTTON in asked[0]
    assert taps == [found]


_L, _R, _V = 308, 806, 352.0  # the bobber: triangle wave, measured on MuMu
_WIDTH = _R - _L
_START_X = 700  # truth: x at game time 0, moving right
_FRESH_DELAY = 0.1  # the freshest frame is this old
_TAP_DELAY = 0.05  # the tap needs this long to reach the game
_FPS = 25  # the stream delivers about this many different frames per second


def _truth_x(seconds: float) -> float:
    """True bobber x at a game time (x 700 at 0 s, moving right)."""
    phase = (_START_X - _L + _V * seconds) % (2 * _WIDTH)
    return _L + (phase if phase < _WIDTH else 2 * _WIDTH - phase)


def _seen(seconds: float, fps: float = _FPS) -> int:
    """X of the frame on screen at `seconds`.

    A frame is decoded `fps` times a second and is late by 0.1 to 0.4 s (a ramp:
    the picture runs in slow motion until a catch-up, like the real stream).
    """
    frame_at = int(seconds * fps) / fps
    stale = _FRESH_DELAY + 0.3 * ((frame_at / 0.5) % 1)
    return round(_truth_x(frame_at - stale))


def _crossing(after: float, x: float) -> float:
    """First game time after `after` the true bobber is on `x`."""
    t = after
    side = _truth_x(t) < x
    while (_truth_x(t) < x) == side:
        t += 0.001
    return t


def _clock_after(seconds: float) -> BobberClock:
    clock = BobberClock()
    tracker = HeadingTracker()
    for step in range(round(seconds * 100) + 1):
        t = step / 100
        for x, direction, wall in tracker.add(_seen(t), t):
            clock.observe(x, direction, wall)
    return clock


def _feed(tracker: HeadingTracker, xs: list[int], start: float = 0.0):
    """Add frames 0.04 s apart; return what each add returned."""
    return [tracker.add(x, start + 0.04 * i) for i, x in enumerate(xs)]


def test_tracker_gives_the_direction_of_a_steady_move_to_the_whole_run():
    out = _feed(HeadingTracker(), [400, 406, 412, 418, 424])
    assert out[:3] == [[], [], []]
    # the 4th frame completes the run: every frame of it gets the direction
    assert [(x, d) for x, d, _ in out[3]] == [(400, 1), (406, 1), (412, 1), (418, 1)]
    assert out[3][0][2] == 0.0  # with the wall time of its own frame
    assert [(x, d) for x, d, _ in out[4]] == [(424, 1)]


def test_tracker_direction_left():
    out = _feed(HeadingTracker(), [418, 412, 406, 400])
    assert [d for _, d, _ in out[3]] == [-1, -1, -1, -1]


def test_tracker_ignores_jitter_of_one_pixel():
    assert _feed(HeadingTracker(), [400, 401, 400, 401, 400]) == [[]] * 5


def test_tracker_starts_a_new_run_after_a_stream_jump():
    # the stream stalled and caught up over a bounce: x jumps 36 px. The frame
    # after the jump is the freshest one and gets the direction of its own run.
    out = _feed(HeadingTracker(), [727, 732, 768, 763, 758, 752])
    assert out[:5] == [[]] * 5
    assert [(x, d) for x, d, _ in out[5]] == [
        (768, -1),
        (763, -1),
        (758, -1),
        (752, -1),
    ]


def test_tracker_starts_a_new_run_at_a_turn():
    out = _feed(HeadingTracker(), [790, 796, 801, 806, 800, 794, 788])
    assert [(x, d) for x, d, _ in out[3]] == [(790, 1), (796, 1), (801, 1), (806, 1)]
    # 800, 794, 788 are only 3 frames of the new run: no direction yet, and the
    # frames before the turn are not given the wrong one
    assert out[4:] == [[], [], []]


def test_bobber_clock_is_not_ready_without_observations():
    clock = BobberClock()
    assert not clock.ready
    clock.observe(400, 1, 0.0)
    assert not clock.ready


def test_bobber_clock_predicts_position_through_bounces():
    clock = _clock_after(1.0)
    assert clock.ready
    # the model runs _FRESH_DELAY behind the wall clock
    for wall in (1.2, 1.6, 2.0, 2.4):
        assert clock.position(wall) == pytest.approx(
            _truth_x(wall - _FRESH_DELAY), abs=8
        )


def test_bobber_clock_ignores_stale_frames():
    # stale frames (up to 0.4 s old) are most of the stream; the clock follows the
    # freshest ones and does not drift to the stale ones
    clock = _clock_after(4.0)
    assert clock.position(4.3) == pytest.approx(_truth_x(4.3 - _FRESH_DELAY), abs=8)


_WARM_UP = 1.3  # the freshest frame (1.0 s) is given a direction by 1.12 s


def _planned_tap_wall(lead: float) -> float:
    """Wall time a tap must be sent to land on x 600 (centre of the test zones)."""
    return _crossing(_WARM_UP, 600) + _FRESH_DELAY - lead


def test_plan_tap_aims_at_the_centre():
    clock = _clock_after(_WARM_UP)
    now = _planned_tap_wall(0.2) - 0.018
    assert plan_tap(clock, (590, 610), now, 0.2, 0.03) == pytest.approx(
        0.018, abs=0.015
    )


def test_plan_tap_not_close_yet_is_none():
    clock = _clock_after(_WARM_UP)
    now = _planned_tap_wall(0.2) - 0.3
    assert plan_tap(clock, (590, 610), now, 0.2, 0.03) is None


def test_plan_tap_late_but_inside_the_zone_taps_at_once():
    clock = _clock_after(_WARM_UP)
    now = _planned_tap_wall(0.2) + 0.05
    assert plan_tap(clock, (500, 700), now, 0.2, 0.03) == 0.0
    assert plan_tap(clock, (590, 610), now, 0.2, 0.03) is None


def test_plan_tap_not_ready_is_none():
    assert plan_tap(BobberClock(), (590, 610), 0.45, 0.2, 0.03) is None


def _tap_times(
    monkeypatch: pytest.MonkeyPatch,
    zone: tuple[int, int] | None,
    lead: float,
    end: float,
    fps: float = _FPS,
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
        lambda _screenshot: (_seen(clock[0], fps), zone) if clock[0] < end else None,
    )
    fake = SimpleNamespace(
        settings=SimpleNamespace(
            fishing_contest=SimpleNamespace(tap_lead_seconds=lead)
        ),
        get_screenshot=lambda: None,
        tap=lambda *_args, **_kwargs: taps.append(clock[0]),
        _stream_frame_stats=lambda: (None, None),
    )
    ClashOfCritters._play_tension_bar(fake)
    return taps


def _lands_on_the_zone(tap: float, zone: tuple[int, int]) -> bool:
    return zone[0] <= _truth_x(tap + _TAP_DELAY) <= zone[1]


def test_tension_bar_taps_once_and_lands_in_a_small_zone(monkeypatch):
    zone = (590, 610)
    taps = _tap_times(monkeypatch, zone, _FRESH_DELAY + _TAP_DELAY, end=1.2)
    assert len(taps) == 1
    assert _lands_on_the_zone(taps[0], zone)


def test_tension_bar_held_frames_do_not_tap_twice(monkeypatch):
    # a frame is repeated for 0.1 s: the old zone shows again after the tap
    zone = (590, 610)
    taps = _tap_times(monkeypatch, zone, _FRESH_DELAY + _TAP_DELAY, end=1.2, fps=10)
    assert len(taps) == 1


def test_tension_bar_second_crossing_after_a_bounce(monkeypatch):
    # readable while the bobber is on the right half; it crosses the centre
    # (x 430) going left, bounces off the left end and comes back later
    zone = (300, 560)
    taps = _tap_times(monkeypatch, zone, _FRESH_DELAY + _TAP_DELAY, end=4.2)
    assert len(taps) == 2
    assert all(_lands_on_the_zone(tap, zone) for tap in taps)


def test_tension_bar_uses_the_lead_setting(monkeypatch):
    zone = (590, 610)
    late = _tap_times(monkeypatch, zone, 0.1, end=1.2)
    early = _tap_times(monkeypatch, zone, 0.3, end=1.2)
    assert late[0] - early[0] == pytest.approx(0.2, abs=0.05)


def test_tension_bar_no_tap_without_a_zone(monkeypatch):
    assert _tap_times(monkeypatch, None, 0.15, end=2.0) == []


def test_tension_bar_logs_its_stats(monkeypatch, caplog):
    caplog.set_level("INFO")
    _tap_times(monkeypatch, (590, 610), _FRESH_DELAY + _TAP_DELAY, end=1.2)
    stats = [m for m in caplog.messages if m.startswith("Tension bar stats:")]
    assert len(stats) == 1
    assert "screenshots (no stream)" in stats[0]


def test_tension_stats_count_stream_frames_per_second():
    stats = TensionBarStats(10.0, 100)
    stats.add(10.5, 110, 10.45)
    stats.add(11.0, 130, 10.9)
    line = stats.summary(11.0, hits=2)
    assert "2 taps" in line
    assert "stream 30 frames = 30.0 fps" in line
    assert "2 loop passes" in line
    assert "longest pass gap 0.50 s" in line
    assert "oldest frame 0.10 s" in line


def test_tension_stats_without_a_stream():
    stats = TensionBarStats(0.0, None)
    stats.add(0.1, None, None)
    assert "screenshots (no stream)" in stats.summary(0.1, hits=0)


def test_stream_frame_stats_without_a_stream():
    fake = SimpleNamespace(_stream=None)
    assert ClashOfCritters._stream_frame_stats(fake) == (None, None)


def test_stream_frame_stats_reads_the_stream():
    stream = SimpleNamespace(get_frame_stats=lambda: (7, 1.5))
    fake = SimpleNamespace(_stream=stream)
    assert ClashOfCritters._stream_frame_stats(fake) == (7, 1.5)


def test_fishing_contest_settings_default():
    assert FishingContestSettings().tap_lead_seconds == 0.2
    assert "fishing_contest" in Settings.model_fields


@pytest.mark.parametrize("value", [-0.01, 0.51])
def test_fishing_contest_tap_lead_out_of_range_is_rejected(value):
    with pytest.raises(ValidationError):
        FishingContestSettings(tap_lead_seconds=value)


@pytest.mark.parametrize("value", [0.0, 0.5])
def test_fishing_contest_tap_lead_range_ends_are_accepted(value):
    assert FishingContestSettings(tap_lead_seconds=value).tap_lead_seconds == value
