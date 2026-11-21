"""Tests for the Clash of Critters tray scan and formation deployment."""

import logging
from pathlib import Path
from types import SimpleNamespace
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
from adb_auto_player.games.clash_of_critters.deploy import DeployMixin, DeployResult
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
    StageId,
)
from adb_auto_player.models.geometry import Point

STAGE = StageId(15, 50)


def xy(point: Point) -> tuple[int, int]:
    """Coordinates of a point.

    ``Point`` has no dataclass fields, so any two points compare equal; tests
    must compare coordinates instead.
    """
    return point.x, point.y


def drags(mock: MagicMock) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """(start, end) of every call of a drag-like mock."""
    return [(xy(c.args[0]), xy(c.args[1])) for c in mock.call_args_list]


class _DeployBot(DeployMixin):
    """Concrete DeployMixin (Game leaves `settings` abstract, `device` a property)."""

    device = None
    settings = None  # replaced per instance


def _unit(evolution_id: str, row: int, col: int) -> FormationUnit:
    tatari_id, tier = evolution_id.rsplit("-", 1)
    return FormationUnit(row, col, tatari_id, evolution_id, int(tier), False)


@pytest.fixture
def bot() -> MagicMock:
    """DeployMixin instance with every device-facing method mocked.

    Dragging a card puts one more tatari on the (simulated) field; the counter
    reads that number back.
    """
    game = object.__new__(_DeployBot)
    field = {"count": 0}

    def drag(card: Point, cell: Point) -> None:
        field["count"] += 1

    game.settings = SimpleNamespace(
        auto_battle=SimpleNamespace(tray_settle_poll_seconds=0.5)
    )
    game.tap = MagicMock()
    game.device = MagicMock()
    game.get_screenshot = MagicMock()
    game._apply_vertical_offset = lambda point: point
    game._visible_cards = MagicMock(return_value=[])
    game._scroll_tray = MagicMock(return_value=False)
    game._scan_owned = MagicMock(return_value=set())
    game._select_element = MagicMock()
    game._get_recognizer = MagicMock()
    game._wait_tray_stable = MagicMock()
    game._drag_card = MagicMock(side_effect=drag)
    game._field_move = MagicMock(return_value=True)
    game._read_deployed_count = MagicMock(side_effect=lambda: field["count"])
    return game


@pytest.fixture(autouse=True)
def no_sleep():
    """Never really sleep."""
    with patch.object(deploy, "sleep") as sleep:
        yield sleep


CARD_A = Point(110, 1285)
CARD_B = Point(288, 1285)
CARD_C = Point(466, 1285)


def test_clear_tapped_before_any_drag(bot: MagicMock) -> None:
    parent = MagicMock()
    parent.attach_mock(bot.tap, "tap")
    parent.attach_mock(bot._drag_card, "drag")
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),)))
    tap, drag = parent.mock_calls[0], parent.mock_calls[1]
    assert (tap[0], xy(tap.args[0]), tap.kwargs) == (
        "tap",
        xy(CLEAR_FIELD_POINT),
        {"log": False},
    )
    assert (drag[0], xy(drag.args[0]), xy(drag.args[1])) == (
        "drag",
        (110, 1285),
        (300, 490),
    )


def test_drags_each_owned_unit_to_its_cell(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2", "fire-3-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2"), (CARD_B, "fire-3-2")]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1), _unit("fire-3-2", 2, 3)))
    assert bot._deploy_formation(formation).count == 2
    assert drags(bot._drag_card) == [
        ((110, 1285), (300, 490)),
        ((288, 1285), (540, 610)),
    ]


def test_unowned_unit_is_skipped(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    formation = Formation(STAGE, (_unit("fire-3-2", 1, 1), _unit("grass-4-2", 2, 2)))
    bot._deploy_formation(formation)
    assert drags(bot._drag_card) == [((110, 1285), (420, 610))]


def test_card_that_cannot_be_found_is_skipped(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "fire-3-2")]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    assert bot._deploy_formation(formation).count == 0
    bot._drag_card.assert_not_called()


def test_nothing_deployable_returns_zero_and_no_drag(bot: MagicMock) -> None:
    bot._scan_owned.return_value = set()
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    assert bot._deploy_formation(formation).count == 0
    bot._drag_card.assert_not_called()


def test_walks_back_through_the_tray_placing_cards(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2", "grass-3-1"}
    bot._visible_cards.side_effect = [
        [(CARD_A, "grass-4-2")],  # the end of the tray, where the scan stopped
        [(CARD_B, "grass-3-1")],  # one page back
    ]
    bot._scroll_tray.side_effect = [True, False]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1), _unit("grass-3-1", 2, 2)))
    assert bot._deploy_formation(formation).count == 2
    assert bot._scroll_tray.call_args_list == [call(False)]
    assert [start for start, _ in drags(bot._drag_card)] == [(110, 1285), (288, 1285)]


