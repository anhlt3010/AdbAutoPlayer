"""Tests for loading Clash of Critters formation files."""

import json
from pathlib import Path

import pytest
from adb_auto_player.games.clash_of_critters import formation as formation_module
from adb_auto_player.games.clash_of_critters.formation import (
    FormationUnit,
    StageId,
    load_formation,
)

REAL_ROOT = Path(formation_module.__file__).parent / "tatari_formations"


def _unit(row: int, col: int, evolution_id: str = "grass-4-2") -> dict:
    tatari_id, tier = evolution_id.rsplit("-", 1)
    return {
        "row": row,
        "col": col,
        "tatari_id": tatari_id,
        "evolution_id": evolution_id,
        "name": "X",
        "tier": int(tier),
        "glitter": False,
    }


def _write(root: Path, stage: str, shared_with: str, units: list[dict]) -> None:
    chapter = stage.split("-", maxsplit=1)[0]
    folder = root / chapter
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "chapter": int(chapter),
        "stage": stage,
        "level": 100,
        "shared_with": shared_with,
        "units": units,
    }
    (folder / f"{stage}.json").write_text(json.dumps(data), encoding="utf-8")


def test_loads_units(tmp_path: Path) -> None:
    _write(tmp_path, "15-1", "15-1", [_unit(1, 1), _unit(2, 3, "fire-3-2")])
    result = load_formation(tmp_path, StageId(15, 1))
    assert result is not None
    assert result.stage == StageId(15, 1)
    assert result.units[0] == FormationUnit(1, 1, "grass-4", "grass-4-2", 2, False)
    assert result.units[1].evolution_id == "fire-3-2"


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_formation(tmp_path, StageId(4, 2)) is None


def test_shared_with_other_stage_loads_that_file(tmp_path: Path) -> None:
    _write(tmp_path, "15-1", "15-1", [_unit(1, 1), _unit(1, 2)])
    _write(tmp_path, "15-2", "15-1", [])
    result = load_formation(tmp_path, StageId(15, 2))
    assert result is not None
    assert result.stage == StageId(15, 2)
    assert len(result.units) == 2


def test_shared_with_self_uses_own_units(tmp_path: Path) -> None:
    _write(tmp_path, "15-3", "15-3", [_unit(5, 5)])
    result = load_formation(tmp_path, StageId(15, 3))
    assert result is not None
    assert [(u.row, u.col) for u in result.units] == [(5, 5)]


def test_shared_with_missing_file_returns_none(tmp_path: Path) -> None:
    _write(tmp_path, "15-2", "15-1", [])
    assert load_formation(tmp_path, StageId(15, 2)) is None


def test_shared_with_loop_returns_none(tmp_path: Path) -> None:
    _write(tmp_path, "15-1", "15-2", [])
    _write(tmp_path, "15-2", "15-1", [])
    assert load_formation(tmp_path, StageId(15, 1)) is None


@pytest.mark.skipif(not REAL_ROOT.exists(), reason="formation data not present")
def test_real_boss_file_loads() -> None:
    result = load_formation(REAL_ROOT, StageId(15, 50))
    assert result is not None
    assert result.units
    assert all(1 <= u.row <= 5 and 1 <= u.col <= 5 for u in result.units)


@pytest.mark.parametrize(
    "units",
    [
        [{"row": 1, "col": 1}],  # keys missing
        [{**_unit(1, 1), "row": "x"}],  # not a number
        [_unit(0, 1)],  # outside the 5x5 field
        [_unit(1, 6)],
        ["not a unit"],
    ],
)
def test_a_malformed_unit_means_no_formation(tmp_path: Path, units: list) -> None:
    _write(tmp_path, "15-1", "15-1", units)
    assert load_formation(tmp_path, StageId(15, 1)) is None


def test_a_file_that_is_not_an_object_means_no_formation(tmp_path: Path) -> None:
    (tmp_path / "15").mkdir()
    (tmp_path / "15" / "15-1.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert load_formation(tmp_path, StageId(15, 1)) is None
