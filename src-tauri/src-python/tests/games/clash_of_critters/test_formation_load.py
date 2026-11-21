"""Tests for loading Clash of Critters formation files."""

import json
from pathlib import Path

import pytest
from adb_auto_player.games.clash_of_critters import formation as formation_module
from adb_auto_player.games.clash_of_critters.formation import (
    FormationUnit,
    StageId,
    load_formations,
    parse_stage,
)

REAL_ROOT = Path(formation_module.__file__).parent / "tatari_formations"
MIN_FORMATIONS = 2


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


def _write(
    root: Path, stage: str, shared_with: str, formations: list[list[dict]]
) -> None:
    chapter = stage.split("-", maxsplit=1)[0]
    folder = root / chapter
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "chapter": int(chapter),
        "stage": stage,
        "shared_with": shared_with,
        "formations": [
            {"source": "x", "level": 100 + i, "units": units}
            for i, units in enumerate(formations)
        ],
    }
    (folder / f"{stage}.json").write_text(json.dumps(data), encoding="utf-8")


def test_loads_every_formation_in_order(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "15-1",
        "15-1",
        [[_unit(1, 1), _unit(2, 3, "fire-3-2")], [_unit(1, 1), _unit(3, 3)]],
    )
    result = load_formations(tmp_path, StageId(15, 1))
    assert len(result) == MIN_FORMATIONS
    assert [f.index for f in result] == [0, 1]
    assert result[0].stage == StageId(15, 1)
    assert result[0].level == 100
    assert result[1].level == 101
    assert result[0].units[0] == FormationUnit(1, 1, "grass-4", "grass-4-2", 2, False)
    assert result[0].units[1].evolution_id == "fire-3-2"
    assert len(result[1].units) == MIN_FORMATIONS


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_formations(tmp_path, StageId(4, 2)) == ()


def test_shared_with_other_stage_loads_that_file(tmp_path: Path) -> None:
    _write(tmp_path, "15-1", "15-1", [[_unit(1, 1), _unit(1, 2)]])
    _write(tmp_path, "15-2", "15-1", [])
    result = load_formations(tmp_path, StageId(15, 2))
    assert len(result) == 1
    assert result[0].stage == StageId(15, 2)
    assert len(result[0].units) == MIN_FORMATIONS


def test_shared_with_self_uses_own_formations(tmp_path: Path) -> None:
    _write(tmp_path, "15-3", "15-3", [[_unit(5, 5)]])
    result = load_formations(tmp_path, StageId(15, 3))
    assert [(u.row, u.col) for u in result[0].units] == [(5, 5)]


def test_shared_with_is_ignored_when_the_stage_has_its_own_formations(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "15-1", "15-1", [[_unit(1, 1)]])
    _write(tmp_path, "15-2", "15-1", [[_unit(4, 4)]])
    result = load_formations(tmp_path, StageId(15, 2))
    assert [(u.row, u.col) for u in result[0].units] == [(4, 4)]


def test_shared_with_missing_file_returns_empty(tmp_path: Path) -> None:
    _write(tmp_path, "15-2", "15-1", [])
    assert load_formations(tmp_path, StageId(15, 2)) == ()


def test_shared_with_loop_returns_empty(tmp_path: Path) -> None:
    _write(tmp_path, "15-1", "15-2", [])
    _write(tmp_path, "15-2", "15-1", [])
    assert load_formations(tmp_path, StageId(15, 1)) == ()


def test_a_malformed_formation_is_skipped_and_the_others_are_kept(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "15-1", "15-1", [[{"row": 1, "col": 1}], [_unit(2, 2)]])
    result = load_formations(tmp_path, StageId(15, 1))
    assert len(result) == 1
    assert result[0].index == 0
    assert (result[0].units[0].row, result[0].units[0].col) == (2, 2)


def test_a_formation_without_units_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "15-1", "15-1", [[], [_unit(2, 2)]])
    result = load_formations(tmp_path, StageId(15, 1))
    assert len(result) == 1


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
    _write(tmp_path, "15-1", "15-1", [units])
    assert load_formations(tmp_path, StageId(15, 1)) == ()


def test_a_file_that_is_not_an_object_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "15").mkdir()
    (tmp_path / "15" / "15-1.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert load_formations(tmp_path, StageId(15, 1)) == ()


@pytest.mark.skipif(not REAL_ROOT.exists(), reason="formation data not present")
def test_real_boss_file_loads() -> None:
    result = load_formations(REAL_ROOT, StageId(15, 50))
    assert result
    assert all(1 <= u.row <= 5 and 1 <= u.col <= 5 for f in result for u in f.units)


@pytest.mark.skipif(not REAL_ROOT.exists(), reason="formation data not present")
def test_real_data_has_stages_with_several_formations() -> None:
    for path in sorted(REAL_ROOT.glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if len(data.get("formations") or []) >= MIN_FORMATIONS:
            stage = parse_stage(data["stage"])
            assert stage is not None
            result = load_formations(REAL_ROOT, stage)
            assert len(result) >= MIN_FORMATIONS
            assert all(
                1 <= u.row <= 5 and 1 <= u.col <= 5 for f in result for u in f.units
            )
            return
    pytest.fail("no stage with several formations in the data")
