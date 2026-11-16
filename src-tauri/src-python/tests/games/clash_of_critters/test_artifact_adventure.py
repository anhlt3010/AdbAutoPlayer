"""Tests for the Clash of Critters Artifact Adventure commands."""

from itertools import count
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters import main
from adb_auto_player.games.clash_of_critters.main import ClashOfCritters
from adb_auto_player.games.clash_of_critters.settings import Settings

MIN_WIN_RATE = 80
ADVANCE_LIMIT = 2
IDLE_STEP_SECONDS = 30

SCREENS = [
    main.ARTIFACT_ADVENTURE_TAP_TO_CONTINUE,
    main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
    main.ARTIFACT_ADVENTURE_START_BUTTON,
    main.ARTIFACT_ADVENTURE_RETREAT_BUTTON,
    main.ARTIFACT_ADVENTURE_ACCEPT_BUTTON,
    main.ARTIFACT_ADVENTURE_CLAIM_BUTTON,
    main.OPEN_ALL_BUTTON,
    main.OK_BUTTON,
    main.MORE_GROUP_BUTTON,
]


def _match(template: str) -> SimpleNamespace:
    return SimpleNamespace(template=template)


@pytest.fixture
def bot() -> MagicMock:
    """ClashOfCritters instance with device-facing methods mocked."""
    game = object.__new__(ClashOfCritters)
    game.find_any_template = MagicMock(return_value=None)
    game.wait_for_template = MagicMock()
    game.wait_for_any_template = MagicMock()
    game.tap = MagicMock()
    game.open_eyes = MagicMock()
    settings = Settings()
    settings.artifact_adventure.min_win_rate_percent = MIN_WIN_RATE
    settings.artifact_adventure.limited_advance_count = ADVANCE_LIMIT
    game.get_settings = MagicMock(return_value=settings)
    return game


def _script_screens(bot: MagicMock, *templates: str) -> None:
    """Make successive find_any_template calls return the given screens."""
    bot.find_any_template.side_effect = [_match(t) for t in templates]


@pytest.fixture(autouse=True)
def no_sleep():
    """Never really sleep; expose the patched sleep to tests."""
    with patch.object(main, "sleep") as sleep:
        yield sleep


# --- Pinball screen handling (shared by every Events command) -----------------


def test_on_camp_screen_taps_pinball_tab(bot: MagicMock) -> None:
    pinball = _match(main.PINBALL_TAB)
    bot.wait_for_any_template.side_effect = [pinball, _match(main.CAMP_TAB)]
    bot._open_pinball_screen()
    bot.tap.assert_called_once_with(pinball, log=False)
    assert bot.wait_for_any_template.call_count == 2  # waits for the switch


def test_on_pinball_screen_does_nothing(bot: MagicMock) -> None:
    bot.wait_for_any_template.return_value = _match(main.CAMP_TAB)
    bot._open_pinball_screen()
    bot.tap.assert_not_called()
    assert bot.wait_for_any_template.call_count == 1


# --- Entry point of both commands --------------------------------------------


def test_skips_navigation_when_already_in_adventure(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON)
    bot._open_artifact_adventure_from_pinball = MagicMock()
    bot._run_artifact_adventure = MagicMock()
    bot._artifact_adventure(max_advances=None)
    bot._open_artifact_adventure_from_pinball.assert_not_called()
    bot._run_artifact_adventure.assert_called_once_with(SCREENS, None)


def test_opens_event_from_pinball_when_not_in_adventure(bot: MagicMock) -> None:
    bot._open_pinball_screen = MagicMock()
    icon = _match(main.ARTIFACT_ADVENTURE_ICON)
    bot.wait_for_template.return_value = icon
    bot._run_artifact_adventure = MagicMock()
    bot._artifact_adventure(max_advances=None)
    bot._open_pinball_screen.assert_called_once()
    bot.tap.assert_called_once_with(icon, log=False)
    bot.wait_for_any_template.assert_called_once()
    bot._run_artifact_adventure.assert_called_once_with(SCREENS, None)


def test_unlimited_command_passes_no_limit(bot: MagicMock) -> None:
    bot._artifact_adventure = MagicMock()
    bot.artifact_adventure()
    bot._artifact_adventure.assert_called_once_with(max_advances=None)


def test_limited_command_passes_configured_limit(bot: MagicMock) -> None:
    bot._artifact_adventure = MagicMock()
    bot.artifact_adventure_limited()
    bot._artifact_adventure.assert_called_once_with(max_advances=ADVANCE_LIMIT)


