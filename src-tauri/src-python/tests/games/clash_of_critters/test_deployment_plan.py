"""Tests for planning which owned tatari fills each formation cell."""

from adb_auto_player.games.clash_of_critters.deployment_plan import (
    plan_deployment,
    split_evolution_id,
)
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
    StageId,
)

STAGE = StageId(15, 50)


def _unit(evolution_id: str, row: int = 1, col: int = 1, glitter: bool = False):
    tatari_id, tier, _ = split_evolution_id(evolution_id)
    return FormationUnit(row, col, tatari_id, evolution_id, tier, glitter)


def _plan(units: list[FormationUnit], owned: set[str]) -> list[str | None]:
    result = plan_deployment(Formation(STAGE, tuple(units)), owned)
    return [placement.evolution_id for placement in result]


def test_split_evolution_id() -> None:
    assert split_evolution_id("water-3-2g") == ("water-3", 2, True)
    assert split_evolution_id("grass-4-2") == ("grass-4", 2, False)


def test_exact_id_is_used() -> None:
    assert _plan([_unit("grass-4-2")], {"grass-4-2", "grass-4-3"}) == ["grass-4-2"]


def test_glitter_wanted_but_only_normal_owned() -> None:
    unit = _unit("water-3-2g", glitter=True)
    assert _plan([unit], {"water-3-2"}) == ["water-3-2"]


def test_other_evolution_of_same_tatari_is_used() -> None:
    assert _plan([_unit("grass-4-2")], {"grass-4-3"}) == ["grass-4-3"]


def test_equal_distance_prefers_higher_tier() -> None:
    assert _plan([_unit("grass-4-2")], {"grass-4-1", "grass-4-3"}) == ["grass-4-3"]


def test_nearest_tier_wins() -> None:
    assert _plan([_unit("grass-4-3")], {"grass-4-1", "grass-4-2"}) == ["grass-4-2"]


def test_tatari_not_owned_gives_none() -> None:
    assert _plan([_unit("grass-4-2")], {"fire-3-2"}) == [None]


def test_each_owned_card_used_once() -> None:
    units = [_unit("grass-4-2", 1, 1), _unit("grass-4-2", 1, 2)]
    assert _plan(units, {"grass-4-2"}) == ["grass-4-2", None]


def test_at_most_fifteen_placements() -> None:
    units = [_unit("grass-4-2", 1 + i % 5, 1 + i // 5) for i in range(17)]
    owned = {f"grass-{i}-2" for i in range(17)}
    owned |= {"grass-4-2"}
    assert len(_plan(units, owned)) == 15


def test_placements_keep_unit_and_file_order() -> None:
    units = [_unit("grass-4-2", 1, 1), _unit("fire-3-2", 2, 3)]
    result = plan_deployment(Formation(STAGE, tuple(units)), {"grass-4-2"})
    assert [p.unit for p in result] == units
    assert [p.evolution_id for p in result] == ["grass-4-2", None]
