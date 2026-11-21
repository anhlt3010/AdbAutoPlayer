"""Plan which owned tatari fills each cell of a formation."""

import logging
from collections.abc import Collection
from dataclasses import dataclass

from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
)

_GLITTER_SUFFIX = "g"


def split_evolution_id(evolution_id: str) -> tuple[str, int, bool]:
    """Split an evolution id into its tatari id, tier and glitter flag.

    Args:
        evolution_id: For example "water-3-2" or "water-3-2g".

    Returns:
        A tuple such as ("water-3", 2, True) for "water-3-2g".
    """
    glitter = evolution_id.endswith(_GLITTER_SUFFIX)
    base = evolution_id.removesuffix(_GLITTER_SUFFIX)
    tatari_id, tier = base.rsplit("-", 1)
    return tatari_id, int(tier), glitter


@dataclass(frozen=True)
class Placement:
    """A formation unit and the owned evolution chosen for it (None if none)."""

    unit: FormationUnit
    evolution_id: str | None


def _choose(unit: FormationUnit, available: set[str]) -> str | None:
    base = unit.evolution_id.removesuffix(_GLITTER_SUFFIX)
    wanted = base + _GLITTER_SUFFIX if unit.glitter else base
    # Exact evolution first, then the same evolution with the other glitter flag.
    for candidate in (wanted, base, base + _GLITTER_SUFFIX):
        if candidate in available:
            return candidate

    family = []
    for owned_id in available:
        tatari_id, tier, glitter = split_evolution_id(owned_id)
        if tatari_id == unit.tatari_id:
            # Nearest tier; a higher tier wins a tie; normal before glitter.
            family.append((abs(tier - unit.tier), -tier, glitter, owned_id))
    if not family:
        return None
    return min(family)[3]


def plan_deployment(
    formation: Formation, owned: Collection[str], max_units: int = 15
) -> list[Placement]:
    """Choose an owned tatari for each unit of the formation.

    Each owned tatari is used at most once and units are handled in file order.

    Args:
        formation: The formation to deploy.
        owned: Evolution ids the player owns (glitter ids end in "g").
        max_units: The most units that can be on the field.

    Returns:
        One placement per unit, cut to max_units. A placement without an
        evolution id means the player has no usable tatari for that cell.
    """
    available = set(owned)
    placements: list[Placement] = []
    for unit in formation.units[:max_units]:
        chosen = _choose(unit, available)
        if chosen is None:
            logging.warning(
                f"No owned tatari for {unit.evolution_id} "
                f"(row {unit.row}, col {unit.col}), leaving the cell empty."
            )
        else:
            available.discard(chosen)
        placements.append(Placement(unit, chosen))
    return placements
