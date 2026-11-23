"""Tests for the navigation of the Võ Đường Huy Hiệu command."""

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters import badge_dojo
from adb_auto_player.games.clash_of_critters.badge_dojo import (
    BADGE_DOJO_BANNER,
    DOJO_CLAIM_BADGE_BUTTON,
    DOJO_CLOSE_POINT,
    DOJO_GREAT_BUTTON,
    DOJO_RECEIVE_TEXT,
    DOJO_ELEMENTS,
    DOJO_SCREEN_MARKER,
    DOJO_START_BUTTON,
    DOJO_TAB_POINTS,
    MODES_BUTTON,
    DIALOG_TAP_POINT,
    REVEAL_BUTTON_POINT,
    BadgeDojoMixin,
    DojoFight,
)
from adb_auto_player.games.clash_of_critters.battle_layout import (
    BATTLE_LAYOUT,
    DOJO_LAYOUT,
)

RETURN_POLLS = 15


class _DojoBot(BadgeDojoMixin):
    """Concrete mixin (Game leaves `settings` abstract, `device` a property)."""

    device = None
    settings = None


def _match(template: str) -> SimpleNamespace:
    return SimpleNamespace(template=template)


@pytest.fixture
def bot() -> MagicMock:
    """Mixin instance with every device-facing method mocked."""
    game = object.__new__(_DojoBot)
    game.open_eyes = MagicMock()
    game.tap = MagicMock()
    game.get_screenshot = MagicMock(return_value=np.zeros((1920, 1080, 3), np.uint8))
    game.find_any_template = MagicMock(return_value=None)
    game._tap_common_button = MagicMock(return_value=False)
    game._open_badge_dojo = MagicMock()
    return game


@pytest.fixture(autouse=True)
def no_sleep():
    """Never really sleep."""
    with patch.object(badge_dojo, "sleep") as sleep:
        yield sleep


def _xy(point: object) -> tuple[int, int]:
    return point.x, point.y  # type: ignore[attr-defined]


def test_grey_tab_is_skipped_without_a_challenge_tap(bot: MagicMock) -> None:
    with patch.object(badge_dojo, "challenge_button_is_yellow", return_value=False):
        assert bot._enter_dojo_tab("water") is False
    assert [_xy(c.args[0]) for c in bot.tap.call_args_list] == [
        _xy(DOJO_TAB_POINTS["water"])
    ]


def test_yellow_tab_is_entered(bot: MagicMock) -> None:
    with patch.object(badge_dojo, "challenge_button_is_yellow", return_value=True):
        assert bot._enter_dojo_tab("grass") is True


