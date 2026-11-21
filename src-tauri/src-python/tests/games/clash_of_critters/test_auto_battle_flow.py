"""Tests for the Clash of Critters auto battle state machine."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from adb_auto_player.games.clash_of_critters import auto_battle
from adb_auto_player.games.clash_of_critters.auto_battle import (
    DEFEAT_TITLE,
    FIGHT_BUTTON,
    HUB_BATTLE_BUTTON,
    PREP_REPORT_ICON,
    QUICK_DEPLOY_BUTTON,
    RETRY_BUTTON,
    STAGE_MAP_MARKER,
    AutoBattleMixin,
)
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
    StageId,
)
from adb_auto_player.games.clash_of_critters.settings import Settings

STARTUP_WAIT = 7
IDLE_LIMIT = 100
MAX_ATTEMPTS = 2
BOSS = StageId(15, 50)
NORMAL = StageId(15, 49)


class _Bot(AutoBattleMixin):
    """Concrete mixin (Game leaves `settings` abstract, `device` a property)."""

    device = None
    settings = None  # replaced per instance

    def _tap_common_button(self) -> bool:
        return False


def _match(template: str) -> SimpleNamespace:
    return SimpleNamespace(template=template)


def xy(point) -> tuple[int, int]:
    """Point equality is always true in this repo, so compare coordinates."""
    return point.x, point.y


@pytest.fixture
def bot() -> MagicMock:
    """AutoBattleMixin instance with every device-facing method mocked."""
    game = object.__new__(_Bot)
    settings = Settings()
    settings.auto_battle.startup_wait_seconds = STARTUP_WAIT
    settings.auto_battle.idle_limit_seconds = IDLE_LIMIT
    settings.auto_battle.max_formation_attempts = MAX_ATTEMPTS
    game.settings = settings
    game.is_game_running = MagicMock(return_value=True)
    game.start_game = MagicMock()
    game.tap = MagicMock()
    game._tap_common_button = MagicMock(return_value=False)
    game._read_stage = MagicMock(return_value=NORMAL)
    game._deploy_formation = MagicMock(return_value=15)
    game.find_any_template = MagicMock(return_value=None)
    game.template_dir = MagicMock()
    game._screens: set[str] = set()
    return game


@pytest.fixture(autouse=True)
def no_sleep():
    """Never really sleep; expose the patched sleep to tests."""
    with patch.object(auto_battle, "sleep") as sleep:
        yield sleep


@pytest.fixture(autouse=True)
def a_formation():
    """Every stage has a formation file unless a test says otherwise."""
    formation = Formation(BOSS, (FormationUnit(1, 1, "fire-3", "fire-3-2", 2, False),))
    with patch.object(auto_battle, "load_formation", return_value=formation) as load:
        yield load


def _show(bot: MagicMock, *templates: str) -> None:
    """Make exactly these templates visible on screen."""
    present = {t: _match(t) for t in templates}

    def find(wanted: list[str], **_: object) -> SimpleNamespace | None:
        for template in wanted:
            if template in present:
                return present[template]
        return None

    bot.find_any_template.side_effect = find


def _tapped(bot: MagicMock) -> list[str | tuple[int, int]]:
    """What was tapped: a template name or a point's coordinates."""
    out: list[str | tuple[int, int]] = []
    for c in bot.tap.call_args_list:
        target = c.args[0]
        out.append(target.template if hasattr(target, "template") else xy(target))
    return out


# --- game and generic screens --------------------------------------------------------


def test_restarts_game_when_not_running(bot: MagicMock, no_sleep: MagicMock) -> None:
    bot.is_game_running.return_value = False
    assert bot._auto_battle_step() is True
    bot.start_game.assert_called_once()
    no_sleep.assert_called_once_with(STARTUP_WAIT)
    bot.tap.assert_not_called()


def test_common_button_takes_priority(bot: MagicMock) -> None:
    bot._tap_common_button.return_value = True
    _show(bot, HUB_BATTLE_BUTTON)
    assert bot._auto_battle_step() is True
    bot.tap.assert_not_called()


def test_camp_screen_opens_the_stage_map(bot: MagicMock) -> None:
    _show(bot, HUB_BATTLE_BUTTON)
    bot._auto_battle_step()
    assert _tapped(bot) == [HUB_BATTLE_BUTTON]


def test_stage_map_presses_the_start_button(bot: MagicMock) -> None:
    _show(bot, STAGE_MAP_MARKER)
    bot._auto_battle_step()
    assert _tapped(bot) == [(540, 1690)]


def test_defeat_taps_retry(bot: MagicMock) -> None:
    _show(bot, DEFEAT_TITLE, RETRY_BUTTON)
    assert bot._auto_battle_step() is True
    assert _tapped(bot) == [RETRY_BUTTON]


