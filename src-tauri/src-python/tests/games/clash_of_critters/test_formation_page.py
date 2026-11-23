"""Tests for the HTML page of the prepared formations of a stage."""

from adb_auto_player.games.clash_of_critters.formation_page import (
    render_formation_page,
)
from adb_auto_player.games.clash_of_critters.formation_view import (
    FormationViewResponse,
    ViewFormation,
    ViewUnit,
)

SPRITE = "data:image/png;base64,AAAA"


def _unit(
    row: int,
    col: int,
    name: str = "Mochi",
    tier: int = 2,
    glitter: bool = False,
    evolution_id: str = "grass-4-2",
) -> ViewUnit:
    return ViewUnit(
        row=row,
        col=col,
        tatari_id="grass-4",
        evolution_id=evolution_id,
        name=name,
        tier=tier,
        glitter=glitter,
    )


def _response(
    formations: list[ViewFormation], sprites: dict[str, str] | None = None
) -> FormationViewResponse:
    return FormationViewResponse(
        status="ok",
        stage="15-50",
        formations=formations,
        sprites={"grass-4-2": SPRITE} if sprites is None else sprites,
    )


def test_page_has_the_stage_and_a_grid_per_formation() -> None:
    page = render_formation_page(
        _response(
            [
                ViewFormation(level=30, units=[_unit(1, 1)]),
                ViewFormation(level=None, units=[_unit(2, 2)]),
            ]
        )
    )
    assert "15-50" in page
    assert page.count('class="cell') == 2 * 25


def test_unit_cell_shows_sprite_name_and_tier() -> None:
    page = render_formation_page(
        _response([ViewFormation(level=None, units=[_unit(1, 1, glitter=True)])])
    )
    assert f'<img src="{SPRITE}"' in page
    assert "Mochi" in page
    assert "T2" in page
    assert 'class="cell unit glitter"' in page


def test_unit_without_a_sprite_still_shows_its_name() -> None:
    page = render_formation_page(
        _response([ViewFormation(level=None, units=[_unit(1, 1)])], sprites={})
    )
    assert "Mochi" in page
    assert "<img" not in page


def test_names_are_escaped() -> None:
    name = '<script>alert(1)</script>&"'
    page = render_formation_page(
        _response([ViewFormation(level=None, units=[_unit(1, 1, name=name)])])
    )
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_level_none_does_not_print_none() -> None:
    page = render_formation_page(
        _response([ViewFormation(level=None, units=[_unit(1, 1)])])
    )
    assert "None" not in page


def test_empty_cells_are_blank() -> None:
    page = render_formation_page(
        _response([ViewFormation(level=None, units=[_unit(1, 1)])])
    )
    assert page.count('class="cell unit') == 1
    assert page.count('class="cell"') == 24
