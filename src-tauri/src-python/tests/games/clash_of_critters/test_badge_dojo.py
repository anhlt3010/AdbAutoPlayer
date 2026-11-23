"""Tests for the entry of the Võ Đường Huy Hiệu command (Chế Độ and its banner)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from adb_auto_player.games.clash_of_critters import main
from adb_auto_player.games.clash_of_critters.badge_dojo import (
    BADGE_DOJO_BANNER,
    MODES_BUTTON,
)
from adb_auto_player.games.clash_of_critters.main import ClashOfCritters
from adb_auto_player.registries import COMMAND_REGISTRY


@pytest.fixture
def bot() -> MagicMock:
    """ClashOfCritters instance with device-facing methods mocked."""
    game = object.__new__(ClashOfCritters)
    game.wait_for_template = MagicMock(side_effect=["modes_match", "banner_match"])
    game.tap = MagicMock()
    game.open_eyes = MagicMock()
    return game


def test_open_badge_dojo_taps_modes_button_then_banner(bot: MagicMock) -> None:
    bot._open_badge_dojo()

    templates = [c.args[0] for c in bot.wait_for_template.call_args_list]
    assert templates == [MODES_BUTTON, BADGE_DOJO_BANNER]
    taps = [c.args[0] for c in bot.tap.call_args_list]
    assert taps == ["modes_match", "banner_match"]


def test_does_not_open_pinball_screen(bot: MagicMock) -> None:
    bot._open_pinball_screen = MagicMock()

    bot._open_badge_dojo()

    bot._open_pinball_screen.assert_not_called()


def test_command_is_in_che_do_category() -> None:
    commands = [
        c
        for module in COMMAND_REGISTRY.values()
        for name, c in module.items()
        if name.endswith(".badge_dojo")
    ]
    assert len(commands) == 1
    assert commands[0].menu_item.category == "Chế Độ"


@pytest.mark.parametrize("template", [MODES_BUTTON, BADGE_DOJO_BANNER])
def test_templates_exist(template: str) -> None:
    path = Path(main.__file__).parent / "templates" / template
    assert path.is_file()


def test_bundle_lists_tatari_dojo() -> None:
    bundle = Path(__file__).parents[4] / "tauri.bundle.templates.json"
    resources = json.loads(bundle.read_text(encoding="utf-8"))["bundle"]["resources"]
    assert any(key.endswith("clash_of_critters/tatari_dojo/") for key in resources)
