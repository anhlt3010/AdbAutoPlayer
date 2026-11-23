"""Clash of Critters stage ids and prepared formations."""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_BOSS_EVERY = 10
_MAX_SHARE_HOPS = 5
_FIELD_SIZE = 5
# A stage like "15-50"; digits must not touch other digits or letters, so an OCR
# misread such as "15-5O" is rejected instead of read as "15-5".
_STAGE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*-\s*(\d{1,3})(?![\dA-Za-z])")


@dataclass(frozen=True)
class StageId:
    """A stage of the campaign, for example 15-50."""

    chapter: int
    number: int

    def __str__(self) -> str:
        """Return the stage as "chapter-number"."""
        return f"{self.chapter}-{self.number}"


def parse_stage(text: str) -> StageId | None:
    """Find a stage id such as "15-50" in OCR text.

    Args:
        text: Text read from the stage label.

    Returns:
        The first stage id found, or None if the text holds none.
    """
    match = _STAGE_PATTERN.search(text)
    if match is None:
        return None
    return StageId(int(match.group(1)), int(match.group(2)))


def is_boss_stage(stage: StageId) -> bool:
    """Return True if the stage is a boss stage (number divisible by 10)."""
    return stage.number % _BOSS_EVERY == 0


@dataclass(frozen=True)
class FormationUnit:
    """One tatari of a formation and the cell it stands in (1-based)."""

    row: int
    col: int
    tatari_id: str
    evolution_id: str
    tier: int
    glitter: bool
    name: str = ""


@dataclass(frozen=True)
class Formation:
    """The prepared formation of a stage."""

    stage: StageId
    units: tuple[FormationUnit, ...]
    index: int = 0
    level: int | None = None


def _read_stage_file(root: Path, stage: StageId) -> dict | None:
    return _read_json(root / str(stage.chapter) / f"{stage}.json")


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_unit(raw: dict) -> FormationUnit:
    """Build a unit from its JSON; raises if a key is missing or a value is bad."""
    unit = FormationUnit(
        row=int(raw["row"]),
        col=int(raw["col"]),
        tatari_id=str(raw["tatari_id"]),
        evolution_id=str(raw["evolution_id"]),
        tier=int(raw["tier"]),
        glitter=bool(raw.get("glitter", False)),
        name=str(raw.get("name", "")),
    )
    if not (1 <= unit.row <= _FIELD_SIZE and 1 <= unit.col <= _FIELD_SIZE):
        raise ValueError(f"Cell ({unit.row}, {unit.col}) is outside the field.")
    return unit


def _parse_formations(
    raw_formations: list, stage: StageId, current: StageId
) -> tuple[Formation, ...]:
    """Build the usable formations; a malformed or empty one is skipped."""
    result: list[Formation] = []
    for raw in raw_formations:
        try:
            units = tuple(_parse_unit(u) for u in raw["units"])
            level = raw.get("level")
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            logging.warning(f"A formation of stage {current} is malformed: {error!r}")
            continue
        if not units:
            continue
        result.append(
            Formation(
                stage,
                units,
                index=len(result),
                level=level if isinstance(level, int) else None,
            )
        )
    return tuple(result)


def load_formations(root: Path, stage: StageId) -> tuple[Formation, ...]:
    """Load the formations of a stage, following "shared_with" links.

    Args:
        root: The tatari_formations folder.
        stage: The stage to load.

    Returns:
        The usable formations in file order (empty if the stage has none).
    """
    return _load_shared(lambda current: _read_stage_file(root, current), stage)


def load_dojo_formations(
    root: Path, element: str, stage: StageId
) -> tuple[Formation, ...]:
    """Load the formations of a Võ Đường stage, following "shared_with" links.

    Args:
        root: The tatari_dojo folder (one sub-folder per element).
        element: The element of the Võ Đường, for example "grass".
        stage: The stage to load, for example 4-2 (Võ Đường 4, stage 2).

    Returns:
        The usable formations in file order (empty if the stage has none).
    """
    return _load_shared(
        lambda current: _read_json(root / element / f"{current}.json"), stage
    )


def _load_shared(
    read: Callable[[StageId], dict | None], stage: StageId
) -> tuple[Formation, ...]:
    current = stage
    for _ in range(_MAX_SHARE_HOPS + 1):
        data = read(current)
        if data is None:
            logging.debug(f"No formation file for stage {current}.")
            return ()
        raw_formations = data.get("formations") or []
        if raw_formations:
            return _parse_formations(raw_formations, stage, current)
        target = parse_stage(str(data.get("shared_with", "")))
        if target is None or target == current:
            return ()
        current = target
    return ()
