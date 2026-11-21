"""Tests for recognizing tray cards from a real preparation-screen capture."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters import card_recognition as cr_module
from adb_auto_player.games.clash_of_critters.battle_layout import card_box, tray_slots
from adb_auto_player.games.clash_of_critters.card_recognition import (
    CardRecognizer,
    RecognitionCache,
    card_art_key,
    classify_element,
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
# off by the right edge of the tray and must not be guessed.
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
CUT_OFF_CARDS = (5, 11)


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
    cache = RecognitionCache(tmp_path_factory.mktemp("cache") / "cards.json")
    recognizer = CardRecognizer(TatariDb.load(DB_ROOT), cache)
    return [recognizer.recognize(_card(screen, i)) for i in range(12)]


def test_classify_element_of_visible_cards(screen: np.ndarray) -> None:
    from adb_auto_player.games.clash_of_critters.battle_layout import (
        ELEMENT_ICON_BOX,
    )

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


def test_cut_off_cards_are_not_guessed(recognized: list[str | None]) -> None:
    for index in CUT_OFF_CARDS:
        assert recognized[index] is None


def test_recognized_ids_match_the_card_element(recognized: list[str | None]) -> None:
    db = TatariDb.load(DB_ROOT)
    for index, evolution_id in enumerate(recognized):
        if evolution_id is None:
            continue
        sprite = db.get(evolution_id)
        assert sprite is not None
        assert sprite.element == ELEMENTS_IN_TRAY[index]
        assert split_evolution_id(evolution_id)[0] == sprite.tatari_id


def test_blank_card_returns_none() -> None:
    blank = np.full((190, 160, 3), (60, 170, 250), np.uint8)
    recognizer = CardRecognizer(
        TatariDb.load(DB_ROOT), RecognitionCache(Path("unused.json"))
    )
    assert recognizer.recognize(blank) is None


def test_cache_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cards.json"
    cache = RecognitionCache(path)
    cache.put("abc", "water-3-3")
    cache.save()
    assert RecognitionCache(path).get("abc") == "water-3-3"
    assert RecognitionCache(path).get("missing") is None


def test_corrupt_cache_loads_empty(tmp_path: Path) -> None:
    path = tmp_path / "cards.json"
    path.write_text("{not json", encoding="utf-8")
    assert RecognitionCache(path).get("abc") is None


def test_cache_hit_skips_matching(screen: np.ndarray, tmp_path: Path) -> None:
    calls: list[str] = []

    class Spy(CardRecognizer):
        def _match(self, card_bgr, element):  # type: ignore[no-untyped-def]
            calls.append(element)
            return "water-3-3"

    cache = RecognitionCache(tmp_path / "cards.json")
    recognizer = Spy(TatariDb.load(DB_ROOT), cache)
    card = _card(screen, 2)
    assert recognizer.recognize(card) == "water-3-3"
    assert recognizer.recognize(card) == "water-3-3"
    assert calls == ["water"]


def test_art_key_is_stable_and_differs_between_cards(screen: np.ndarray) -> None:
    assert card_art_key(_card(screen, 2)) == card_art_key(_card(screen, 2).copy())
    assert card_art_key(_card(screen, 2)) != card_art_key(_card(screen, 10))


def test_normal_cards_are_not_mistaken_for_glitter(
    recognized: list[str | None],
) -> None:
    # Outline matching alone prefers the glitter twin of the 2nd card; colour decides.
    assert recognized[0] == "rock-5-1"
    assert recognized[1] == "rock-4-1"
    assert recognized[4] == "lightning-4-2"
