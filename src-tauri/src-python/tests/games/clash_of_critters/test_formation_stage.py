"""Tests for Clash of Critters stage parsing and the boss rule."""

import pytest
from adb_auto_player.games.clash_of_critters.formation import (
    StageId,
    is_boss_stage,
    parse_stage,
)


def test_parse_plain() -> None:
    assert parse_stage("15-50") == StageId(15, 50)


def test_parse_with_spaces() -> None:
    assert parse_stage(" 4 - 7 ") == StageId(4, 7)


def test_parse_inside_other_text() -> None:
    assert parse_stage("Cấp 399 15-50") == StageId(15, 50)


@pytest.mark.parametrize("text", ["15-5O", "", "abc"])
def test_parse_garbage_returns_none(text: str) -> None:
    assert parse_stage(text) is None


def test_str() -> None:
    assert str(StageId(15, 50)) == "15-50"


@pytest.mark.parametrize("stage", [StageId(15, 10), StageId(15, 50), StageId(76, 80)])
def test_boss_stages(stage: StageId) -> None:
    assert is_boss_stage(stage)


@pytest.mark.parametrize("stage", [StageId(15, 49), StageId(15, 1)])
def test_normal_stages(stage: StageId) -> None:
    assert not is_boss_stage(stage)
