"""Map the tatari ids of the formation files to the game's own species ids (``tid``).

A formation file names a species as ``<element>-<n>`` (for example ``rock-5``). In the
game it is the n-th species of that element by ascending ``tid`` (14 per element), see
``data/tatari_to_tid.json``. ``tid`` does not change when a tatari evolves.

Two ways to fix a wrong or missing entry, both without touching the code:
* ``set_override(...)`` / the override file, edited by the player (wins over everything);
* ``rebuild_mapping(...)``, which regenerates the base file from the species list of
  the game (needed only after a game update adds species).
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import UnknownTatari

_DATA = Path(__file__).resolve().parent / "data" / "tatari_to_tid.json"
# Game ``UnitElement`` codes.
ELEMENTS = {2: "water", 3: "fire", 4: "grass", 5: "lightning", 6: "rock"}


class TatariMap:
    """``tatari_id -> tid`` with a player override file."""

    def __init__(
        self, base_file: Path = _DATA, override_file: Path | None = None
    ) -> None:
        self.base_file = Path(base_file)
        self.override_file = (
            Path(override_file)
            if override_file
            else self.base_file.with_name("tatari_to_tid.override.json")
        )
        self.reload()

    def reload(self) -> None:
        self._base: dict[str, int] = json.loads(
            self.base_file.read_text(encoding="utf-8")
        )
        self._override: dict[str, int] = {}
        if self.override_file.exists():
            self._override = {
                k: int(v)
                for k, v in json.loads(
                    self.override_file.read_text(encoding="utf-8")
                ).items()
            }

    def tid(self, tatari_id: str) -> int:
        """Game species id of a tatari id such as ``"rock-5"``."""
        value = self._override.get(tatari_id, self._base.get(tatari_id))
        if value is None:
            raise UnknownTatari(
                f"no game species id for {tatari_id!r}; add it to {self.override_file.name}"
            )
        return int(value)

    def set_override(self, tatari_id: str, tid: int) -> None:
        """Remember a manual mapping (persisted in the override file)."""
        self._override[tatari_id] = int(tid)
        self.override_file.write_text(
            json.dumps(self._override, indent=1, sort_keys=True), encoding="utf-8"
        )

    def clear_override(self, tatari_id: str) -> None:
        self._override.pop(tatari_id, None)
        self.override_file.write_text(
            json.dumps(self._override, indent=1, sort_keys=True), encoding="utf-8"
        )

    def items(self) -> dict[str, int]:
        """The effective mapping (base plus overrides)."""
        return {**self._base, **self._override}


def build_rank_mapping(species: dict[int, int]) -> dict[str, int]:
    """Apply the rank rule to ``{tid: UnitElement}`` read from the game."""
    by_element: dict[str, list[int]] = {}
    for tid in sorted(species):
        by_element.setdefault(ELEMENTS[species[tid]], []).append(tid)
    return {
        f"{element}-{n}": tid
        for element, tids in by_element.items()
        for n, tid in enumerate(tids, 1)
    }


def rebuild_mapping(species: dict[int, int], target: Path = _DATA) -> dict[str, int]:
    """Regenerate the base mapping file from ``{tid: UnitElement}`` read from the game.

    The species list comes from the game's ``petConfig`` of each owned pet (see the
    README, "After a game update").
    """
    mapping = build_rank_mapping(species)
    Path(target).write_text(
        json.dumps(mapping, indent=1, sort_keys=True), encoding="utf-8"
    )
    return mapping
