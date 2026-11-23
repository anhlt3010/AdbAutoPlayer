"""Tests for teaching the bot cards it did not recognize."""

import shutil
from pathlib import Path

import cv2
import pytest
from adb_auto_player.games.clash_of_critters import card_recognition as cr_module
from adb_auto_player.games.clash_of_critters.card_recognition import (
    TEMPLATE_DIR_NAME,
    UNRECOGNIZED_DIR_NAME,
    CardTemplateStore,
)
from adb_auto_player.games.clash_of_critters.card_teaching import (
    load_waiting_cards,
    teach_card,
)
from adb_auto_player.games.clash_of_critters.tatari_db import TatariDb

DATA_DIR = Path(__file__).parent / "data"
DB_ROOT = Path(cr_module.__file__).parent / "tatari_db"

pytestmark = pytest.mark.skipif(
    not DB_ROOT.exists(), reason="tatari_db data not present"
)


@pytest.fixture(scope="module")
def db() -> TatariDb:
    return TatariDb.load(DB_ROOT)


def _add(config_dir: Path, *names: str) -> list[str]:
    """Copy fixture crops into the unrecognized folder; returns their ids."""
    folder = config_dir / UNRECOGNIZED_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy(DATA_DIR / f"unrecognized_{name}.png", folder / f"{name}.png")
    return list(names)


def _files(config_dir: Path) -> set[str]:
    return {
        p.relative_to(config_dir).as_posix()
        for p in config_dir.rglob("*")
        if p.is_file()
    }


def test_load_lists_cards_and_choices(tmp_path: Path, db: TatariDb) -> None:
    _add(tmp_path, "fire_8_a", "water_10_a")
    result = load_waiting_cards(tmp_path, db)
    assert {card.element for card in result.cards} == {"fire", "water"}
    assert all(card.image.startswith("data:image/png;base64,") for card in result.cards)
    assert set(result.choices) == {"fire", "water"}
    fire = {choice.evolution_id: choice for choice in result.choices["fire"]}
    assert fire["fire-8-2"].sprite is not None
    assert fire["fire-8-2"].sprite.startswith("data:image/png;base64,")
    assert fire["fire-8-2"].tier == 2
    assert not fire["fire-8-2"].glitter


def test_load_missing_folder(tmp_path: Path, db: TatariDb) -> None:
    result = load_waiting_cards(tmp_path, db)
    assert result.cards == []
    assert result.choices == {}


def test_load_skips_unreadable(tmp_path: Path, db: TatariDb) -> None:
    _add(tmp_path, "fire_8_a")
    (tmp_path / UNRECOGNIZED_DIR_NAME / "bad.png").write_bytes(b"junk")
    assert [card.id for card in load_waiting_cards(tmp_path, db).cards] == [
        "fire_8_a"
    ]


def test_teach_ok_removes_duplicates(tmp_path: Path, db: TatariDb) -> None:
    _add(tmp_path, "fire_8_a", "fire_8_b", "water_10_a")
    assert teach_card(tmp_path, db, "fire_8_a", "fire-8-2") == "ok"
    assert (tmp_path / TEMPLATE_DIR_NAME / "fire" / "fire-8-2.png").is_file()
    left = sorted(p.stem for p in (tmp_path / UNRECOGNIZED_DIR_NAME).glob("*.png"))
    assert left == ["water_10_a"]
    store = CardTemplateStore(tmp_path / TEMPLATE_DIR_NAME)
    card = cv2.imread(str(DATA_DIR / "unrecognized_fire_8_b.png"))
    assert store.match(card, "fire") == "fire-8-2"


def test_teach_unknown_evolution(tmp_path: Path, db: TatariDb) -> None:
    _add(tmp_path, "fire_8_a")
    before = _files(tmp_path)
    assert teach_card(tmp_path, db, "fire_8_a", "fire-99-1") == "unknown_evolution"
    assert _files(tmp_path) == before


def test_teach_wrong_element(tmp_path: Path, db: TatariDb) -> None:
    _add(tmp_path, "fire_8_a")
    before = _files(tmp_path)
    assert teach_card(tmp_path, db, "fire_8_a", "water-10-2") == "wrong_element"
    assert _files(tmp_path) == before


@pytest.mark.parametrize("crop_id", ["nope", "../fire_8_a", "", "fire_8_a.png"])
def test_teach_unknown_crop(tmp_path: Path, db: TatariDb, crop_id: str) -> None:
    _add(tmp_path, "fire_8_a")
    before = _files(tmp_path)
    assert teach_card(tmp_path, db, crop_id, "fire-8-2") == "unknown_crop"
    assert _files(tmp_path) == before


def test_reteach_replaces_only_that_template(tmp_path: Path, db: TatariDb) -> None:
    other = tmp_path / TEMPLATE_DIR_NAME / "fire" / "fire-1-2.png"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"existing")
    _add(tmp_path, "fire_8_a")
    assert teach_card(tmp_path, db, "fire_8_a", "fire-8-2") == "ok"
    assert other.read_bytes() == b"existing"
