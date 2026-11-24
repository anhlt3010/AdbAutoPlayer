"""Tests for the Clash of Critters formation viewer."""

import base64
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from adb_auto_player.games.clash_of_critters import formation_view
from adb_auto_player.games.clash_of_critters.battle_layout import DOJO_LAYOUT
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
    StageId,
)
from adb_auto_player.games.clash_of_critters.formation_view import (
    build_response,
    load_formation_view,
    read_stage_from_screenshot,
    read_tray_element,
    sprite_data_uri,
)
from adb_auto_player.games.clash_of_critters.tatari_db import Sprite, TatariDb
from PIL import Image

STAGE = StageId(15, 50)
SPRITE_MAX_SIDE = 96
DATA_DIR = Path(__file__).parent / "data"


def _capture(name: str) -> np.ndarray:
    image = cv2.imread(str(DATA_DIR / name))
    assert image is not None, name
    return image


def _png(path: Path, size: tuple[int, int] = (200, 300)) -> Path:
    Image.new("RGBA", size, (255, 0, 0, 128)).save(path)
    return path


def _db(png: Path) -> TatariDb:
    return TatariDb([Sprite("grass-4-4", "grass-4", "grass", 4, False, png)])


def _unit(row: int, col: int, evolution_id: str, glitter: bool = False):
    tatari_id, tier = evolution_id.rsplit("-", 1)
    return FormationUnit(
        row,
        col,
        tatari_id,
        evolution_id,
        int(tier.rstrip("g")),
        glitter,
        name="Orchitoria",
    )


def test_units_keep_file_order_level_and_glitter(tmp_path: Path) -> None:
    db = _db(_png(tmp_path / "s.png"))
    formations = (
        Formation(STAGE, (_unit(1, 1, "grass-4-4"),), index=0, level=1475),
        Formation(
            STAGE, (_unit(2, 3, "grass-4-4g", glitter=True),), index=1, level=1500
        ),
    )
    response = build_response(STAGE, formations, db)
    assert response.status == "ok"
    assert response.stage == "15-50"
    assert [f.level for f in response.formations] == [1475, 1500]
    first = response.formations[0].units[0]
    assert (first.row, first.col, first.tier, first.name) == (1, 1, 4, "Orchitoria")
    assert first.glitter is False
    second = response.formations[1].units[0]
    assert (second.row, second.col, second.evolution_id) == (2, 3, "grass-4-4g")
    assert second.glitter is True


def test_sprite_is_a_small_png_data_uri(tmp_path: Path) -> None:
    uri = sprite_data_uri(_png(tmp_path / "big.png", (200, 300)))
    assert uri is not None
    assert uri.startswith("data:image/png;base64,")
    image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert image.mode == "RGBA"
    assert max(image.size) == SPRITE_MAX_SIDE


def test_missing_sprite_file_gives_none(tmp_path: Path) -> None:
    assert sprite_data_uri(tmp_path / "nope.png") is None


def test_unknown_evolution_has_no_sprite(tmp_path: Path) -> None:
    db = _db(_png(tmp_path / "s.png"))
    formation = Formation(STAGE, (_unit(1, 1, "fire-9-3"),), level=10)
    response = build_response(STAGE, (formation,), db)
    unit = response.formations[0].units[0]
    assert "fire-9-3" not in response.sprites
    assert (unit.tier, unit.name) == (3, "Orchitoria")


def test_known_evolution_gets_its_sprite(tmp_path: Path) -> None:
    db = _db(_png(tmp_path / "s.png"))
    formation = Formation(STAGE, (_unit(1, 1, "grass-4-4"),))
    response = build_response(STAGE, (formation,), db)
    sprite = response.sprites.get("grass-4-4")
    assert sprite is not None
    assert sprite.startswith("data:image/png;base64,")


def test_repeated_evolution_is_sent_once(tmp_path: Path) -> None:
    db = _db(_png(tmp_path / "s.png"))
    first = Formation(STAGE, (_unit(1, 1, "grass-4-4"), _unit(1, 2, "grass-4-4")))
    second = Formation(STAGE, (_unit(2, 2, "grass-4-4"),), index=1)
    response = build_response(STAGE, (first, second), db)
    assert list(response.sprites) == ["grass-4-4"]
    assert sum(len(f.units) for f in response.formations) == 3


def test_no_formations_gives_no_formation(tmp_path: Path) -> None:
    response = build_response(STAGE, (), _db(_png(tmp_path / "s.png")))
    assert response.status == "no_formation"
    assert response.stage == "15-50"
    assert response.formations == []


def test_fight_screen_reads_its_stage() -> None:
    assert read_stage_from_screenshot(_capture("battle_screen.png")) == StageId(15, 50)


@pytest.mark.parametrize(
    ("name", "stage"),
    [
        ("prep_screen_cleared.png", StageId(15, 50)),
        ("prep_screen_scrolled.png", StageId(15, 50)),
        ("prep_screen_deployed.png", StageId(15, 50)),
        ("prep_screen_report.png", StageId(15, 50)),
        ("prep_screen_auto_fight.png", StageId(15, 51)),
    ],
)
def test_preparation_screens_read_a_stage(name: str, stage: StageId) -> None:
    assert read_stage_from_screenshot(_capture(name)) == stage


