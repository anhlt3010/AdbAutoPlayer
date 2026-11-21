"""Every battle template matches its own screen and no other (real captures)."""

from pathlib import Path

import cv2
import numpy as np
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
)

TEMPLATE_DIR = Path(auto_battle.__file__).parent / "templates"
DATA_DIR = Path(__file__).parent / "data"
SCREENS = {
    "camp": "camp_screen.png",
    "map": "stage_map_screen.png",
    "prep": "prep_screen_cleared.png",
    "prep_after_loss": "prep_screen_report.png",
    "defeat": "defeat_screen.png",
}
SHOWN_ON = [
    (HUB_BATTLE_BUTTON, {"camp"}),
    (STAGE_MAP_MARKER, {"map"}),
    (QUICK_DEPLOY_BUTTON, {"prep", "prep_after_loss"}),
    (FIGHT_BUTTON, {"prep", "prep_after_loss"}),
    # Only shown once the stage was lost: it must not match the first visit.
    (PREP_REPORT_ICON, {"prep_after_loss"}),
    (DEFEAT_TITLE, {"defeat"}),
    (RETRY_BUTTON, {"defeat"}),
]
MATCH = 0.9
NO_MATCH = 0.6


def _score(template: str, screen: str) -> float:
    tpl = cv2.imread(str(TEMPLATE_DIR / template))
    img = cv2.imread(str(DATA_DIR / screen))
    assert tpl is not None, template
    assert img is not None, screen
    scores = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    return float(np.nan_to_num(scores, nan=-1.0).max())


@pytest.mark.parametrize("template, shown_on", SHOWN_ON)
def test_template_matches_only_its_own_screens(
    template: str, shown_on: set[str]
) -> None:
    for name, file in SCREENS.items():
        score = _score(template, file)
        if name in shown_on:
            assert score >= MATCH, f"{template} on {name}: {score:.2f}"
        else:
            assert score < NO_MATCH, f"{template} on {name}: {score:.2f}"
