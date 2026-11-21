"""HTML page that shows the prepared formations of a stage."""

from html import escape

from adb_auto_player.games.clash_of_critters.formation_view import (
    FormationViewResponse,
    ViewFormation,
    ViewUnit,
)

_GRID_SIZE = 5

_STYLE = """
body { font-family: sans-serif; background: #1e1e24; color: #eee; margin: 24px; }
h1 { font-size: 22px; }
h2 { font-size: 16px; margin: 24px 0 8px; }
.grid { display: grid; grid-template-columns: repeat(5, 96px); gap: 6px; }
.cell { width: 96px; height: 112px; border-radius: 8px; background: #2b2b33;
  display: flex; flex-direction: column; align-items: center;
  justify-content: flex-start; font-size: 11px; text-align: center; }
.cell.unit { background: #3a3a46; }
.cell.glitter { box-shadow: 0 0 0 2px gold; }
.cell img { width: 80px; height: 80px; object-fit: contain; }
.name { overflow: hidden; max-width: 92px; white-space: nowrap;
  text-overflow: ellipsis; }
"""


def _cell(unit: ViewUnit | None, sprites: dict[str, str]) -> str:
    if unit is None:
        return '<div class="cell"></div>'
    classes = "cell unit glitter" if unit.glitter else "cell unit"
    sprite = sprites.get(unit.evolution_id)
    image = f'<img src="{escape(sprite, quote=True)}" alt="">' if sprite else ""
    return (
        f'<div class="{classes}">{image}'
        f'<span class="name">{escape(unit.name)}</span>'
        f"<span>T{unit.tier}</span></div>"
    )


def _grid(formation: ViewFormation, sprites: dict[str, str]) -> str:
    by_cell = {(unit.row, unit.col): unit for unit in formation.units}
    cells = [
        _cell(by_cell.get((row, col)), sprites)
        for row in range(1, _GRID_SIZE + 1)
        for col in range(1, _GRID_SIZE + 1)
    ]
    return '<div class="grid">' + "".join(cells) + "</div>"


def render_formation_page(response: FormationViewResponse) -> str:
    """Build a self-contained HTML page with every formation of the stage.

    Args:
        response: The formations and sprites of a stage (status "ok").

    Returns:
        A complete HTML document: one 5x5 grid per formation, each cell with the
        sprite, name and tier of its tatari (cells without a tatari are blank).
    """
    total = len(response.formations)
    sections = []
    for index, formation in enumerate(response.formations, start=1):
        level = f" - Lv {formation.level}" if formation.level is not None else ""
        sections.append(
            f"<h2>Đội hình {index}/{total}{level}</h2>"
            + _grid(formation, response.sprites)
        )
    stage = escape(response.stage or "")
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>Màn {stage}</title><style>{_STYLE}</style></head><body>"
        f"<h1>Màn {stage}</h1>{''.join(sections)}</body></html>"
    )
