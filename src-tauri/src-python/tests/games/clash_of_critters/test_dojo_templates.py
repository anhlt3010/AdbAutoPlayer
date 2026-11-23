"""Tests for the Võ Đường templates, matched against the saved captures."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters import main

ASSETS_DIR = Path(__file__).parents[5] / "docs" / "superpowers" / "specs" / "assets"
TEMPLATE_DIR = Path(main.__file__).parent / "templates"
MIN_ON_SOURCE = 0.95
MAX_ON_OTHERS = 0.7
MIN_EXISTING_ON_DOJO = 0.9

# template -> the capture it was cropped from
SOURCES = {
    "dojo_start_button.png": "dojo_stage_list.png",
    "dojo_my_badges_button.png": "dojo_tabs_grass_yellow.png",
    "dojo_retry_button.png": "dojo_defeat.png",
    "dojo_continue_button.png": "dojo_victory.png",
    "dojo_defeat_back_button.png": "dojo_defeat.png",
    "dojo_new_trait_title.png": "dojo_new_trait_popup.png",
    "dojo_victory_back_button.png": "dojo_victory_last_stage.png",
    "dojo_claim_badge_button.png": "dojo_victory_claim_badge.png",
    "dojo_receive_text.png": "dojo_receive_prompt.png",
    "dojo_great_button.png": "dojo_badge_received.png",
}
CAPTURES = (
    "dojo_stage_list.png",
    "dojo_defeat.png",
    "dojo_victory.png",
    "dojo_new_trait_popup.png",
    "dojo_prep_cleared.png",
    "dojo_tabs_grass_yellow.png",
    "dojo_victory_last_stage.png",
    "dojo_victory_claim_badge.png",
    "dojo_receive_prompt.png",
    "dojo_badge_received.png",
)


def _best(image_name: str, template_name: str) -> float:
    image = cv2.imread(str(ASSETS_DIR / image_name))
    template = cv2.imread(str(TEMPLATE_DIR / template_name))
    assert image is not None, image_name
    assert template is not None, template_name
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    return float(np.max(result))


@pytest.mark.parametrize("template", sorted(SOURCES))
def test_template_matches_its_capture(template: str) -> None:
    assert _best(SOURCES[template], template) >= MIN_ON_SOURCE


@pytest.mark.parametrize("template", sorted(SOURCES))
def test_template_does_not_match_the_other_captures(template: str) -> None:
    for capture in CAPTURES:
        if capture == SOURCES[template]:
            continue
        if template == "dojo_my_badges_button.png" and capture.startswith("dojo_tabs"):
            continue  # every Võ Đường screen has this button
        if template == "dojo_victory_back_button.png" and capture == "dojo_victory.png":
            continue  # the same white "Trở Về" sits in the two-button layout
        if (
            template == "dojo_receive_text.png"
            and capture == "dojo_victory_claim_badge.png"
        ):
            continue  # "Nhận Huy Hiệu" starts with the same word; tapping it is right
        assert _best(capture, template) < MAX_ON_OTHERS, (template, capture)


def test_screen_marker_matches_another_element() -> None:
    assert _best("dojo_tabs_rock_grey.png", "dojo_my_badges_button.png") >= 0.9


@pytest.mark.parametrize(
    "template, capture",
    [
        ("victory_title.png", "dojo_victory.png"),
        ("defeat_title.png", "dojo_defeat.png"),
        ("quick_deploy_button.png", "dojo_prep_cleared.png"),
        ("fight_button.png", "dojo_prep_cleared.png"),
    ],
)
def test_existing_templates_match_the_dojo_screens(template: str, capture: str) -> None:
    assert _best(capture, template) >= MIN_EXISTING_ON_DOJO


def test_victory_back_button_matches_the_two_button_layout() -> None:
    assert _best("dojo_victory.png", "dojo_victory_back_button.png") >= 0.9