def test_stops_scrolling_once_every_card_is_placed(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),)))
    bot._scroll_tray.assert_not_called()


def test_at_most_fifteen_drags(bot: MagicMock) -> None:
    ids = [f"grass-{i}-2" for i in range(17)]
    bot._scan_owned.return_value = set(ids)
    units = tuple(_unit(evo, 1 + i % 5, 1 + i // 5) for i, evo in enumerate(ids))
    bot._visible_cards.return_value = [
        (Point(cell_center(u.row, u.col).x, 1285), u.evolution_id) for u in units
    ]
    bot._deploy_formation(Formation(STAGE, units))
    assert bot._drag_card.call_count == MAX_DEPLOYED


def test_deploys_one_element_at_a_time(bot: MagicMock) -> None:
    parent = MagicMock()
    parent.attach_mock(bot._select_element, "select")
    parent.attach_mock(bot._drag_card, "drag")
    bot._scan_owned.return_value = {"grass-4-2", "fire-3-2", "grass-3-1"}
    bot._visible_cards.return_value = [
        (CARD_A, "grass-4-2"),
        (CARD_B, "fire-3-2"),
        (CARD_C, "grass-3-1"),
    ]
    formation = Formation(
        STAGE,
        (_unit("grass-4-2", 1, 1), _unit("fire-3-2", 2, 2), _unit("grass-3-1", 3, 3)),
    )
    bot._deploy_formation(formation)
    sequence = [
        ("select", c.args[0])
        if c[0] == "select"
        else ("drag", xy(c.args[0]), xy(c.args[1]))
        for c in parent.mock_calls
    ]
    assert sequence == [
        ("select", "grass"),
        ("drag", (110, 1285), (300, 490)),
        ("drag", (466, 1285), (540, 730)),
        ("select", "fire"),
        ("drag", (288, 1285), (420, 610)),
        ("select", None),
    ]
    assert bot._scan_owned.call_count == 2


def test_filter_is_reset_even_when_nothing_is_deployed(bot: MagicMock) -> None:
    bot._scan_owned.return_value = set()
    bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),)))
    assert bot._select_element.call_args_list == [call("grass"), call(None)]


def test_unreadable_tatari_data_is_found_before_the_field_is_cleared(
    bot: MagicMock,
) -> None:
    bot._get_recognizer.side_effect = FileNotFoundError("tatari_db.json")
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1),))
    assert bot._deploy_formation(formation).count == 0
    bot.tap.assert_not_called()
    bot._drag_card.assert_not_called()


# --- dragging across a long way ----------------------------------------------------


def test_shallow_drag_is_done_in_two_legs(bot: MagicMock) -> None:
    card = Point(109, 1285)
    bot._scan_owned.return_value = {"water-3-3"}
    bot._visible_cards.return_value = [(card, "water-3-3")]
    formation = Formation(STAGE, (_unit("water-3-3", 5, 4),))
    assert bot._deploy_formation(formation).count == 1
    assert drags(bot._drag_card) == [((109, 1285), (420, 610))]
    assert drags(bot._field_move) == [((420, 610), (660, 970))]


def test_a_failed_field_move_is_reported(bot: MagicMock) -> None:
    bot._field_move.return_value = False
    bot._scan_owned.return_value = {"water-3-3"}
    bot._visible_cards.return_value = [(Point(109, 1285), "water-3-3")]
    formation = Formation(STAGE, (_unit("water-3-3", 5, 4),))
    bot._deploy_formation(formation)
    # The unit stays on the intermediate cell, which counts as occupied for the
    # next unit but not as a placement of this one.
    assert bot._field_move.call_count == 1


