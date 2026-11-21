"""Clash of Critters stage ids and prepared formations."""

import re
from dataclasses import dataclass

_BOSS_EVERY = 10
# A stage like "15-50"; digits must not touch other digits or letters, so an OCR
# misread such as "15-5O" is rejected instead of read as "15-5".
_STAGE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*-\s*(\d{1,3})(?![\dA-Za-z])")


@dataclass(frozen=True)
class StageId:
    """A stage of the campaign, for example 15-50."""

    chapter: int
    number: int

    def __str__(self) -> str:
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
