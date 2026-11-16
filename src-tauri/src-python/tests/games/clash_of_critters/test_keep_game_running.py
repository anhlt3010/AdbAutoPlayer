"""Tests for Clash of Critters 'Keep Game Running' tick logic."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from adb_auto_player.games.clash_of_critters import main
from adb_auto_player.games.clash_of_critters.main import ClashOfCritters
from adb_auto_player.games.clash_of_critters.settings import Settings

STARTUP_WAIT = 7


@pytest.fixture
def bot() -> MagicMock:
    """ClashOfCritters instance with device-facing methods mocked."""
    game = object.__new__(ClashOfCritters)
    game.is_game_running = MagicMock(return_value=True)
    game.start_game = MagicMock()
    game.find_any_template = MagicMock(return_value=None)
    game.tap = MagicMock()
    game.find_all_template_matches = MagicMock(return_value=[])
    game._quick_deploy_done = False
    settings = Settings()
    settings.keep_alive.startup_wait_seconds = STARTUP_WAIT
    game.get_settings = MagicMock(return_value=settings)
    return game


def _match(template: str) -> SimpleNamespace:
    return SimpleNamespace(template=template)


def test_restarts_game_when_not_running(bot: MagicMock) -> None:
    bot.is_game_running.return_value = False
    with patch.object(main, "sleep") as sleep:
        bot._keep_alive_tick()
    bot.start_game.assert_called_once()
    sleep.assert_called_once_with(STARTUP_WAIT)
    bot.find_any_template.assert_not_called()
    bot.tap.assert_not_called()


def test_does_nothing_while_auto_battling(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(main.AUTO_BATTLING)
    bot._keep_alive_tick()
    bot.start_game.assert_not_called()
    bot.tap.assert_not_called()


def test_does_nothing_when_no_template_matches(bot: MagicMock) -> None:
    bot._keep_alive_tick()
    bot.tap.assert_not_called()


@pytest.mark.parametrize(
    "template",
    [main.HUB_BATTLE_BUTTON, main.STAGE_START_BUTTON, main.AUTO_BATTLE_BUTTON],
)
def test_taps_navigation_buttons(bot: MagicMock, template: str) -> None:
    match = _match(template)
    bot.find_any_template.return_value = match
    bot._keep_alive_tick()
    bot.tap.assert_called_once_with(match, log=False)


@pytest.mark.parametrize(
    "template", [main.OPEN_ALL_BUTTON, main.OK_BUTTON, main.MORE_GROUP_BUTTON]
)
def test_taps_common_buttons_on_any_screen(bot: MagicMock, template: str) -> None:
    button = _match(template)
    # Only the common-button lookup sees the button; nothing else is on screen.
    bot.find_any_template.side_effect = lambda templates: (
        button if template in templates else None
    )
    bot._keep_alive_tick()
    bot.tap.assert_called_once_with(button, log=False)


def test_common_button_takes_priority_over_navigation(bot: MagicMock) -> None:
    ok = _match(main.OK_BUTTON)
    hub = _match(main.HUB_BATTLE_BUTTON)
    bot.find_any_template.side_effect = lambda templates: (
        ok if main.OK_BUTTON in templates else hub
    )
    bot._keep_alive_tick()
    bot.tap.assert_called_once_with(ok, log=False)


def _prep_screen(bot: MagicMock, dislikes: int) -> tuple[SimpleNamespace, ...]:
    """Make the bot see the preparation screen with `dislikes` Dislike icons."""
    auto_button = _match(main.AUTO_BATTLE_BUTTON)
    quick_button = _match(main.QUICK_DEPLOY_BUTTON)
    bot.find_any_template.side_effect = lambda templates: (
        quick_button if templates == [main.QUICK_DEPLOY_BUTTON] else auto_button
    )
    bot.find_all_template_matches.return_value = [object()] * dislikes
    return auto_button, quick_button


def test_quick_deploy_when_dislikes_reach_threshold(bot: MagicMock) -> None:
    _, quick_button = _prep_screen(bot, dislikes=3)
    bot._keep_alive_tick()
    bot.tap.assert_called_once_with(quick_button, log=False)


def test_no_quick_deploy_below_threshold(bot: MagicMock) -> None:
    auto_button, _ = _prep_screen(bot, dislikes=2)
    bot._keep_alive_tick()
    bot.tap.assert_called_once_with(auto_button, log=False)


def test_quick_deploy_only_once_per_preparation_screen(bot: MagicMock) -> None:
    auto_button, quick_button = _prep_screen(bot, dislikes=5)
    bot._keep_alive_tick()
    bot._keep_alive_tick()
    assert [c.args[0] for c in bot.tap.call_args_list] == [quick_button, auto_button]


def test_quick_deploy_allowed_again_after_leaving_preparation(bot: MagicMock) -> None:
    _, quick_button = _prep_screen(bot, dislikes=5)
    bot._keep_alive_tick()
    bot.find_any_template.side_effect = None
    bot.find_any_template.return_value = _match(main.AUTO_BATTLING)
    bot._keep_alive_tick()
    _prep_screen(bot, dislikes=5)
    bot._keep_alive_tick()
    assert [c.args[0] for c in bot.tap.call_args_list] == [quick_button, quick_button]


def test_falls_back_to_auto_battle_when_quick_deploy_button_missing(
    bot: MagicMock,
) -> None:
    auto_button = _match(main.AUTO_BATTLE_BUTTON)
    bot.find_any_template.side_effect = lambda templates: (
        None if templates == [main.QUICK_DEPLOY_BUTTON] else auto_button
    )
    bot.find_all_template_matches.return_value = [object()] * 4
    bot._keep_alive_tick()
    bot.tap.assert_called_once_with(auto_button, log=False)