@pytest.mark.parametrize(
    "name",
    [
        "camp_screen.png",
        "defeat_screen.png",
        "victory_screen.png",
        "stage_map_screen.png",
        "map_after_victory.png",
    ],
)
def test_screens_without_a_label_are_unreadable(name: str) -> None:
    assert read_stage_from_screenshot(_capture(name)) is None


def test_half_size_screenshot_still_reads() -> None:
    half = cv2.resize(_capture("battle_screen.png"), (540, 960))
    assert read_stage_from_screenshot(half) == StageId(15, 50)


def test_near_miss_text_is_unreadable() -> None:
    backend = MagicMock()
    backend.extract_text.return_value = "15-5O"
    with patch.object(formation_view, "_ocr", return_value=backend):
        assert read_stage_from_screenshot(_capture("battle_screen.png")) is None


REAL_ROOT = Path(formation_view.__file__).parent


def _no_grab() -> np.ndarray:
    raise AssertionError("the screenshot must not be taken")


def _grab_of(name: str):
    return lambda: _capture(name)


def test_typed_stage_skips_the_screenshot() -> None:
    response = load_formation_view("73-1", grab=_no_grab, data_root=REAL_ROOT)
    assert response.status == "ok"
    assert response.stage == "73-1"
    assert len(response.formations) == 1
    assert response.formations[0].level == 1475
    assert len(response.formations[0].units) == 15
    first = response.formations[0].units[0]
    assert (first.evolution_id, first.tier, first.name) == (
        "grass-4-4",
        4,
        "Orchitoria",
    )
    assert "grass-4-4" in response.sprites


def test_typed_stage_with_en_dash_and_spaces() -> None:
    response = load_formation_view("73 \u2013 1", grab=_no_grab, data_root=REAL_ROOT)
    assert (response.status, response.stage) == ("ok", "73-1")


def test_bad_typed_stage_is_invalid() -> None:
    response = load_formation_view("abc", grab=_no_grab, data_root=REAL_ROOT)
    assert response.status == "stage_invalid"
    assert response.stage is None
    assert response.formations == []


def test_typed_stage_without_file() -> None:
    response = load_formation_view("99-99", grab=_no_grab, data_root=REAL_ROOT)
    assert response.status == "no_formation"
    assert response.stage == "99-99"


def test_formation_with_only_bad_units_gives_no_formation(tmp_path: Path) -> None:
    folder = tmp_path / "tatari_formations" / "15"
    folder.mkdir(parents=True)
    bad_unit = {
        "row": 9,
        "col": 9,
        "tatari_id": "grass-4",
        "evolution_id": "grass-4-4",
        "tier": 4,
    }
    (folder / "15-1.json").write_text(
        json.dumps({"formations": [{"level": 1, "units": [bad_unit]}]}),
        encoding="utf-8",
    )
    db_folder = tmp_path / "tatari_db"
    db_folder.mkdir()
    (db_folder / "tatari_db.json").write_text('{"tataris": []}', encoding="utf-8")
    response = load_formation_view("15-1", grab=_no_grab, data_root=tmp_path)
    assert response.status == "no_formation"
    assert response.stage == "15-1"


def test_screen_stage_comes_from_the_capture() -> None:
    response = load_formation_view(
        None, grab=_grab_of("battle_screen.png"), data_root=REAL_ROOT
    )
    assert response.stage == "15-50"


def test_screen_without_label_is_unreadable() -> None:
    response = load_formation_view(
        None, grab=_grab_of("camp_screen.png"), data_root=REAL_ROOT
    )
    assert response.status == "stage_unreadable"
    assert response.stage is None


def test_failing_grab_means_no_device() -> None:
    def grab() -> np.ndarray:
        raise RuntimeError("no device")

    response = load_formation_view(None, grab=grab, data_root=REAL_ROOT)
    assert response.status == "no_device"
    assert response.formations == []


# --- Võ Đường mode -------------------------------------------------------

ASSETS_DIR = Path(__file__).parents[5] / "docs" / "superpowers" / "specs" / "assets"
DOJO_BOX = DOJO_LAYOUT.stage_label_box


def _dojo(name: str) -> np.ndarray:
    image = cv2.imread(str(ASSETS_DIR / name))
    assert image is not None, name
    return image


def _dojo_grab(name: str):
    return lambda: _dojo(name)


def _votes(elements: list[str | None]):
    """A classify_element replacement that answers the list in call order."""
    answers = iter(elements)
    return lambda _icon: next(answers, None)


def test_dojo_prep_screen_reads_its_stage_with_the_dojo_box() -> None:
    screen = _dojo("dojo_prep_cleared.png")
    assert read_stage_from_screenshot(screen, DOJO_BOX) == StageId(4, 2)


def test_dojo_prep_screen_votes_its_element() -> None:
    assert read_tray_element(_dojo("dojo_prep_cleared.png")) == "grass"
    assert read_tray_element(_dojo("dojo_prep_scrolled.png")) == "grass"