# --- Main loop ----------------------------------------------------------------


def test_loop_taps_claim_button(bot: MagicMock) -> None:
    claim = _match(main.ARTIFACT_ADVENTURE_CLAIM_BUTTON)
    bot.find_any_template.side_effect = [claim, *[None] * 5]
    with patch.object(main, "monotonic", side_effect=count(step=IDLE_STEP_SECONDS)):
        bot._run_artifact_adventure(SCREENS)
    bot.tap.assert_called_once_with(claim, log=False)


@pytest.mark.parametrize(
    "template",
    [
        main.OPEN_ALL_BUTTON,
        main.OK_BUTTON,
        main.MORE_GROUP_BUTTON,
    ],
)
def test_loop_taps_open_all_and_ok_buttons(bot: MagicMock, template: str) -> None:
    button = _match(template)
    bot.find_any_template.side_effect = [button, *[None] * 5]
    with patch.object(main, "monotonic", side_effect=count(step=IDLE_STEP_SECONDS)):
        bot._run_artifact_adventure(SCREENS)
    bot.tap.assert_called_once_with(button, log=False)


def test_open_all_and_ok_templates_exist() -> None:
    templates = Path(main.__file__).parent / "templates"
    assert (templates / main.OPEN_ALL_BUTTON).is_file()
    assert (templates / main.OK_BUTTON).is_file()
    assert (templates / main.MORE_GROUP_BUTTON).is_file()


def test_loop_reacts_to_each_screen(bot: MagicMock, no_sleep: MagicMock) -> None:
    tap_to_continue = _match(main.ARTIFACT_ADVENTURE_TAP_TO_CONTINUE)
    advance = _match(main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON)
    accept = _match(main.ARTIFACT_ADVENTURE_ACCEPT_BUTTON)
    start = _match(main.ARTIFACT_ADVENTURE_START_BUTTON)
    # Trailing Nones let the idle timeout end the loop.
    bot.find_any_template.side_effect = [
        tap_to_continue,
        advance,
        accept,
        start,
        *[None] * 5,
    ]
    with patch.object(main, "monotonic", side_effect=count(step=IDLE_STEP_SECONDS)):
        bot._run_artifact_adventure(SCREENS)
    assert [c.args[0] for c in bot.tap.call_args_list] == [
        tap_to_continue,
        advance,
        accept,
        start,
    ]
    # New adventure screen pauses before pressing start.
    assert call(main._START_SCREEN_WAIT_SECONDS) in no_sleep.call_args_list


