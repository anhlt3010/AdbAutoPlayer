"""Tests for recognizing tray cards from a real preparation-screen capture."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters import card_recognition as cr_module
from adb_auto_player.games.clash_of_critters.battle_layout import (
    ELEMENT_ICON_BOX,
    card_box,
    tray_slots,
)
from adb_auto_player.games.clash_of_critters.card_recognition import (
    CardRecognizer,
    CardTemplateStore,
    classify_element,
    is_deployed,
)
from adb_auto_player.games.clash_of_critters.deployment_plan import (
    split_evolution_id,
)
from adb_auto_player.games.clash_of_critters.tatari_db import TatariDb

DATA_DIR = Path(__file__).parent / "data"
DB_ROOT = Path(cr_module.__file__).parent / "tatari_db"

pytestmark = pytest.mark.skipif(
    not DB_ROOT.exists(), reason="tatari_db data not present"
)

# Read from docs/superpowers/specs/assets/prep_screen_cleared.png (row-major).
ELEMENTS_IN_TRAY = [
    "rock", "rock", "water", "water", "lightning", "water",
    "lightning", "grass", "fire", "grass", "rock", "water",
]  # fmt: skip

# Cards checked by eye against the wiki sprites. The 6th and 12th cards are cut
# off by the right edge of the tray; whatever they are recognized as must still be
# of the right element (checked below).
EXPECTED_IDS = {
    0: "rock-5-1",
    1: "rock-4-1",
    2: "water-3-3",
    4: "lightning-4-2",
    6: "lightning-3-3",
    7: "grass-3-1",
    9: "grass-7-2",
    10: "rock-3-2",
}


@pytest.fixture(scope="module")
def screen() -> np.ndarray:
    image = cv2.imread(str(DATA_DIR / "prep_screen_cleared.png"))
    assert image is not None
    return image


def _card(screen: np.ndarray, index: int) -> np.ndarray:
    left, top, right, bottom = card_box(tray_slots()[index])
    return screen[top:bottom, left:right]


@pytest.fixture(scope="module")
def recognized(screen: np.ndarray, tmp_path_factory) -> list[str | None]:
    store = CardTemplateStore(tmp_path_factory.mktemp("templates"))
    recognizer = CardRecognizer(TatariDb.load(DB_ROOT), store)
    return [recognizer.recognize(_card(screen, i)) for i in range(12)]


def test_classify_element_of_visible_cards(screen: np.ndarray) -> None:
    left, top, right, bottom = ELEMENT_ICON_BOX
    found = [
        classify_element(_card(screen, i)[top:bottom, left:right]) for i in range(12)
    ]
    assert found == ELEMENTS_IN_TRAY


def test_recognize_known_cards(recognized: list[str | None]) -> None:
    for index, expected in EXPECTED_IDS.items():
        assert recognized[index] is not None, f"card {index} not recognized"
        base = recognized[index].removesuffix("g")
        assert base == expected, f"card {index}"


def test_recognized_ids_match_the_card_element(recognized: list[str | None]) -> None:
    db = TatariDb.load(DB_ROOT)
    for index, evolution_id in enumerate(recognized):
        if evolution_id is None:
            continue
        sprite = db.get(evolution_id)
        assert sprite is not None
        assert sprite.element == ELEMENTS_IN_TRAY[index]
        assert split_evolution_id(evolution_id)[0] == sprite.tatari_id


def test_blank_card_returns_none(tmp_path: Path) -> None:
    blank = np.full((190, 160, 3), (60, 170, 250), np.uint8)
    recognizer = CardRecognizer(TatariDb.load(DB_ROOT), CardTemplateStore(tmp_path))
    assert recognizer.recognize(blank) is None


class _Spy(CardRecognizer):
    """Image recognition replaced by a counter, to see when it is used."""

    result: str | None = "water-3-3"

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.calls: list[str | None] = []

    def _match(self, card_bgr, element):  # type: ignore[no-untyped-def]
        self.calls.append(element)
        return self.result


def _spy(tmp_path: Path) -> _Spy:
    return _Spy(TatariDb.load(DB_ROOT), CardTemplateStore(tmp_path))


def test_recognized_card_is_saved_as_a_template(
    screen: np.ndarray, tmp_path: Path
) -> None:
    assert _spy(tmp_path).recognize(_card(screen, 2)) == "water-3-3"
    assert (tmp_path / "water" / "water-3-3.png").is_file()


def test_stored_template_is_used_before_image_recognition(
    screen: np.ndarray, tmp_path: Path
) -> None:
    recognizer = _spy(tmp_path)
    assert recognizer.recognize(_card(screen, 2)) == "water-3-3"
    assert recognizer.recognize(_card(screen, 2)) == "water-3-3"
    assert recognizer.calls == ["water"]


def test_templates_are_reused_by_a_new_recognizer(
    screen: np.ndarray, tmp_path: Path
) -> None:
    _spy(tmp_path).recognize(_card(screen, 2))
    later = _spy(tmp_path)
    assert later.recognize(_card(screen, 2)) == "water-3-3"
    assert later.calls == []


def test_card_without_a_template_falls_back_to_image_recognition(
    screen: np.ndarray, tmp_path: Path
) -> None:
    recognizer = _spy(tmp_path)
    recognizer.recognize(_card(screen, 2))
    recognizer.result = "rock-3-2"
    assert recognizer.recognize(_card(screen, 10)) == "rock-3-2"
    assert recognizer.calls == ["water", "rock"]


def test_unrecognized_card_is_not_saved(screen: np.ndarray, tmp_path: Path) -> None:
    recognizer = _spy(tmp_path)
    recognizer.result = None
    assert recognizer.recognize(_card(screen, 2)) is None
    assert not any(tmp_path.rglob("*.png"))


def test_deployed_card_is_skipped_and_never_saved(tmp_path: Path) -> None:
    deployed = cv2.imread(str(DATA_DIR / "prep_screen_deployed.png"))
    recognizer = _spy(tmp_path)
    assert recognizer.recognize(_card(deployed, 0)) is None
    assert recognizer.calls == []
    assert not any(tmp_path.rglob("*.png"))


def test_normal_cards_are_not_mistaken_for_glitter(
    recognized: list[str | None],
) -> None:
    # Outline matching alone prefers the glitter twin of the 2nd card; colour decides.
    assert recognized[0] == "rock-5-1"
    assert recognized[1] == "rock-4-1"
    assert recognized[4] == "lightning-4-2"
    # The red dragon; its glitter twin is pink.
    assert recognized[8] == "fire-4-3"


# --- cards that were missed on a real tray (found by scanning every element) ------


def _fresh_recognizer(tmp_path: Path) -> CardRecognizer:
    return CardRecognizer(TatariDb.load(DB_ROOT), CardTemplateStore(tmp_path))


def _data_card(name: str) -> np.ndarray:
    card = cv2.imread(str(DATA_DIR / name))
    assert card is not None
    return card


@pytest.mark.parametrize(
    "name", ["card_grass_a.png", "card_grass_b.png", "card_grass_c.png"]
)
def test_green_creatures_are_not_mistaken_for_a_deployed_card(name: str) -> None:
    assert not is_deployed(_data_card(name))


def test_card_with_a_small_lead_in_outline_is_found_by_colour(
    tmp_path: Path,
) -> None:
    result = _fresh_recognizer(tmp_path).recognize(_data_card("card_lightning_8_2.png"))
    assert result == "lightning-8-2"


def test_other_evolution_of_the_same_tatari_is_found(tmp_path: Path) -> None:
    # The player owns another evolution than the formation asks for (water-7-2);
    # it must still be recognized so the planner can substitute it.
    result = _fresh_recognizer(tmp_path).recognize(_data_card("card_water_7.png"))
    assert result is not None
    assert split_evolution_id(result)[0] == "water-7"


@pytest.mark.parametrize(
    "name, tatari",
    [
        ("card_grass_a.png", "grass-13"),
        ("card_grass_b.png", "grass-5"),
        ("card_grass_c.png", "grass-9"),
    ],
)
def test_green_creature_cards_are_recognized(
    tmp_path: Path, name: str, tatari: str
) -> None:
    result = _fresh_recognizer(tmp_path).recognize(_data_card(name))
    assert result is not None
    assert split_evolution_id(result)[0] == tatari


def test_sprite_without_alpha_gets_its_background_removed(tmp_path: Path) -> None:
    # The glitter sprites of the 13th tatari family are plain rectangles in the db.
    recognizer = _fresh_recognizer(tmp_path)
    sprite = TatariDb.load(DB_ROOT).get("water-13-2g")
    assert sprite is not None
    image = recognizer._load(sprite)
    height, width = image.shape[:2]
    assert image[0, 0, 3] == 0
    assert image[height // 2, width // 2, 3] == 255


def test_glitter_card_of_a_sprite_without_alpha_is_recognized(tmp_path: Path) -> None:
    result = _fresh_recognizer(tmp_path).recognize(_data_card("card_water_13.png"))
    assert result is not None
    assert split_evolution_id(result)[0] == "water-13"