def test_screen_without_a_tray_has_no_element() -> None:
    assert read_tray_element(_capture("camp_screen.png")) is None


def test_one_vote_is_not_enough(monkeypatch) -> None:
    monkeypatch.setattr(
        formation_view, "classify_element", _votes(["grass", None, None])
    )
    assert read_tray_element(_dojo("dojo_prep_cleared.png")) is None


def test_tied_vote_is_unreadable(monkeypatch) -> None:
    monkeypatch.setattr(
        formation_view,
        "classify_element",
        _votes(["grass", "grass", "fire", "fire"]),
    )
    assert read_tray_element(_dojo("dojo_prep_cleared.png")) is None


def test_dojo_screen_gives_formations_of_the_detected_element() -> None:
    response = load_formation_view(
        None, grab=_dojo_grab("dojo_prep_cleared.png"), data_root=REAL_ROOT, mode="dojo"
    )
    assert (response.status, response.stage, response.element, response.mode) == (
        "ok",
        "4-2",
        "grass",
        "dojo",
    )
    assert response.formations


def test_a_readable_tray_beats_the_remembered_element() -> None:
    # The page sends the element it knows with every load; a screen read after the
    # bot moved to another Võ Đường must still follow the tray.
    response = load_formation_view(
        None,
        grab=_dojo_grab("dojo_prep_cleared.png"),
        data_root=REAL_ROOT,
        mode="dojo",
        element="fire",
    )
    assert (response.status, response.stage, response.element) == ("ok", "4-2", "grass")


def test_an_unreadable_tray_falls_back_to_the_given_element(monkeypatch) -> None:
    monkeypatch.setattr(formation_view, "read_tray_element", lambda *_: None)
    response = load_formation_view(
        None,
        grab=_dojo_grab("dojo_prep_cleared.png"),
        data_root=REAL_ROOT,
        mode="dojo",
        element="fire",
    )
    assert (response.stage, response.element) == ("4-2", "fire")


def test_dojo_screen_without_element_keeps_the_stage(monkeypatch) -> None:
    monkeypatch.setattr(formation_view, "read_tray_element", lambda *_: None)
    response = load_formation_view(
        None, grab=_dojo_grab("dojo_prep_cleared.png"), data_root=REAL_ROOT, mode="dojo"
    )
    assert (response.status, response.stage, response.element) == (
        "element_unreadable",
        "4-2",
        None,
    )


def test_dojo_typed_stage_with_element_skips_the_screenshot() -> None:
    response = load_formation_view(
        "4-3", grab=_no_grab, data_root=REAL_ROOT, mode="dojo", element="grass"
    )
    assert (response.status, response.stage, response.element) == (
        "ok",
        "4-3",
        "grass",
    )


def test_dojo_typed_stage_without_element_is_unreadable() -> None:
    response = load_formation_view(
        "4-3", grab=_no_grab, data_root=REAL_ROOT, mode="dojo"
    )
    assert (response.status, response.stage) == ("element_unreadable", "4-3")


def test_a_dojo_has_ten_stages_so_a_typed_eleventh_is_invalid() -> None:
    response = load_formation_view(
        "4-11", grab=_no_grab, data_root=REAL_ROOT, mode="dojo", element="grass"
    )
    assert response.status == "stage_invalid"
    assert response.formations == []


def test_a_dojo_stage_read_from_the_screen_above_ten_is_unreadable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        formation_view, "read_stage_from_screenshot", lambda *_: StageId(4, 11)
    )
    response = load_formation_view(
        None, grab=_dojo_grab("dojo_prep_cleared.png"), data_root=REAL_ROOT, mode="dojo"
    )
    assert response.status == "stage_unreadable"


def test_cards_cut_off_by_the_screen_edge_do_not_vote(monkeypatch) -> None:
    seen: list[object] = []

    def classify(icon):
        seen.append(icon)
        return "fire"

    # One whole card and one cut by the right edge of the screen, in each tray row.
    monkeypatch.setattr(formation_view, "find_card_lefts", lambda *_: [20, 1000])
    monkeypatch.setattr(formation_view, "classify_element", classify)
    assert read_tray_element(_dojo("dojo_prep_cleared.png")) == "fire"
    assert len(seen) == len(DOJO_LAYOUT.tray_rows_y)  # only the whole cards


def test_dojo_unknown_element_is_unreadable() -> None:
    response = load_formation_view(
        "4-3", grab=_no_grab, data_root=REAL_ROOT, mode="dojo", element="wind"
    )
    assert response.status == "element_unreadable"


def test_dojo_screen_without_label_is_stage_unreadable() -> None:
    response = load_formation_view(
        None, grab=_grab_of("camp_screen.png"), data_root=REAL_ROOT, mode="dojo"
    )
    assert response.status == "stage_unreadable"


def test_dojo_typed_stage_without_file_names_the_element() -> None:
    response = load_formation_view(
        "9-1", grab=_no_grab, data_root=REAL_ROOT, mode="dojo", element="grass"
    )
    assert (response.status, response.element, response.mode) == (
        "no_formation",
        "grass",
        "dojo",
    )
