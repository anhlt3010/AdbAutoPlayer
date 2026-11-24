"""Teach the bot tray cards it did not recognize.

The auto battle saves one crop per unrecognized card in the unrecognized folder.
The formation viewer lists them with the wiki sprites of their element, and the
user picks the right evolution; the crop then becomes a player template.
"""

import base64
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from adb_auto_player.games.clash_of_critters.battle_layout import ELEMENT_ICON_BOX
from adb_auto_player.games.clash_of_critters.card_recognition import (
    TEMPLATE_DIR_NAME,
    UNRECOGNIZED_DIR_NAME,
    CardTemplateStore,
    art_match_score,
    classify_element,
    read_image,
)
from adb_auto_player.games.clash_of_critters.formation_view import sprite_data_uri
from adb_auto_player.games.clash_of_critters.tatari_db import (
    ELEMENTS,
    Sprite,
    TatariDb,
)
from pydantic import BaseModel

TeachStatus = Literal["ok", "unknown_crop", "unknown_evolution", "wrong_element"]

# Same bar as a player template: a crop this close is the same card.
_SAME_CARD_SCORE = 0.8
_DATA_URI_PREFIX = "data:image/png;base64,"


class WaitingCard(BaseModel):
    """A saved crop of a card that was not recognized."""

    id: str
    element: str
    image: str


class CardChoice(BaseModel):
    """One evolution the user can pick for a card."""

    evolution_id: str
    tatari_id: str
    tier: int
    glitter: bool
    sprite: str | None


class WaitingCardsResponse(BaseModel):
    """The waiting cards and the picker data of their elements."""

    cards: list[WaitingCard]
    choices: dict[str, list[CardChoice]]


def _crops(config_dir: Path) -> dict[str, tuple[np.ndarray, str]]:
    """Readable crops with a known element, by file stem."""
    folder = config_dir / UNRECOGNIZED_DIR_NAME
    if not folder.is_dir():
        return {}
    left, top, right, bottom = ELEMENT_ICON_BOX
    crops: dict[str, tuple[np.ndarray, str]] = {}
    for path in sorted(folder.glob("*.png")):
        image = read_image(path)
        if image is None:
            continue
        # A crop saved with a known element (Võ Đường) carries it in its name.
        prefix = path.stem.split("_", 1)[0]
        element = (
            prefix
            if "_" in path.stem and prefix in ELEMENTS
            else classify_element(image[top:bottom, left:right])
        )
        if element is not None:
            crops[path.stem] = (image, element)
    return crops


def _image_uri(image: np.ndarray) -> str:
    _, encoded = cv2.imencode(".png", image)  # a decoded image always encodes
    return _DATA_URI_PREFIX + base64.b64encode(encoded.tobytes()).decode("ascii")


def _tatari_number(sprite: Sprite) -> int:
    number = sprite.tatari_id.rsplit("-", 1)[-1]
    return int(number) if number.isdigit() else 0


def _choices(db: TatariDb, element: str) -> list[CardChoice]:
    sprites = sorted(
        db.sprites_for_element(element),
        key=lambda s: (_tatari_number(s), s.tatari_id, s.glitter, s.tier),
    )
    return [
        CardChoice(
            evolution_id=s.evolution_id,
            tatari_id=s.tatari_id,
            tier=s.tier,
            glitter=s.glitter,
            sprite=sprite_data_uri(s.image_path),
        )
        for s in sprites
    ]


def load_waiting_cards(config_dir: Path, db: TatariDb) -> WaitingCardsResponse:
    """List the unrecognized cards and the evolutions they can be taught as.

    Args:
        config_dir: The app config dir of the profile.
        db: The tatari database.

    Returns:
        The cards, and the picker choices of each element that has a card.
    """
    crops = _crops(config_dir)
    cards = [
        WaitingCard(id=crop_id, element=element, image=_image_uri(image))
        for crop_id, (image, element) in crops.items()
    ]
    elements = sorted({card.element for card in cards})
    return WaitingCardsResponse(
        cards=cards, choices={element: _choices(db, element) for element in elements}
    )


def teach_card(
    config_dir: Path, db: TatariDb, crop_id: str, evolution_id: str
) -> TeachStatus:
    """Save a waiting card as the template of an evolution.

    The crop and every other waiting crop of the same card are removed.

    Args:
        config_dir: The app config dir of the profile.
        db: The tatari database.
        crop_id: The file stem of the crop, as listed by load_waiting_cards.
        evolution_id: The evolution the user picked, such as "fire-8-2".

    Returns:
        "ok", or why nothing was saved.
    """
    crops = _crops(config_dir)
    # Only listed stems are accepted, so crop_id never becomes a path.
    if crop_id not in crops:
        return "unknown_crop"
    sprite = db.get(evolution_id)
    if sprite is None:
        return "unknown_evolution"
    image, element = crops[crop_id]
    if sprite.element != element:
        return "wrong_element"
    CardTemplateStore(config_dir / TEMPLATE_DIR_NAME).save(evolution_id, image)
    folder = config_dir / UNRECOGNIZED_DIR_NAME
    for other_id, (other, _) in crops.items():
        same = other_id == crop_id or (
            other.shape == image.shape
            and art_match_score(other, image) >= _SAME_CARD_SCORE
        )
        if same:
            (folder / f"{other_id}.png").unlink(missing_ok=True)
    return "ok"