def test_cells_taken_by_earlier_units_are_avoided(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2", "grass-3-1"}
    first = Point(cell_center(2, 2).x, 1285)
    shallow = Point(109, 1285)
    bot._visible_cards.return_value = [(first, "grass-4-2"), (shallow, "grass-3-1")]
    formation = Formation(STAGE, (_unit("grass-4-2", 2, 2), _unit("grass-3-1", 5, 4)))
    bot._deploy_formation(formation)
    # (2, 2) is taken, so the second unit goes through another cell.
    assert drags(bot._field_move) == [((420, 490), (660, 970))]


def test_field_move_checks_that_the_target_cell_changed(bot: MagicMock) -> None:
    before = np.zeros((1920, 1080, 3), np.uint8)
    after = before.copy()
    target = cell_center(5, 4)
    after[target.y - 40 : target.y + 40, target.x - 40 : target.x + 40] = 200
    bot.get_screenshot.side_effect = [before, after]
    assert DeployMixin._field_move(bot, cell_center(2, 2), target) is True
    assert drags(bot._drag_card) == [((420, 610), (660, 970))]


def test_field_move_is_repeated_once_when_nothing_changed(bot: MagicMock) -> None:
    still = np.zeros((1920, 1080, 3), np.uint8)
    bot.get_screenshot.return_value = still
    assert DeployMixin._field_move(bot, cell_center(2, 2), cell_center(5, 4)) is False
    assert bot._drag_card.call_count == 2


def test_card_is_found_again_before_repeating_a_drag(bot: MagicMock) -> None:
    # The first drag did nothing (the tray may have moved); the card is looked up
    # again instead of reusing the old position.
    field = {"count": 0, "attempts": 0}

    def drag(card: Point, cell: Point) -> None:
        field["attempts"] += 1
        if field["attempts"] >= 2:
            field["count"] += 1

    bot._drag_card.side_effect = drag
    bot._read_deployed_count.side_effect = lambda: field["count"]
    bot._scan_owned.return_value = {"grass-4-2"}
    old = Point(cell_center(1, 1).x, 1285)
    moved = Point(cell_center(1, 1).x + 3, 1285)
    bot._visible_cards.side_effect = [[(old, "grass-4-2")], [(moved, "grass-4-2")]]
    bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),)))
    assert drags(bot._drag_card) == [
        ((300, 1285), (300, 490)),
        ((303, 1285), (300, 490)),
    ]


# --- checking that a drag worked ------------------------------------------------------


def _flaky_drags(bot: MagicMock, working_from_attempt: int) -> None:
    """Make drags put a tatari on the field only from the given attempt on."""
    field = {"count": 0, "attempts": 0}

    def drag(card: Point, cell: Point) -> None:
        field["attempts"] += 1
        if field["attempts"] >= working_from_attempt:
            field["count"] += 1

    bot._drag_card.side_effect = drag
    bot._read_deployed_count.side_effect = lambda: field["count"]


def test_a_drag_that_did_not_register_is_repeated_once(bot: MagicMock) -> None:
    _flaky_drags(bot, working_from_attempt=2)
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    assert bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),))).count == 1
    assert bot._drag_card.call_count == 2


def test_a_drag_is_not_repeated_when_it_worked(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),)))
    assert bot._drag_card.call_count == 1


def test_gives_up_after_one_repeat(bot: MagicMock) -> None:
    _flaky_drags(bot, working_from_attempt=99)
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    result = bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),)))
    assert result.count == 0
    # Two drags in the first pass, then two more in each of the fill rounds.
    assert bot._drag_card.call_count == 2 * (1 + deploy._FILL_ATTEMPTS)


def test_unreadable_counter_means_no_checking(bot: MagicMock) -> None:
    bot._read_deployed_count.side_effect = None
    bot._read_deployed_count.return_value = None
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    assert bot._deploy_formation(Formation(STAGE, (_unit("grass-4-2", 1, 1),))).count == 1
    assert bot._drag_card.call_count == 1


def test_select_element_taps_the_filter_button(bot: MagicMock) -> None:
    DeployMixin._select_element(bot, "water")
    bot.tap.assert_called_once()
    assert xy(bot.tap.call_args.args[0]) == xy(ELEMENT_FILTER_POINTS["water"])
    assert xy(ELEMENT_FILTER_POINTS["water"]) == (240, 1665)
    assert bot.tap.call_args.kwargs == {"log": False}


def test_select_element_waits_for_the_tray_to_settle(bot: MagicMock) -> None:
    DeployMixin._select_element(bot, "fire")
    bot._wait_tray_stable.assert_called_once_with()


def test_select_all_taps_the_all_button(bot: MagicMock) -> None:
    DeployMixin._select_element(bot, None)
    bot.tap.assert_called_once()
    assert xy(bot.tap.call_args.args[0]) == xy(ALL_FILTER_POINT) == (90, 1665)
    assert bot.tap.call_args.kwargs == {"log": False}


# --- tray scanning --------------------------------------------------------------


@pytest.fixture
def tray_bot() -> MagicMock:
    """DeployMixin instance for the tray methods (real `_scan_owned`)."""
    game = object.__new__(_DeployBot)
    game._visible_cards = MagicMock(return_value=[])
    game._scroll_tray = MagicMock(return_value=False)
    return game


