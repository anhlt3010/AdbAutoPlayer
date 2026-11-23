"""Tests for the player's own card templates (cut from real tray cards)."""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters.battle_layout import card_box, tray_slots
from adb_auto_player.games.clash_of_critters.card_recognition import (
    CardTemplateStore,
    is_deployed,
)

DATA_DIR = Path(__file__).parent / "data"
SHIFT = np.float32([[1, 0, 3], [0, 1, -2]])

# Cards of prep_screen_cleared.png by index: 2 and 3 are water, 10 is rock.
WATER_CARD, OTHER_WATER_CARD, ROCK_CARD = 2, 3, 10
# prep_screen_deployed.png: every whole card has the green check except these.
NOT_DEPLOYED = {5, 9, 11}


def _load(name: str) -> np.ndarray:
    image = cv2.imread(str(DATA_DIR / name))
    assert image is not None
    return image


def _card(screen: np.ndarray, index: int) -> np.ndarray:
    left, top, right, bottom = card_box(tray_slots()[index])
    return screen[top:bottom, left:right].copy()


@pytest.fixture(scope="module")
def cleared() -> np.ndarray:
    return _load("prep_screen_cleared.png")


@pytest.fixture(scope="module")
def deployed() -> np.ndarray:
    return _load("prep_screen_deployed.png")


def test_saved_template_is_matched(tmp_path: Path, cleared: np.ndarray) -> None:
    store = CardTemplateStore(tmp_path)
    store.save("water-3-3", _card(cleared, WATER_CARD))
    assert store.match(_card(cleared, WATER_CARD), "water") == "water-3-3"


def test_match_tolerates_a_small_shift(tmp_path: Path, cleared: np.ndarray) -> None:
    store = CardTemplateStore(tmp_path)
    store.save("water-3-3", _card(cleared, WATER_CARD))
    card = _card(cleared, WATER_CARD)
    shifted = cv2.warpAffine(
        card, SHIFT, (card.shape[1], card.shape[0]), borderMode=cv2.BORDER_REPLICATE
    )
    assert store.match(shifted, "water") == "water-3-3"


def test_other_cards_do_not_match(tmp_path: Path, cleared: np.ndarray) -> None:
    store = CardTemplateStore(tmp_path)
    store.save("water-3-3", _card(cleared, WATER_CARD))
    assert store.match(_card(cleared, OTHER_WATER_CARD), "water") is None


def test_only_templates_of_the_same_element_are_compared(
    tmp_path: Path, cleared: np.ndarray
) -> None:
    store = CardTemplateStore(tmp_path)
    store.save("water-3-3", _card(cleared, WATER_CARD))
    assert store.match(_card(cleared, WATER_CARD), "rock") is None


def test_templates_persist_on_disk(tmp_path: Path, cleared: np.ndarray) -> None:
    CardTemplateStore(tmp_path).save("water-3-3", _card(cleared, WATER_CARD))
    assert (tmp_path / "water" / "water-3-3.png").is_file()
    reloaded = CardTemplateStore(tmp_path)
    assert reloaded.match(_card(cleared, WATER_CARD), "water") == "water-3-3"


def test_saving_again_replaces_the_template(
    tmp_path: Path, cleared: np.ndarray
) -> None:
    store = CardTemplateStore(tmp_path)
    store.save("water-3-3", _card(cleared, OTHER_WATER_CARD))
    store.save("water-3-3", _card(cleared, WATER_CARD))
    assert store.match(_card(cleared, WATER_CARD), "water") == "water-3-3"
    assert store.match(_card(cleared, OTHER_WATER_CARD), "water") is None


def test_missing_directory_matches_nothing(tmp_path: Path, cleared: np.ndarray) -> None:
    store = CardTemplateStore(tmp_path / "missing")
    assert store.match(_card(cleared, WATER_CARD), "water") is None


def test_unreadable_template_file_is_skipped(
    tmp_path: Path, cleared: np.ndarray
) -> None:
    (tmp_path / "water").mkdir()
    (tmp_path / "water" / "water-1-1.png").write_bytes(b"not a png")
    store = CardTemplateStore(tmp_path)
    store.save("water-3-3", _card(cleared, WATER_CARD))
    assert store.match(_card(cleared, WATER_CARD), "water") == "water-3-3"


def test_store_sees_template_added_by_another_store(
    tmp_path: Path, cleared: np.ndarray
) -> None:
    reader = CardTemplateStore(tmp_path)
    assert reader.match(_card(cleared, WATER_CARD), "water") is None
    CardTemplateStore(tmp_path).save("water-3-3", _card(cleared, WATER_CARD))
    assert reader.match(_card(cleared, WATER_CARD), "water") == "water-3-3"


def test_store_sees_template_replaced_in_place(
    tmp_path: Path, cleared: np.ndarray
) -> None:
    reader = CardTemplateStore(tmp_path)
    reader.save("water-3-3", _card(cleared, WATER_CARD))
    assert reader.match(_card(cleared, OTHER_WATER_CARD), "water") is None
    CardTemplateStore(tmp_path).save("water-3-3", _card(cleared, OTHER_WATER_CARD))
    path = tmp_path / "water" / "water-3-3.png"
    stamp = path.stat().st_mtime_ns + 10**9
    os.utime(path, ns=(stamp, stamp))
    assert reader.match(_card(cleared, OTHER_WATER_CARD), "water") == "water-3-3"


def test_own_save_does_not_hide_a_template_written_meanwhile(
    tmp_path: Path, cleared: np.ndarray
) -> None:
    battle = CardTemplateStore(tmp_path)
    assert battle.match(_card(cleared, WATER_CARD), "water") is None
    # The viewer teaches one card while the battle recognizes another one.
    CardTemplateStore(tmp_path).save("water-3-3", _card(cleared, WATER_CARD))
    battle.save("water-5-2", _card(cleared, OTHER_WATER_CARD))
    assert battle.match(_card(cleared, WATER_CARD), "water") == "water-3-3"


def test_is_deployed_on_real_screens(cleared: np.ndarray, deployed: np.ndarray) -> None:
    assert not any(is_deployed(_card(cleared, i)) for i in range(12))
    found = {i for i in range(12) if is_deployed(_card(deployed, i))}
    assert found == set(range(12)) - NOT_DEPLOYED
