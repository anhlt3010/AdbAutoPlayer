"""Tests for the tatari database loader."""

import json
from pathlib import Path

import pytest
from adb_auto_player.games.clash_of_critters import tatari_db as db_module
from adb_auto_player.games.clash_of_critters.tatari_db import ELEMENTS, TatariDb

REAL_ROOT = Path(db_module.__file__).parent / "tatari_db"


def _evolution(evo_id: str, stage: int, glitter: bool) -> dict:
    entry = {
        "stage": stage,
        "name": "N",
        "normal": {"id": evo_id, "image": f"images/{evo_id}.png"},
        "glitter": None,
    }
    if glitter:
        entry["glitter"] = {
            "id": f"{evo_id}g",
            "name": "G",
            "image": f"images/{evo_id}g.png",
        }
    return entry


@pytest.fixture
def small_root(tmp_path: Path) -> Path:
    data = {
        "source": "test",
        "tataris": [
            {
                "tatari_id": "water-3",
                "type": "Water",
                "has_glitter": True,
                "evolutions": [
                    _evolution("water-3-1", 1, True),
                    _evolution("water-3-2", 2, True),
                ],
            },
            {
                "tatari_id": "fire-1",
                "type": "Fire",
                "has_glitter": False,
                "evolutions": [_evolution("fire-1-1", 1, False)],
            },
        ],
    }
    (tmp_path / "tatari_db.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_sprites_for_element_include_glitter(small_root: Path) -> None:
    db = TatariDb.load(small_root)
    ids = {s.evolution_id for s in db.sprites_for_element("water")}
    assert ids == {"water-3-1", "water-3-1g", "water-3-2", "water-3-2g"}
    assert [s.evolution_id for s in db.sprites_for_element("fire")] == ["fire-1-1"]
    assert db.sprites_for_element("rock") == []


def test_get_fields(small_root: Path) -> None:
    sprite = TatariDb.load(small_root).get("water-3-2g")
    assert sprite is not None
    assert sprite.element == "water"
    assert sprite.tatari_id == "water-3"
    assert sprite.tier == 2
    assert sprite.glitter is True
    assert sprite.image_path == small_root / "images" / "water-3-2g.png"


def test_get_unknown_returns_none(small_root: Path) -> None:
    assert TatariDb.load(small_root).get("nope-1-1") is None


@pytest.mark.skipif(not REAL_ROOT.exists(), reason="tatari_db data not present")
def test_real_database() -> None:
    db = TatariDb.load(REAL_ROOT)
    total = sum(len(db.sprites_for_element(e)) for e in ELEMENTS)
    assert total == len(list((REAL_ROOT / "images").glob("*.png")))
    sprite = db.get("water-3-3g")
    assert sprite is not None
    assert sprite.glitter is True
    assert sprite.tier == 3
    for element in ELEMENTS:
        assert db.sprites_for_element(element)
        assert all(s.image_path.exists() for s in db.sprites_for_element(element))
