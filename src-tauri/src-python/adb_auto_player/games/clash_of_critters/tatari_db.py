"""Loader for the tatari database (wiki data and sprites)."""

import json
from dataclasses import dataclass
from pathlib import Path

ELEMENTS = ("fire", "water", "grass", "rock", "lightning")


@dataclass(frozen=True)
class Sprite:
    """One evolution (normal or glitter) with its wiki sprite."""

    evolution_id: str
    tatari_id: str
    element: str
    tier: int
    glitter: bool
    image_path: Path


class TatariDb:
    """The tatari database read from ``tatari_db.json``."""

    def __init__(self, sprites: list[Sprite]) -> None:
        """Index the given sprites by id and by element.

        Args:
            sprites: Every normal and glitter sprite of the database.
        """
        self._by_id = {sprite.evolution_id: sprite for sprite in sprites}
        self._by_element: dict[str, list[Sprite]] = {}
        for sprite in sprites:
            self._by_element.setdefault(sprite.element, []).append(sprite)

    @classmethod
    def load(cls, root: Path) -> "TatariDb":
        """Read ``root/tatari_db.json``.

        Args:
            root: The tatari_db folder (holds the json and ``images/``).

        Returns:
            The loaded database.
        """
        data = json.loads((root / "tatari_db.json").read_text(encoding="utf-8"))
        sprites: list[Sprite] = []
        for tatari in data["tataris"]:
            element = str(tatari["type"]).lower()
            for evolution in tatari["evolutions"]:
                for key, is_glitter in (("normal", False), ("glitter", True)):
                    entry = evolution.get(key)
                    if entry is None:
                        continue
                    sprites.append(
                        Sprite(
                            evolution_id=entry["id"],
                            tatari_id=tatari["tatari_id"],
                            element=element,
                            tier=int(evolution["stage"]),
                            glitter=is_glitter,
                            image_path=root / entry["image"],
                        )
                    )
        return cls(sprites)

    def sprites_for_element(self, element: str) -> list[Sprite]:
        """Return the sprites (normal and glitter) of one element."""
        return list(self._by_element.get(element, []))

    def get(self, evolution_id: str) -> Sprite | None:
        """Return the sprite of an evolution id, or None if unknown."""
        return self._by_id.get(evolution_id)