def test_scan_owned_collects_every_page_and_stays_at_the_end(
    tray_bot: MagicMock,
) -> None:
    pages = [
        [(Point(1, 1), "a-1-1"), (Point(2, 1), "b-1-1")],
        [(Point(1, 1), "b-1-1"), (Point(2, 1), None), (Point(3, 1), "c-1-1")],
    ]
    tray_bot._visible_cards.side_effect = pages
    # Back to the start (already there), forward once, then the end is reached.
    tray_bot._scroll_tray.side_effect = [False, True, False]
    assert tray_bot._scan_owned() == {"a-1-1", "b-1-1", "c-1-1"}
    assert tray_bot._scroll_tray.call_args_list == [call(False), call(True), call(True)]


# --- input and screen reading ---------------------------------------------------


def test_drag_card_swipes_between_points(bot: MagicMock) -> None:
    DeployMixin._drag_card(bot, Point(110, 1285), Point(300, 490))
    bot.device.swipe.assert_called_once()
    swipe = bot.device.swipe.call_args
    assert (xy(swipe.args[0]), xy(swipe.args[1])) == ((110, 1285), (300, 490))
    assert swipe.kwargs == {"duration": deploy._DRAG_SECONDS}


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
    bot.settings.auto_battle.tray_settle_poll_seconds = 0.2
    bot.get_screenshot.side_effect = [_frame(10), _frame(10)]
    DeployMixin._wait_tray_stable(bot)
    no_sleep.assert_called_once_with(0.2)


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
    cards = DeployMixin._visible_cards(bot)
    # 4 whole cards per row, 2 rows; slots follow the card positions, not a fixed grid.
    assert len(cards) == 8
    assert [point.x for point, _ in cards[:4]] == [250, 427, 605, 783]
    assert [point.y for point, _ in cards[::4]] == [1285, 1480]
    assert recognizer.recognize.call_args_list[0].args[0].shape == (190, 160, 3)


# --- filling what is missing ---------------------------------------------------------


def _one_unit() -> Formation:
    return Formation(STAGE, (_unit("grass-4-2", 1, 1),))


def test_complete_formation_reports_complete(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2", "fire-3-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2"), (CARD_B, "fire-3-2")]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1), _unit("fire-3-2", 2, 3)))
    result = bot._deploy_formation(formation)
    assert result == DeployResult(2, 2)
    assert result.complete


def test_missing_unit_is_filled_in_a_later_round(bot: MagicMock) -> None:
    _flaky_drags(bot, working_from_attempt=3)  # the first pass (2 drags) fails
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    result = bot._deploy_formation(_one_unit())
    assert result == DeployResult(1, 1)
    clears = [c for c in bot.tap.call_args_list if xy(c.args[0]) == xy(CLEAR_FIELD_POINT)]
    assert len(clears) == 1  # the field is never cleared again to fill it


def test_gives_up_after_the_fill_rounds(bot: MagicMock) -> None:
    _flaky_drags(bot, working_from_attempt=999)
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    result = bot._deploy_formation(_one_unit())
    assert result == DeployResult(0, 1)
    assert not result.complete
    assert bot._scan_owned.call_count == 1 + deploy._FILL_ATTEMPTS


def test_unowned_units_are_not_needed(bot: MagicMock) -> None:
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1), _unit("fire-3-2", 2, 2)))
    result = bot._deploy_formation(formation)
    assert result == DeployResult(1, 1)
    assert bot._scan_owned.call_count == 2  # one per element, no fill round


def test_unreadable_counter_does_not_fill_forever(bot: MagicMock) -> None:
    bot._read_deployed_count.side_effect = None
    bot._read_deployed_count.return_value = None
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = []  # the card is never found
    result = bot._deploy_formation(_one_unit())
    assert result == DeployResult(0, 1)
    assert bot._scan_owned.call_count == 1 + deploy._FILL_ATTEMPTS


def test_nothing_owned_means_nothing_needed_and_no_fill(bot: MagicMock) -> None:
    bot._scan_owned.return_value = set()
    assert bot._deploy_formation(_one_unit()) == DeployResult(0, 0)
    assert bot._scan_owned.call_count == 1


def test_more_units_than_needed_is_complete() -> None:
    assert DeployResult(16, 15).complete


def test_progress_is_logged_per_element(
    bot: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    bot._scan_owned.return_value = {"grass-4-2"}
    bot._visible_cards.return_value = [(CARD_A, "grass-4-2")]
    formation = Formation(STAGE, (_unit("grass-4-2", 1, 1), _unit("grass-3-1", 2, 2)))
    bot._deploy_formation(formation)
    text = " | ".join(record.getMessage() for record in caplog.records)
    assert "Hệ grass: nhận diện 1 tatari trong tray" in text
    assert "thiếu grass-3-1" in text
    assert "Hệ grass: đã xếp 1/1" in text
    assert "Đã xếp 1/1 quân" in text
