"""Tests for the stage loop of the Võ Đường Huy Hiệu command."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from adb_auto_player.exceptions import GameTimeoutError
from adb_auto_player.games.clash_of_critters import badge_dojo
from adb_auto_player.games.clash_of_critters.auto_battle import (
    DEFEAT_TITLE,
    QUICK_DEPLOY_BUTTON,
    VICTORY_TITLE,
)
from adb_auto_player.games.clash_of_critters.badge_dojo import (
    CHALLENGE_POINT,
    DOJO_CLAIM_BADGE_BUTTON,
    DOJO_CONTINUE_BUTTON,
    DOJO_DEFEAT_BACK_BUTTON,
    DOJO_NEW_TRAIT_TITLE,
    DOJO_RETRY_BUTTON,
    DOJO_SCREEN_MARKER,
    DOJO_VICTORY_BACK_BUTTON,
    DOJO_START_BUTTON,
    DOJO_CLOSE_POINT,
    NEW_TRAIT_CLOSE_POINT,
    PREP_BACK_POINT,
    REVEAL_BUTTON_POINT,
    BadgeDojoMixin,
    DojoFight,
)
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
    StageId,
)

MAX_ATTEMPTS = 3
STAGE_42 = StageId(4, 2)
STAGE_43 = StageId(4, 3)
UNREADABLE_POLLS = 3


class _DojoBot(BadgeDojoMixin):
    """Concrete mixin (Game leaves `settings` abstract, `device` a property)."""

    device = None
    settings = None


def _match(template: str) -> SimpleNamespace:
    return SimpleNamespace(template=template)


def _formation(index: int = 0) -> Formation:
    unit = FormationUnit(1, 1, "grass-4", "grass-4-2", 2, False)
    return Formation(STAGE_42, (unit,), index=index)


@pytest.fixture
def bot() -> MagicMock:
    """Mixin instance with every device-facing method mocked."""
    game = object.__new__(_DojoBot)
    game.settings = SimpleNamespace(
        auto_battle=SimpleNamespace(
            max_formation_attempts=MAX_ATTEMPTS,
            idle_limit_seconds=300,
            poll_interval_seconds=2,
        )
    )
    game.template_dir = Path("games/clash_of_critters/templates")
    game.find_any_template = MagicMock(return_value=None)
    game.wait_for_template = MagicMock()
    game.tap = MagicMock()
    game._tap_common_button = MagicMock(return_value=False)
    game._read_stage = MagicMock(return_value=STAGE_42)
    game._play_plan_step = MagicMock(return_value=True)
    game._tap_fight = MagicMock()
    game.get_screenshot = MagicMock(return_value=np.zeros((1920, 1080, 3), np.uint8))
    return game


@pytest.fixture(autouse=True)
def no_sleep():
    """Never really sleep."""
    with patch.object(badge_dojo, "sleep") as sleep:
        yield sleep


def _taps(bot: MagicMock) -> list[tuple[int, int]]:
    """Coordinates of every tap on a plain point or a match (Point equals all)."""
    return [(c.args[0].x, c.args[0].y) for c in bot.tap.call_args_list]


def test_new_trait_popup_is_tapped_away(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(DOJO_NEW_TRAIT_TITLE)
    assert bot._dojo_step("grass", []) == "go"
    assert _taps(bot) == [(NEW_TRAIT_CLOSE_POINT.x, NEW_TRAIT_CLOSE_POINT.y)]


def test_prep_screen_loads_the_plan_and_plays_a_step(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(QUICK_DEPLOY_BUTTON)
    formation = _formation()
    with patch.object(badge_dojo, "load_dojo_formations") as loader:
        loader.return_value = (formation,)
        assert bot._dojo_step("grass", []) == "go"
    root = Path("games/clash_of_critters/tatari_dojo")
    loader.assert_called_once_with(root, "grass", STAGE_42)
    assert bot._plan_steps == [formation]
    bot._play_plan_step.assert_called_once_with(STAGE_42, False, None)


def test_unreadable_stage_leaves_after_three_polls(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(QUICK_DEPLOY_BUTTON)
    bot._read_stage.return_value = None
    results = [bot._dojo_step("grass", []) for _ in range(UNREADABLE_POLLS)]
    assert results == ["go", "go", "done"]
    bot._play_plan_step.assert_not_called()
    bot._tap_fight.assert_not_called()
    assert _taps(bot) == [(PREP_BACK_POINT.x, PREP_BACK_POINT.y)]


def test_stage_without_a_formation_file_leaves_without_fighting(
    bot: MagicMock,
) -> None:
    bot.find_any_template.return_value = _match(QUICK_DEPLOY_BUTTON)
    with patch.object(badge_dojo, "load_dojo_formations", return_value=()):
        assert bot._dojo_step("grass", []) == "done"
    bot._play_plan_step.assert_not_called()
    assert _taps(bot) == [(PREP_BACK_POINT.x, PREP_BACK_POINT.y)]


def test_a_plan_step_that_cannot_be_played_leaves(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(QUICK_DEPLOY_BUTTON)
    bot._play_plan_step.return_value = False
    with patch.object(badge_dojo, "load_dojo_formations") as loader:
        loader.return_value = (_formation(),)
        assert bot._dojo_step("grass", []) == "done"
    assert _taps(bot) == [(PREP_BACK_POINT.x, PREP_BACK_POINT.y)]


def test_same_visit_only_presses_fight_again(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(QUICK_DEPLOY_BUTTON)
    bot._prep_phase = "formation"
    assert bot._dojo_step("grass", []) == "go"
    bot._tap_fight.assert_called_once_with()
    bot._play_plan_step.assert_not_called()


def test_victory_records_and_continues(bot: MagicMock) -> None:
    continue_match = _match(DOJO_CONTINUE_BUTTON)
    bot.find_any_template.side_effect = [_match(VICTORY_TITLE), continue_match]
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation()]
    bot._plan_pos, bot._plan_fights = 0, 2
    fights: list[DojoFight] = []
    assert bot._dojo_step("grass", fights) == "go"
    assert fights == [DojoFight("grass", "4-2", 1, 2, True)]
    assert bot.tap.call_args.args[0] is continue_match
    assert bot._plan_stage is None


def _real_plan_bot(bot: MagicMock, counter: int) -> None:
    """Make `bot` run the real `_play_plan_step`, with a field that shows `counter`."""
    bot._play_plan_step = lambda *args: BadgeDojoMixin._play_plan_step(bot, *args)
    bot._deploy_current_step = MagicMock(return_value=True)
    bot._read_deployed_count = MagicMock(return_value=counter)


def _win_then_prepare_next_stage(bot: MagicMock, fights: list[DojoFight]) -> None:
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation()]
    bot._plan_pos, bot._plan_fights = 0, 1
    bot.find_any_template.side_effect = [
        _match(VICTORY_TITLE),
        _match(DOJO_CONTINUE_BUTTON),
        _match(QUICK_DEPLOY_BUTTON),
    ]
    bot._read_stage.return_value = STAGE_43
    bot._dojo_step("grass", fights)
    with patch.object(badge_dojo, "load_dojo_formations") as loader:
        loader.return_value = (_formation(),)
        bot._dojo_step("grass", fights)
    loader.assert_called_once()


def test_win_then_next_stage_keeps_the_field_and_fights(bot: MagicMock) -> None:
    _real_plan_bot(bot, counter=5)  # the game keeps the field after a win
    _win_then_prepare_next_stage(bot, [])
    bot._deploy_current_step.assert_not_called()
    bot._tap_fight.assert_called_once_with()
    assert bot._plan_stage == STAGE_43  # loaded, for a loss that needs a deploy
    assert bot._plan_fights == 0  # a kept fight is not part of the plan


def test_win_then_next_stage_deploys_when_the_field_is_empty(
    bot: MagicMock,
) -> None:
    _real_plan_bot(bot, counter=0)
    _win_then_prepare_next_stage(bot, [])
    bot._deploy_current_step.assert_called_once_with(STAGE_43)


def test_a_kept_fight_is_recorded_as_kept(bot: MagicMock) -> None:
    _real_plan_bot(bot, counter=5)
    fights: list[DojoFight] = []
    _win_then_prepare_next_stage(bot, fights)
    bot.find_any_template.side_effect = [
        _match(VICTORY_TITLE),
        _match(DOJO_CONTINUE_BUTTON),
    ]
    bot._dojo_step("grass", fights)
    assert fights[-1] == DojoFight("grass", "4-3", 0, 1, True)


def test_lost_kept_fight_then_deploys_the_stage_formation(bot: MagicMock) -> None:
    _real_plan_bot(bot, counter=5)
    fights: list[DojoFight] = []
    _win_then_prepare_next_stage(bot, fights)
    bot.find_any_template.side_effect = [
        _match(DEFEAT_TITLE),
        _match(DOJO_RETRY_BUTTON),
        _match(QUICK_DEPLOY_BUTTON),
    ]
    bot._dojo_step("grass", fights)  # the kept fight is lost
    bot._dojo_step("grass", fights)  # back on the preparation screen
    assert fights[-1] == DojoFight("grass", "4-3", 0, 1, False)
    bot._deploy_current_step.assert_called_once_with(STAGE_43)


def test_a_loss_clears_the_kept_field(bot: MagicMock) -> None:
    bot._keep_field = True
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation(0), _formation(1)]
    bot._plan_pos, bot._plan_fights = 0, 1
    bot.find_any_template.side_effect = [_match(DEFEAT_TITLE), None]
    bot._dojo_step("grass", [])
    assert bot._keep_field is False


def test_play_dojo_starts_without_a_kept_field(bot: MagicMock) -> None:
    bot._keep_field = True
    bot.wait_for_template.return_value = _match(DOJO_START_BUTTON)
    bot._dojo_step = MagicMock(return_value="done")
    bot._play_dojo("grass", [])
    assert bot._keep_field is False


def test_defeat_retries_while_formations_remain(bot: MagicMock) -> None:
    retry = _match(DOJO_RETRY_BUTTON)
    bot.find_any_template.side_effect = [_match(DEFEAT_TITLE), retry]
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation(0), _formation(1)]
    bot._plan_pos, bot._plan_fights = 0, 1
    fights: list[DojoFight] = []
    assert bot._dojo_step("grass", fights) == "go"
    assert fights == [DojoFight("grass", "4-2", 1, 1, False)]
    assert bot.tap.call_args.args[0] is retry


def test_defeat_on_an_exhausted_plan_goes_back_and_ends_the_dojo(
    bot: MagicMock,
) -> None:
    back = _match(DOJO_DEFEAT_BACK_BUTTON)
    bot.find_any_template.side_effect = [_match(DEFEAT_TITLE), back]
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation(0), _formation(1)]
    bot._plan_pos, bot._plan_fights = 1, MAX_ATTEMPTS
    fights: list[DojoFight] = []
    assert bot._dojo_step("grass", fights) == "done"
    assert fights == [DojoFight("grass", "4-2", 2, MAX_ATTEMPTS, False)]
    assert bot.tap.call_args.args[0] is back


def test_unknown_screen_idle_ends_only_the_element(bot: MagicMock) -> None:
    bot._wait_on_unknown_screen = MagicMock(return_value=False)
    assert bot._dojo_step("grass", []) == "done"


def test_unknown_screen_before_the_limit_keeps_going(bot: MagicMock) -> None:
    bot._wait_on_unknown_screen = MagicMock(return_value=True)
    assert bot._dojo_step("grass", []) == "go"


def test_common_button_is_tapped_first(bot: MagicMock) -> None:
    bot._tap_common_button.return_value = True
    assert bot._dojo_step("grass", []) == "go"
    bot.find_any_template.assert_not_called()


def test_play_dojo_taps_challenge_then_start(bot: MagicMock) -> None:
    start = _match(DOJO_START_BUTTON)
    bot.wait_for_template.return_value = start
    bot._dojo_step = MagicMock(return_value="done")
    bot._play_dojo("grass", [])
    assert (
        bot.tap.call_args_list[0].args[0].x,
        bot.tap.call_args_list[0].args[0].y,
    ) == (
        CHALLENGE_POINT.x,
        CHALLENGE_POINT.y,
    )
    assert bot.tap.call_args_list[1].args[0] is start
    assert bot.wait_for_template.call_args.args[0] == DOJO_START_BUTTON


def test_play_dojo_resets_the_plan(bot: MagicMock) -> None:
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation()]
    bot._plan_pos, bot._plan_fights = 1, 2
    bot.wait_for_template.return_value = _match(DOJO_START_BUTTON)
    bot._dojo_step = MagicMock(return_value="done")
    bot._play_dojo("water", [])
    assert (bot._plan_stage, bot._plan_steps) == (None, None)
    assert (bot._plan_pos, bot._plan_fights) == (0, 0)


def test_a_result_screen_seen_twice_is_recorded_once(bot: MagicMock) -> None:
    retry = _match(DOJO_RETRY_BUTTON)
    bot.find_any_template.side_effect = [
        _match(DEFEAT_TITLE),
        retry,
        _match(DEFEAT_TITLE),
        retry,
    ]
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation(0), _formation(1)]
    bot._plan_pos, bot._plan_fights = 0, 1
    fights: list[DojoFight] = []
    bot._dojo_step("grass", fights)
    bot._dojo_step("grass", fights)
    assert len(fights) == 1
    assert bot.tap.call_count == 2  # the retry button is pressed again


def test_a_new_fight_after_a_result_is_recorded_again(bot: MagicMock) -> None:
    retry = _match(DOJO_RETRY_BUTTON)
    bot.find_any_template.side_effect = [
        _match(DEFEAT_TITLE),
        retry,
        None,  # the fight itself: no known screen
        _match(DEFEAT_TITLE),
        retry,
    ]
    bot._wait_on_unknown_screen = MagicMock(return_value=True)
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation(0), _formation(1)]
    bot._plan_pos, bot._plan_fights = 0, 1
    fights: list[DojoFight] = []
    for _ in range(3):
        bot._dojo_step("grass", fights)
    assert len(fights) == 2


STUCK_POLLS = 200  # more than idle_limit_seconds / poll_interval_seconds (150)


def test_victory_screen_without_a_continue_button_ends_the_dojo(
    bot: MagicMock,
) -> None:
    bot.find_any_template.side_effect = lambda templates: (
        _match(VICTORY_TITLE) if VICTORY_TITLE in templates else None
    )
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation()]
    bot._plan_pos, bot._plan_fights = 0, 1
    fights: list[DojoFight] = []
    results = [bot._dojo_step("grass", fights) for _ in range(STUCK_POLLS)]
    assert "done" in results
    assert len(fights) == 1


def test_a_changing_screen_is_never_stuck(bot: MagicMock) -> None:
    screens = [VICTORY_TITLE, QUICK_DEPLOY_BUTTON] * (STUCK_POLLS // 2)
    bot.find_any_template.side_effect = lambda templates: (
        _match(screens.pop()) if len(templates) > 1 else None
    )
    bot._dojo_prepare = MagicMock(return_value="go")
    results = [bot._dojo_step("grass", []) for _ in range(STUCK_POLLS)]
    assert "done" not in results


def test_stage_list_seen_in_the_loop_presses_bat_dau(bot: MagicMock) -> None:
    start = _match(DOJO_START_BUTTON)
    bot.find_any_template.side_effect = lambda templates: (
        start if DOJO_START_BUTTON in templates else None
    )
    assert bot._dojo_step("grass", []) == "go"
    bot.tap.assert_called_once()
    assert bot.tap.call_args.args[0] is start


def test_dojo_screen_seen_in_the_loop_ends_the_element(bot: MagicMock) -> None:
    bot.find_any_template.return_value = _match(DOJO_SCREEN_MARKER)
    assert bot._dojo_step("grass", []) == "done"
    bot.tap.assert_not_called()


def test_missing_start_button_closes_the_stage_list(bot: MagicMock) -> None:
    bot.wait_for_template.side_effect = GameTimeoutError("no Bắt đầu")
    bot._dojo_step = MagicMock()
    bot._play_dojo("grass", [])
    bot._dojo_step.assert_not_called()
    last = bot.tap.call_args.args[0]
    assert (last.x, last.y) == (DOJO_CLOSE_POINT.x, DOJO_CLOSE_POINT.y)


def test_play_dojo_tells_the_deploy_which_element_the_tray_holds(
    bot: MagicMock,
) -> None:
    bot.wait_for_template.return_value = _match(DOJO_START_BUTTON)
    bot._dojo_step = MagicMock(return_value="done")
    bot._play_dojo("water", [])
    assert bot._tray_element == "water"


REVEAL_CAPTURE = (
    Path(__file__).parents[5]
    / "docs"
    / "superpowers"
    / "specs"
    / "assets"
    / "dojo_more_group_screen.png"
)


def test_reveal_screen_is_tapped_through(bot: MagicMock) -> None:
    bot.get_screenshot.return_value = cv2.imread(str(REVEAL_CAPTURE))
    assert bot._dojo_step("grass", []) == "go"
    bot.find_any_template.assert_not_called()
    point = bot.tap.call_args.args[0]
    assert (point.x, point.y) == (REVEAL_BUTTON_POINT.x, REVEAL_BUTTON_POINT.y)


def _victory_screen(bot: MagicMock, buttons: dict[str, SimpleNamespace]) -> None:
    """A victory screen showing the given buttons (template -> match)."""

    def find(templates: list[str]) -> SimpleNamespace | None:
        if VICTORY_TITLE in templates:
            return _match(VICTORY_TITLE)
        return next((buttons[t] for t in templates if t in buttons), None)

    bot.find_any_template.side_effect = find
    bot._plan_stage, bot._plan_steps = STAGE_42, [_formation()]
    bot._plan_pos, bot._plan_fights = 0, 1


def test_victory_without_continue_goes_back_after_two_polls(bot: MagicMock) -> None:
    back = _match(DOJO_VICTORY_BACK_BUTTON)
    _victory_screen(bot, {DOJO_VICTORY_BACK_BUTTON: back})
    fights: list[DojoFight] = []
    assert bot._dojo_step("grass", fights) == "go"  # "Tiếp tục" may still be coming
    bot.tap.assert_not_called()
    assert bot._dojo_step("grass", fights) == "again"
    assert bot.tap.call_args.args[0] is back
    assert len(fights) == 1


def test_victory_with_continue_never_goes_back(bot: MagicMock) -> None:
    cont = _match(DOJO_CONTINUE_BUTTON)
    _victory_screen(
        bot,
        {DOJO_CONTINUE_BUTTON: cont, DOJO_VICTORY_BACK_BUTTON: _match("back")},
    )
    results = [bot._dojo_step("grass", []) for _ in range(3)]
    assert results == ["go", "go", "go"]
    assert bot.tap.call_count == 3
    assert all(c.args[0] is cont for c in bot.tap.call_args_list)


def test_play_dojo_reports_a_win_that_ended_the_dojo(bot: MagicMock) -> None:
    bot.wait_for_template.return_value = _match(DOJO_START_BUTTON)
    bot._dojo_step = MagicMock(return_value="again")
    assert bot._play_dojo("grass", []) is True
    bot._dojo_step = MagicMock(return_value="done")
    assert bot._play_dojo("grass", []) is False


def test_play_dojo_can_resume_with_the_kept_field(bot: MagicMock) -> None:
    bot._keep_field = True
    bot.wait_for_template.return_value = _match(DOJO_START_BUTTON)
    bot._dojo_step = MagicMock(return_value="done")
    bot._play_dojo("grass", [], resume=True)
    assert bot._keep_field is True


def test_win_of_stage_ten_claims_the_badge_and_enters_the_next_tier(
    bot: MagicMock,
) -> None:
    claim = _match(DOJO_CLAIM_BADGE_BUTTON)
    _victory_screen(bot, {DOJO_CLAIM_BADGE_BUTTON: claim})
    fights: list[DojoFight] = []
    assert bot._dojo_step("grass", fights) == "again"
    assert bot.tap.call_args.args[0] is claim
    assert len(fights) == 1
    assert fights[0].won is True


def test_claim_button_wins_over_the_back_button(bot: MagicMock) -> None:
    claim = _match(DOJO_CLAIM_BADGE_BUTTON)
    _victory_screen(
        bot,
        {DOJO_CLAIM_BADGE_BUTTON: claim, DOJO_VICTORY_BACK_BUTTON: _match("back")},
    )
    assert bot._dojo_step("grass", []) == "again"
    assert bot.tap.call_args.args[0] is claim
