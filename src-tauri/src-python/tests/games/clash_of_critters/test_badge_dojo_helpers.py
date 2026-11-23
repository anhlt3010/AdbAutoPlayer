"""Tests for the pure helpers of the Võ Đường Huy Hiệu command."""

from pathlib import Path

import cv2
import pytest
from adb_auto_player.games.clash_of_critters.badge_dojo import (
    DOJO_ELEMENTS,
    DOJO_TAB_POINTS,
    DojoFight,
    challenge_button_is_yellow,
    format_dojo_summary,
    master_dialog_shown,
    more_group_reveal_shown,
)

ASSETS_DIR = Path(__file__).parents[5] / "docs" / "superpowers" / "specs" / "assets"


def _capture(name: str):
    image = cv2.imread(str(ASSETS_DIR / name))
    assert image is not None
    return image


def test_yellow_button_on_grass_capture() -> None:
    assert challenge_button_is_yellow(_capture("dojo_tabs_grass_yellow.png"))


def test_grey_button_on_rock_capture() -> None:
    assert not challenge_button_is_yellow(_capture("dojo_tabs_rock_grey.png"))


def test_tab_points_cover_five_elements_in_order() -> None:
    assert tuple(DOJO_TAB_POINTS) == DOJO_ELEMENTS
    xs = [point.x for point in DOJO_TAB_POINTS.values()]
    assert xs == sorted(set(xs))
    assert {point.y for point in DOJO_TAB_POINTS.values()} == {1720}


def test_summary_lists_each_fight_and_totals() -> None:
    fights = [
        DojoFight("grass", "4-2", 1, 1, False),
        DojoFight("grass", "4-2", 1, 2, True),
        DojoFight("grass", "4-3", 1, 1, True),
    ]
    lines = format_dojo_summary(fights, ["water", "fire"])
    assert "Thảo 4-2 | đội hình 1 | lần 1 | Thua" in lines
    assert "Thảo 4-2 | đội hình 1 | lần 2 | Thắng" in lines
    assert "Thảo 4-3 | đội hình 1 | lần 1 | Thắng" in lines
    assert "Thảo: 2 thắng, 1 thua" in lines
    assert "Bỏ qua (nút Thử Thách xám): Thủy, Hỏa" in lines


def test_summary_without_fights() -> None:
    lines = format_dojo_summary([], list(DOJO_ELEMENTS))
    assert lines
    assert "Bỏ qua (nút Thử Thách xám): Thủy, Hỏa, Thảo, Thạch, Lôi" in lines
    assert not any("thắng" in line for line in lines)


@pytest.mark.parametrize("skipped", [[], ["rock"]])
def test_summary_always_has_a_header(skipped: list[str]) -> None:
    assert format_dojo_summary([], skipped)[0].startswith("Tổng kết")


def test_summary_names_a_fight_with_the_kept_field() -> None:
    lines = format_dojo_summary([DojoFight("grass", "4-3", 0, 1, True)], [])
    assert "Thảo 4-3 | giữ nguyên đội hình | lần 1 | Thắng" in lines


REVEAL_SCREENS = ("dojo_more_group_screen.png", "dojo_more_group_screen_2.png")
OTHER_SCREENS = (
    "dojo_defeat.png",
    "dojo_victory.png",
    "dojo_prep_cleared.png",
    "dojo_next_prep.png",
    "dojo_stage_list.png",
    "dojo_tabs_grass_yellow.png",
    "dojo_tabs_rock_grey.png",
    "dojo_new_trait_popup.png",
    "camp_screen.png",
    "defeat_screen.png",
    "victory_screen.png",
)


@pytest.mark.parametrize("name", REVEAL_SCREENS)
def test_reveal_button_is_seen_at_every_step_of_the_reveal(name: str) -> None:
    # The button pulses (its text is 430-450 px wide), so it is found by colour.
    assert more_group_reveal_shown(_capture(name))


@pytest.mark.parametrize("name", OTHER_SCREENS)
def test_reveal_button_is_not_seen_on_other_screens(name: str) -> None:
    assert not more_group_reveal_shown(_capture(name))


DIALOG_OTHER_SCREENS = (
    *OTHER_SCREENS,
    "dojo_more_group_screen.png",
    "dojo_next_prep.png",
    "dojo_prep_scrolled.png",
    "dojo_victory_last_stage.png",
    "dojo_victory_claim_badge.png",
)


def test_master_dialog_is_seen() -> None:
    assert master_dialog_shown(_capture("dojo_master_dialog.png"))


@pytest.mark.parametrize("name", DIALOG_OTHER_SCREENS)
def test_master_dialog_is_not_seen_on_other_screens(name: str) -> None:
    assert not master_dialog_shown(_capture(name))