def test_new_adventure_screen_tells_user_about_the_wait(
    bot: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    bot.find_any_template.side_effect = [
        _match(main.ARTIFACT_ADVENTURE_START_BUTTON),
        *[None] * 5,
    ]
    with (
        caplog.at_level("INFO"),
        patch.object(main, "monotonic", side_effect=count(step=IDLE_STEP_SECONDS)),
    ):
        bot._run_artifact_adventure(SCREENS, max_advances=None)
    assert "Chờ 20s để người dùng thay đổi setting phù hợp" in caplog.text


def test_loop_stops_after_idle_limit(bot: MagicMock) -> None:
    with patch.object(main, "monotonic", side_effect=count(step=IDLE_STEP_SECONDS)):
        bot._run_artifact_adventure(SCREENS)
    bot.tap.assert_not_called()


def test_unlimited_run_keeps_advancing(bot: MagicMock) -> None:
    advance = _match(main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON)
    bot.find_any_template.side_effect = [advance] * 5 + [None] * 5
    with patch.object(main, "monotonic", side_effect=count(step=IDLE_STEP_SECONDS)):
        bot._run_artifact_adventure(SCREENS, max_advances=None)
    assert bot.tap.call_count == 5


# --- Limited run --------------------------------------------------------------


def test_limit_stops_at_next_stage_screen(bot: MagicMock) -> None:
    advance = _match(main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON)
    _script_screens(bot, *[main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON] * 5)
    bot._run_artifact_adventure(SCREENS, max_advances=ADVANCE_LIMIT)
    assert bot.tap.call_count == ADVANCE_LIMIT
    assert all(c.args[0].template == advance.template for c in bot.tap.call_args_list)


def test_limit_stops_instead_of_starting_new_adventure(bot: MagicMock) -> None:
    _script_screens(
        bot,
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
        main.ARTIFACT_ADVENTURE_ACCEPT_BUTTON,
        main.ARTIFACT_ADVENTURE_START_BUTTON,
    )
    bot._run_artifact_adventure(SCREENS, max_advances=ADVANCE_LIMIT)
    templates = [c.args[0].template for c in bot.tap.call_args_list]
    assert templates == [
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
        main.ARTIFACT_ADVENTURE_ACCEPT_BUTTON,
    ]


def test_limit_still_dismisses_pending_confirm_screen(bot: MagicMock) -> None:
    _script_screens(
        bot,
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
        main.ARTIFACT_ADVENTURE_TAP_TO_CONTINUE,
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
    )
    bot._run_artifact_adventure(SCREENS, max_advances=1)
    templates = [c.args[0].template for c in bot.tap.call_args_list]
    assert templates == [
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
        main.ARTIFACT_ADVENTURE_TAP_TO_CONTINUE,
    ]


def test_limit_still_resolves_pending_fight_choice(bot: MagicMock) -> None:
    bot._fight_or_retreat = MagicMock()
    _script_screens(
        bot,
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
        main.ARTIFACT_ADVENTURE_RETREAT_BUTTON,
        main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
    )
    bot._run_artifact_adventure(SCREENS, max_advances=1)
    bot._fight_or_retreat.assert_called_once()


def test_zero_remaining_limit_taps_nothing_on_stage_screen(bot: MagicMock) -> None:
    _script_screens(bot, main.ARTIFACT_ADVENTURE_ADVANCE_BUTTON)
    bot._run_artifact_adventure(SCREENS, max_advances=0)
    bot.tap.assert_not_called()


# --- Fight or retreat ---------------------------------------------------------


@pytest.mark.parametrize(
    ("win_rate", "fights"),
    [(MIN_WIN_RATE, True), (MIN_WIN_RATE + 5, True), (MIN_WIN_RATE - 1, False)],
)
def test_fight_only_when_win_rate_reaches_minimum(
    bot: MagicMock, win_rate: int, fights: bool
) -> None:
    retreat = _match(main.ARTIFACT_ADVENTURE_RETREAT_BUTTON)
    fight = _match(main.ARTIFACT_ADVENTURE_FIGHT_BUTTON)
    bot._read_win_rate = MagicMock(return_value=win_rate)
    bot.find_any_template.return_value = fight
    bot._fight_or_retreat(retreat)
    bot.tap.assert_called_once_with(fight if fights else retreat, log=False)


def test_retreats_when_win_rate_unreadable(bot: MagicMock) -> None:
    retreat = _match(main.ARTIFACT_ADVENTURE_RETREAT_BUTTON)
    bot._read_win_rate = MagicMock(return_value=None)
    bot._fight_or_retreat(retreat)
    bot.tap.assert_called_once_with(retreat, log=False)
    bot.find_any_template.assert_not_called()


def test_retreats_when_fight_button_missing(bot: MagicMock) -> None:
    retreat = _match(main.ARTIFACT_ADVENTURE_RETREAT_BUTTON)
    bot._read_win_rate = MagicMock(return_value=MIN_WIN_RATE + 10)
    bot.find_any_template.return_value = None
    bot._fight_or_retreat(retreat)
    bot.tap.assert_called_once_with(retreat, log=False)


# --- Win rate OCR parsing -----------------------------------------------------


@pytest.mark.parametrize(
    ("ocr_text", "expected"),
    [
        ("T l thng 80% 5% 十", 85),
        ("Tỷ lệ thắng 80% + 5%", 85),
        ("thng 55 % 5%", 60),
        ("thng 90%", 90),
        ("không có số", None),
        ("", None),
    ],
)
def test_read_win_rate_sums_percentages(
    bot: MagicMock, ocr_text: str, expected: int | None
) -> None:
    bot.get_screenshot = MagicMock(return_value=np.zeros((1920, 1080, 3), np.uint8))
    with patch.object(main, "RapidOCRBackend") as backend:
        backend.return_value.extract_text.return_value = ocr_text
        assert bot._read_win_rate() == expected


def test_read_win_rate_ocrs_only_the_win_rate_line(bot: MagicMock) -> None:
    bot.get_screenshot = MagicMock(return_value=np.zeros((1920, 1080, 3), np.uint8))
    with patch.object(main, "RapidOCRBackend") as backend:
        backend.return_value.extract_text.return_value = ""
        bot._read_win_rate()
    crop = backend.return_value.extract_text.call_args.args[0]
    assert crop.shape[0] < 1920 * 0.1
    assert crop.shape[1] < 1080 * 0.5
