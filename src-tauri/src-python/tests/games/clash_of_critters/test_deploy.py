"""Tests for the Clash of Critters tray scan and formation deployment."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters import deploy
from adb_auto_player.games.clash_of_critters.battle_layout import (
    ALL_FILTER_POINT,
    CLEAR_FIELD_POINT,
    ELEMENT_FILTER_POINTS,
    MAX_DEPLOYED,
    cell_center,
)
from adb_auto_player.games.clash_of_critters.deploy import DeployMixin
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
    StageId,
)
from adb_auto_player.models.geometry import Point

STAGE = StageId(15, 50)


class _DeployBot(DeployMixin):
    """Concrete DeployMixin (Game leaves `settings` abstract, `device` a property)."""

    device = None

    @property
    def settings(self):  # type: ignore[override]
        raise NotImplementedError


def _unit(evolution_id: str, row: int, col: int) -> FormationUnit:
    tatari_id, tier = evolution_id.rsplit("-", 1)
    return FormationUnit(row, col, tatari_id, evolution_id, int(tier), False)


@pytest.fixture
def bot() -> MagicMock:
    """DeployMixin instance with every device-facing method mocked."""
    game = object.__new__(_DeployBot)
    game.tap = MagicMock()
    game.device = MagicMock()
    game.get_screenshot = MagicMock()
    game._apply_vertical_offset = lambda point: point
    game._visible_cards = MagicMock(return_value=[])
    game._scroll_tray = MagicMock(return_value=False)
    game._scan_owned = MagicMock(return_value=set())
    game._select_element = MagicMock()
    game._wait_tray_stable = MagicMock()
    game._locate_card = MagicMock(return_value=Point(110, 1285))
    game._drag_card = MagicMock()
    game._read_deployed_count = MagicMock(return_value=0)
    return game


@pytest.fixture(autouse=True)
def no_sleep():
    """Never really sleep."""
    with patch.object(deploy, "sleep") as sleep:
        yield sleep


def test_clear_tapped_before_any_drag(bot: MagicMock) -> None:
    parent = MagicMock()
    parent.attach_mock(bot.tap, "tap")
    parent.attach_mock(bot._drag_card, "drag")
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._read_deployed_count.side_effect = [0, 1]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    bot._deploy_formation(formation)
    assert parent.mock_calls[0] == call.tap(CLEAR_FIELD_POINT, log=False)
    assert parent.mock_calls[1].args[1] == cell_center(1, 1)


def test_drags_each_owned_unit_to_its_cell(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2", "fire-3-2"}
    bot._locate_card.side_effect = [Point(110, 1285), Point(288, 1285)]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1), _unit("fire-3-2", 2, 3)))
    bot._read_deployed_count.side_effect = [0, 2]
    assert bot._deploy_formation(formation) == 2
    assert bot._drag_card.call_args_list == [
        call(Point(110, 1285), cell_center(1, 1)),
        call(Point(288, 1285), cell_center(2, 3)),
    ]


def test_unowned_unit_is_skipped(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    formation = Formation(STAGE, (_unit("fire-3-2", 1, 1), _unit("grass-4-2", 2, 2)))
    bot._read_deployed_count.side_effect = [0, 1]
    bot._deploy_formation(formation)
    bot._drag_card.assert_called_once_with(Point(110, 1285), cell_center(2, 2))


def test_card_not_found_in_tray_is_skipped(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._locate_card.return_value = None
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    assert bot._deploy_formation(formation) == 0
    bot._drag_card.assert_not_called()


def test_nothing_deployable_returns_zero_and_no_drag(bot: MagicMock) -> None:
    bot._scan_owned.return_value = set()
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    assert bot._deploy_formation(formation) == 0
    bot._drag_card.assert_not_called()


def test_at_most_fifteen_drags(bot: MagicMock) -> None:
    ids = [f"grass-{i}-2" for i in range(17)]
    bot._scan_owned.return_value = set(ids)
    units = tuple(_unit(evo, 1 + i % 5, 1 + i // 5) for i, evo in enumerate(ids))
    bot._read_deployed_count.side_effect = [0, MAX_DEPLOYED]
    bot._deploy_formation(Formation(STAGE, units))
    assert bot._drag_card.call_count == MAX_DEPLOYED


def test_count_falls_back_to_drags_when_unreadable(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._read_deployed_count.return_value = None
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    assert bot._deploy_formation(formation) == 1


def test_deploys_one_element_at_a_time(bot: MagicMock) -> None:
    parent = MagicMock()
    parent.attach_mock(bot._select_element, "select")
    parent.attach_mock(bot._drag_card, "drag")
    bot._scan_owned.return_value = {"grass-4-2", "fire-3-2", "grass-3-1"}
    formation = Formation(
        STAGE,
        (
            _unit("grass-4-2", 1, 1),
            _unit("fire-3-2", 2, 2),
            _unit("grass-3-1", 3, 3),
        ),
    )
    bot._read_deployed_count.side_effect = [0, 3]
    bot._deploy_formation(formation)
    assert parent.mock_calls == [
        call.select("grass"),
        call.drag(Point(110, 1285), cell_center(1, 1)),
        call.drag(Point(110, 1285), cell_center(3, 3)),
        call.select("fire"),
        call.drag(Point(110, 1285), cell_center(2, 2)),
        call.select(None),
    ]
    assert bot._scan_owned.call_count == 2


def test_filter_is_reset_even_when_nothing_is_deployed(bot: MagicMock) -> None:
    bot._scan_owned.return_value = set()
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    bot._deploy_formation(formation)
    assert bot._select_element.call_args_list == [call("grass"), call(None)]


def test_select_element_taps_the_filter_button(bot: MagicMock) -> None:
    DeployMixin._select_element(bot, "water")
    bot.tap.assert_called_once_with(ELEMENT_FILTER_POINTS["water"], log=False)


def test_select_element_waits_for_the_tray_to_settle(bot: MagicMock) -> None:
    DeployMixin._select_element(bot, "fire")
    bot._wait_tray_stable.assert_called_once_with()


def test_select_all_taps_the_all_button(bot: MagicMock) -> None:
    DeployMixin._select_element(bot, None)
    bot.tap.assert_called_once_with(ALL_FILTER_POINT, log=False)


# --- tray scanning --------------------------------------------------------------


@pytest.fixture
def tray_bot() -> MagicMock:
    """DeployMixin instance for the tray methods (real `_locate_card` etc.)."""
    game = object.__new__(_DeployBot)
    game._visible_cards = MagicMock(return_value=[])
    game._scroll_tray = MagicMock(return_value=False)
    return game


def test_locate_card_scrolls_until_found(tray_bot: MagicMock) -> None:
    target = Point(466, 1285)
    tray_bot._visible_cards.side_effect = [
        [(Point(110, 1285), None)],
        [(Point(110, 1285), "fire-3-2")],
        [(target, "grass-4-2")],
    ]
    tray_bot._scroll_tray.return_value = True
    assert tray_bot._locate_card("grass-4-2") == target
    assert tray_bot._scroll_tray.call_count == 2


def test_locate_card_stops_at_tray_end(tray_bot: MagicMock) -> None:
    tray_bot._visible_cards.return_value = [(Point(110, 1285), "fire-3-2")]
    tray_bot._scroll_tray.return_value = False
    assert tray_bot._locate_card("grass-4-2") is None


def test_scan_owned_collects_every_page_and_rewinds(tray_bot: MagicMock) -> None:
    pages = [
        [(Point(1, 1), "a-1-1"), (Point(2, 1), "b-1-1")],
        [(Point(1, 1), "b-1-1"), (Point(2, 1), None), (Point(3, 1), "c-1-1")],
    ]
    tray_bot._visible_cards.side_effect = pages
    # Backward to the start (already there), forward once, then the end,
    # then back to the start.
    tray_bot._scroll_tray.side_effect = [False, True, False, True, False]
    assert tray_bot._scan_owned() == {"a-1-1", "b-1-1", "c-1-1"}
    assert tray_bot._scroll_tray.call_args_list[-2:] == [call(False), call(False)]


# --- input and screen reading ---------------------------------------------------


def test_drag_card_swipes_between_points(bot: MagicMock) -> None:
    DeployMixin._drag_card(bot, Point(110, 1285), Point(300, 490))
    bot.device.swipe.assert_called_once_with(
        Point(110, 1285), Point(300, 490), duration=deploy._DRAG_SECONDS
    )


def test_scroll_tray_reports_movement(bot: MagicMock) -> None:
    before = np.zeros((1920, 1080, 3), np.uint8)
    after = np.full((1920, 1080, 3), 90, np.uint8)
    bot.get_screenshot.return_value = before
    bot._wait_tray_stable.return_value = after
    assert DeployMixin._scroll_tray(bot, forward=True) is True
    bot._wait_tray_stable.return_value = before.copy()
    assert DeployMixin._scroll_tray(bot, forward=True) is False


def test_scroll_tray_compares_the_settled_tray_not_a_moving_one(
    bot: MagicMock,
) -> None:
    bot.get_screenshot.return_value = np.zeros((1920, 1080, 3), np.uint8)
    bot._wait_tray_stable.return_value = np.zeros((1920, 1080, 3), np.uint8)
    DeployMixin._scroll_tray(bot, forward=True)
    bot._wait_tray_stable.assert_called_once_with()


# --- waiting for the tray to stop moving ------------------------------------------


def _frame(value: int) -> np.ndarray:
    return np.full((1920, 1080, 3), value, np.uint8)


def test_wait_tray_stable_returns_once_two_frames_match(bot: MagicMock) -> None:
    frames = [_frame(10), _frame(60), _frame(61), _frame(61), _frame(61)]
    bot.get_screenshot.side_effect = frames
    result = DeployMixin._wait_tray_stable(bot)
    # 10 -> 60 moving, 60 -> 61 still moving a little, 61 -> 61 stable.
    assert bot.get_screenshot.call_count == 4
    assert result is frames[3]


def test_wait_tray_stable_sleeps_between_frames(
    bot: MagicMock, no_sleep: MagicMock
) -> None:
    bot.get_screenshot.side_effect = [_frame(10), _frame(10)]
    DeployMixin._wait_tray_stable(bot)
    no_sleep.assert_called_once_with(deploy._STABLE_POLL_SECONDS)


def test_wait_tray_stable_gives_up_when_the_tray_never_stops(
    bot: MagicMock,
) -> None:
    bot.get_screenshot.side_effect = [_frame(10 + 40 * (i % 2)) for i in range(50)]
    DeployMixin._wait_tray_stable(bot)
    assert bot.get_screenshot.call_count == deploy._STABLE_MAX_POLLS + 1


@pytest.mark.parametrize(
    "text, expected",
    [("Đã triển khai: 12/15", 12), ("Đã triển khai: 0/15", 0), ("???", None)],
)
def test_read_deployed_count_parses(
    bot: MagicMock, text: str, expected: int | None
) -> None:
    bot.get_screenshot.return_value = np.zeros((1920, 1080, 3), np.uint8)
    with patch.object(deploy, "RapidOCRBackend") as backend:
        backend.return_value.extract_text.return_value = text
        assert DeployMixin._read_deployed_count(bot) == expected


def test_visible_cards_follow_the_scrolled_tray(bot: MagicMock) -> None:
    screenshot = cv2.imread(
        str(Path(__file__).parent / "data" / "prep_screen_scrolled.png")
    )
    bot.get_screenshot.return_value = screenshot
    recognizer = MagicMock()
    recognizer.recognize.return_value = "grass-4-2"
    bot._get_recognizer = MagicMock(return_value=recognizer)
    bot._recognition_cache = None
    cards = DeployMixin._visible_cards(bot)
    # 4 whole cards per row, 2 rows; slots follow the card positions, not a fixed grid.
    assert len(cards) == 8
    assert [point.x for point, _ in cards[:4]] == [250, 427, 605, 783]
    assert [point.y for point, _ in cards[::4]] == [1285, 1480]
    assert recognizer.recognize.call_args_list[0].args[0].shape == (190, 160, 3)