# --- the preparation screen ----------------------------------------------------------


def test_normal_stage_uses_quick_deploy_once_then_fights(bot: MagicMock) -> None:
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    bot._auto_battle_step()
    bot._auto_battle_step()
    bot._auto_battle_step()
    assert _tapped(bot) == [QUICK_DEPLOY_BUTTON, FIGHT_BUTTON, FIGHT_BUTTON]
    bot._deploy_formation.assert_not_called()


def test_boss_stage_deploys_the_formation_then_fights(bot: MagicMock) -> None:
    bot._read_stage.return_value = BOSS
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    assert bot._auto_battle_step() is True
    bot._deploy_formation.assert_called_once()
    assert _tapped(bot) == [FIGHT_BUTTON]


def test_report_icon_forces_the_formation_on_a_normal_stage(bot: MagicMock) -> None:
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON, PREP_REPORT_ICON)
    bot._auto_battle_step()
    bot._deploy_formation.assert_called_once()
    assert _tapped(bot) == [FIGHT_BUTTON]


def test_unreadable_stage_falls_back_to_quick_deploy(bot: MagicMock) -> None:
    bot._read_stage.return_value = None
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON, PREP_REPORT_ICON)
    bot._auto_battle_step()
    bot._deploy_formation.assert_not_called()
    assert _tapped(bot) == [QUICK_DEPLOY_BUTTON]


def test_missing_formation_falls_back_to_quick_deploy(
    bot: MagicMock, a_formation: MagicMock
) -> None:
    a_formation.return_value = None
    bot._read_stage.return_value = BOSS
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    bot._auto_battle_step()
    bot._deploy_formation.assert_not_called()
    assert _tapped(bot) == [QUICK_DEPLOY_BUTTON]


def test_nothing_placed_means_no_fight_and_stop(bot: MagicMock) -> None:
    bot._read_stage.return_value = BOSS
    bot._deploy_formation.return_value = 0
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    assert bot._auto_battle_step() is False
    assert _tapped(bot) == []


# --- trying the formation again and again --------------------------------------------


def _boss_visit(bot: MagicMock) -> bool:
    bot._read_stage.return_value = BOSS
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    return bot._auto_battle_step()


def test_formation_attempts_are_capped(bot: MagicMock) -> None:
    results = [_boss_visit(bot) for _ in range(MAX_ATTEMPTS + 1)]
    assert results == [True] * MAX_ATTEMPTS + [False]
    assert bot._deploy_formation.call_count == MAX_ATTEMPTS


def test_attempts_start_again_on_a_new_stage(bot: MagicMock) -> None:
    for _ in range(MAX_ATTEMPTS):
        _boss_visit(bot)
    bot._read_stage.return_value = StageId(15, 60)
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    assert bot._auto_battle_step() is True
    assert bot._deploy_formation.call_count == MAX_ATTEMPTS + 1


# --- quick deploy is pressed once per visit ------------------------------------------


def test_quick_deploy_is_pressed_again_on_the_next_visit(bot: MagicMock) -> None:
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    bot._auto_battle_step()
    bot._auto_battle_step()
    _show(bot)  # the fight itself: no known screen
    bot._auto_battle_step()
    _show(bot, QUICK_DEPLOY_BUTTON, FIGHT_BUTTON)
    bot._auto_battle_step()
    assert _tapped(bot) == [QUICK_DEPLOY_BUTTON, FIGHT_BUTTON, QUICK_DEPLOY_BUTTON]


# --- unknown screens (for example a won fight) ---------------------------------------


def test_stops_after_the_idle_limit_on_an_unknown_screen(bot: MagicMock) -> None:
    clock = iter([1000.0, 1000.0 + IDLE_LIMIT - 1, 1000.0 + IDLE_LIMIT])
    with patch.object(auto_battle, "monotonic", side_effect=lambda: next(clock)):
        assert bot._auto_battle_step() is True  # starts the idle timer
        assert bot._auto_battle_step() is True  # still within the limit
        assert bot._auto_battle_step() is False  # limit reached


def test_a_known_screen_restarts_the_idle_timer(bot: MagicMock) -> None:
    clock = iter([1000.0, 5000.0, 5000.0 + IDLE_LIMIT - 1])
    with patch.object(auto_battle, "monotonic", side_effect=lambda: next(clock)):
        bot._auto_battle_step()  # unknown, timer starts at 1000
        _show(bot, HUB_BATTLE_BUTTON)
        bot._auto_battle_step()  # known screen: no clock needed
        _show(bot)
        assert bot._auto_battle_step() is True  # unknown again, timer restarts
        assert bot._auto_battle_step() is True
