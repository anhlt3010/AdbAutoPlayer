"""Clash of Critters stage ids and prepared formations."""

import json
import logging
import re
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


@dataclass(frozen=True)
class Formation:
    """The prepared formation of a stage."""

    stage: StageId
    units: tuple[FormationUnit, ...]


def _read_stage_file(root: Path, stage: StageId) -> dict | None:
    path = root / str(stage.chapter) / f"{stage}.json"
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
    )
    if not (1 <= unit.row <= _FIELD_SIZE and 1 <= unit.col <= _FIELD_SIZE):
        raise ValueError(f"Cell ({unit.row}, {unit.col}) is outside the field.")
    return unit


def load_formation(root: Path, stage: StageId) -> Formation | None:
    """Load the formation of a stage, following "shared_with" links.

    Args:
        root: The tatari_formations folder.
        stage: The stage to load.

    Returns:
        The formation, or None if there is no usable file for the stage.
    """
    current = stage
    for _ in range(_MAX_SHARE_HOPS + 1):
        data = _read_stage_file(root, current)
        if data is None:
            logging.debug(f"No formation file for stage {current}.")
            return None
        units = data.get("units") or []
        if units:
            try:
                parsed = tuple(_parse_unit(u) for u in units)
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                logging.warning(f"Formation of stage {current} is malformed: {error!r}")
                return None
            return Formation(stage, parsed)
        target = parse_stage(str(data.get("shared_with", "")))
        if target is None or target == current:
            return None
        current = target
    return None