def test_all_tabs_grey_ends_without_a_fight(
    bot: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(return_value=False)
    bot._play_dojo = MagicMock()
    with caplog.at_level(logging.INFO):
        bot._badge_dojo()
    bot._play_dojo.assert_not_called()
    assert "Bỏ qua (nút Thử Thách xám): Thủy, Hỏa, Thảo, Thạch, Lôi" in caplog.text


def test_every_element_is_visited_in_order(bot: MagicMock) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(return_value=True)
    bot._play_dojo = MagicMock(return_value=False)
    bot._badge_dojo()
    entered = [c.args[0] for c in bot._enter_dojo_tab.call_args_list]
    played = [c.args[0] for c in bot._play_dojo.call_args_list]
    assert entered == list(DOJO_ELEMENTS)
    assert played == list(DOJO_ELEMENTS)


def test_summary_is_logged_with_the_fights(
    bot: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(side_effect=lambda e: e == "grass")

    def play(element: str, fights: list[DojoFight], resume: bool = False) -> bool:
        fights.append(DojoFight(element, "4-2", 1, 1, True))
        return False

    bot._play_dojo = MagicMock(side_effect=play)
    with caplog.at_level(logging.INFO):
        bot._badge_dojo()
    assert "Thảo 4-2 | đội hình 1 | lần 1 | Thắng" in caplog.text
    assert "Bỏ qua (nút Thử Thách xám): Thủy, Hỏa, Thạch, Lôi" in caplog.text


def test_dojo_layout_is_used_during_the_run_and_restored_after(
    bot: MagicMock,
) -> None:
    seen: list[object] = []
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(return_value=True)
    bot._play_dojo = MagicMock(side_effect=lambda *_, **__: seen.append(bot._layout))
    bot._badge_dojo()
    assert seen
    assert all(layout is DOJO_LAYOUT for layout in seen)
    assert bot._layout is BATTLE_LAYOUT


def test_layout_is_restored_when_a_dojo_raises(bot: MagicMock) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(return_value=True)
    bot._play_dojo = MagicMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        bot._badge_dojo()
    assert bot._layout is BATTLE_LAYOUT


def test_stops_when_the_dojo_screen_cannot_be_found(
    bot: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=False)
    bot._enter_dojo_tab = MagicMock()
    with caplog.at_level(logging.ERROR):
        bot._badge_dojo()
    bot._enter_dojo_tab.assert_not_called()
    assert "Võ Đường screen not found" in caplog.text


def test_return_to_dojo_screen_from_camp(bot: MagicMock) -> None:
    bot.find_any_template.side_effect = [
        _match(MODES_BUTTON),
        _match(DOJO_SCREEN_MARKER),
    ]
    assert bot._return_to_dojo_screen() is True
    bot._open_badge_dojo.assert_called_once_with()


def test_return_to_dojo_screen_from_the_stage_list(bot: MagicMock) -> None:
    bot.find_any_template.side_effect = [
        _match(DOJO_START_BUTTON),
        _match(DOJO_SCREEN_MARKER),
    ]
    assert bot._return_to_dojo_screen() is True
    assert _xy(bot.tap.call_args.args[0]) == _xy(DOJO_CLOSE_POINT)


def test_return_to_dojo_screen_from_the_banner_screen(bot: MagicMock) -> None:
    banner = _match(BADGE_DOJO_BANNER)
    bot.find_any_template.side_effect = [banner, _match(DOJO_SCREEN_MARKER)]
    assert bot._return_to_dojo_screen() is True
    assert bot.tap.call_args.args[0] is banner


def test_return_to_dojo_screen_gives_up(bot: MagicMock) -> None:
    assert bot._return_to_dojo_screen() is False
    assert bot.find_any_template.call_count == RETURN_POLLS


def test_return_to_dojo_screen_taps_common_buttons_first(bot: MagicMock) -> None:
    bot._tap_common_button.side_effect = [True, False]
    bot.find_any_template.return_value = _match(DOJO_SCREEN_MARKER)
    assert bot._return_to_dojo_screen() is True
    assert bot.find_any_template.call_count == 1


def test_tray_element_is_cleared_after_the_run(bot: MagicMock) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(return_value=True)
    bot._play_dojo = MagicMock(
        side_effect=lambda e, _, **__: setattr(bot, "_tray_element", e)
    )
    bot._badge_dojo()
    assert bot._tray_element is None


def test_a_run_started_on_the_dojo_screen_does_not_open_the_modes_screen(
    bot: MagicMock,
) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(return_value=False)
    bot._badge_dojo()
    bot._open_badge_dojo.assert_not_called()


def test_return_to_dojo_screen_taps_through_the_reveal(bot: MagicMock) -> None:
    assets = Path(__file__).parents[5] / "docs" / "superpowers" / "specs" / "assets"
    reveal = cv2.imread(str(assets / "dojo_more_group_screen.png"))
    blank = np.zeros((1920, 1080, 3), np.uint8)
    bot.get_screenshot.side_effect = [reveal, blank]
    bot.find_any_template.return_value = _match(DOJO_SCREEN_MARKER)
    assert bot._return_to_dojo_screen() is True
    point = bot.tap.call_args.args[0]
    assert (point.x, point.y) == (REVEAL_BUTTON_POINT.x, REVEAL_BUTTON_POINT.y)


def test_a_dojo_won_to_the_end_is_entered_again(bot: MagicMock) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(return_value=True)
    answers = {"grass": [True, False]}
    bot._play_dojo = MagicMock(
        side_effect=lambda element, fights, resume=False: answers.get(
            element, [False]
        ).pop(0)
    )
    bot._badge_dojo()
    grass = [c for c in bot._play_dojo.call_args_list if c.args[0] == "grass"]
    assert len(grass) == 2
    assert grass[0].kwargs.get("resume", False) is False
    assert grass[1].kwargs == {"resume": True}


def test_a_dojo_is_not_entered_again_when_its_button_turned_grey(
    bot: MagicMock,
) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._play_dojo = MagicMock(return_value=True)
    states = iter([True, False])  # yellow when first visited, grey after the win
    bot._enter_dojo_tab = MagicMock(side_effect=lambda e: next(states, False))
    bot._badge_dojo()
    assert bot._play_dojo.call_count == 1


def test_replays_of_one_dojo_are_capped(bot: MagicMock) -> None:
    bot._return_to_dojo_screen = MagicMock(return_value=True)
    bot._enter_dojo_tab = MagicMock(side_effect=lambda e: e == "grass")
    bot._play_dojo = MagicMock(return_value=True)
    bot._badge_dojo()
    assert 1 < bot._play_dojo.call_count <= badge_dojo.MAX_REPLAYS + 1


def test_return_to_dojo_screen_claims_a_pending_badge(bot: MagicMock) -> None:
    claim = _match(DOJO_CLAIM_BADGE_BUTTON)
    bot.find_any_template.side_effect = [claim, _match(DOJO_SCREEN_MARKER)]
    assert bot._return_to_dojo_screen() is True
    assert bot.tap.call_args.args[0] is claim


def test_return_to_dojo_screen_closes_the_master_dialog(bot: MagicMock) -> None:
    assets = Path(__file__).parents[5] / "docs" / "superpowers" / "specs" / "assets"
    dialog = cv2.imread(str(assets / "dojo_master_dialog.png"))
    blank = np.zeros((1920, 1080, 3), np.uint8)
    bot.get_screenshot.side_effect = [dialog, blank]
    bot.find_any_template.return_value = _match(DOJO_SCREEN_MARKER)
    assert bot._return_to_dojo_screen() is True
    point = bot.tap.call_args.args[0]
    assert (point.x, point.y) == (DIALOG_TAP_POINT.x, DIALOG_TAP_POINT.y)


@pytest.mark.parametrize("template", [DOJO_RECEIVE_TEXT, DOJO_GREAT_BUTTON])
def test_return_to_dojo_screen_goes_through_the_badge_screens(
    bot: MagicMock, template: str
) -> None:
    # After the badge is claimed: "Nhận" on the statue, then "Tuyệt vời!".
    shown = _match(template)
    bot.find_any_template.side_effect = [shown, _match(DOJO_SCREEN_MARKER)]
    assert bot._return_to_dojo_screen() is True
    assert bot.tap.call_args.args[0] is shown
