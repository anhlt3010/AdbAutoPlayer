"""Tests that the auto battle is wired into the Clash of Critters game."""

from adb_auto_player.games.clash_of_critters import main  # noqa: F401  (registers)
from adb_auto_player.games.clash_of_critters.auto_battle import AutoBattleMixin
from adb_auto_player.games.clash_of_critters.deploy import DeployMixin
from adb_auto_player.games.clash_of_critters.main import ClashOfCritters
from adb_auto_player.registries import COMMAND_REGISTRY

MODULE = "clash_of_critters"


def test_auto_battle_is_registered_in_the_battle_category() -> None:
    command = COMMAND_REGISTRY[MODULE][f"{MODULE}.auto_battle"]
    assert command.menu_item is not None
    assert command.menu_item.label == "Tự Động Chiến Đấu"
    assert command.menu_item.category == "Battle"


def test_the_old_battle_command_is_gone() -> None:
    assert f"{MODULE}.keep_game_running" not in COMMAND_REGISTRY[MODULE]
    assert not hasattr(ClashOfCritters, "keep_game_running")


def test_the_game_has_the_battle_mixins() -> None:
    assert issubclass(ClashOfCritters, AutoBattleMixin)
    assert issubclass(ClashOfCritters, DeployMixin)


def test_the_game_keeps_its_own_common_button_handling() -> None:
    # The mixin only declares it; the game supplies the real one.
    assert ClashOfCritters._tap_common_button is not AutoBattleMixin._tap_common_button
