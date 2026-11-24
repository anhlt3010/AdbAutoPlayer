"""Recognize which tatari a tray card shows.

A card is first looked up among the player's own templates (crops of cards that
were recognized before, one per evolution), which is fast. Only an unknown card
is recognized from the wiki sprites: the card art is the same drawing as the
sprite but cropped by the card and partly covered by the level text, the skill
icon and the stars on a coloured background. That matching compares the dark
outlines (independent of the background colour) of the card against the sprites
of the card's element, and only then uses colour to tell a normal sprite from its
glitter twin. The result is saved as a template for next time.
"""

import hashlib
import logging
from pathlib import Path

import cv2
import numpy as np
from adb_auto_player.games.clash_of_critters.battle_layout import (
    CARD_ART_BOX,
    ELEMENT_ICON_BOX,
)
from adb_auto_player.games.clash_of_critters.tatari_db import (
    ELEMENTS,
    Sprite,
    TatariDb,
)

# Fill colour (OpenCV hue 0-179, value 0-255) of the element icon of each element.
_ELEMENT_COLORS = {
    "rock": (15, 159),
    "lightning": (22, 250),
    "grass": (47, 197),
    "water": (106, 238),
    "fire": (173, 254),
}
_HUE_RANGE = 180
_MIN_ICON_SATURATION = 90
_MIN_ICON_VALUE = 80
_MIN_ICON_PIXELS = 200
_HUE_WEIGHT = 2.0
_VALUE_WEIGHT = 0.1
_MAX_ICON_DISTANCE = 15.0

# Art window of the card (rows) used for matching, and the skill-icon blob in its
# top-left corner that is blanked out.
_ART_TOP, _ART_BOTTOM = 44, 166
_SKILL_ICON_ROWS = (6, 60)
_SKILL_ICON_COLS = (0, 56)
_DARK_VALUE = 100
_SEARCH_SCALE = 0.5
# Colours only need a coarse picture; this is much faster than the outline search.
_COLOUR_SCALE = 0.25
# Long side of the sprite on a card, in full-resolution pixels. The art on a card
# is often larger than the card itself.
_SPRITE_SIZES = (110, 130, 150, 170, 190, 210, 240)
_ALPHA_MIN = 128
_FLAT_STD = 1e-3
_BGR_CHANNELS = 3
_GRAY_DIMENSIONS = 2
# Background removal for sprites without an alpha channel: how much neighbouring
# pixels may differ (per channel) while still counting as background.
_BACKGROUND_TOLERANCE = 14
_BACKGROUND_SEED_STEP = 4

# Player templates: the card art inset by _TEMPLATE_MARGIN pixels, searched inside
# the full art box so a card a few pixels off still matches.
_TEMPLATE_MARGIN = 5
_TEMPLATE_MIN_SCORE = 0.8
# A deployed card is dimmed and shows a big green check mark in its middle.
_CHECK_ROWS = (60, 150)
_CHECK_COLS = (30, 130)
_CHECK_HUE = (45, 75)
_CHECK_MIN_SATURATION = 120
_CHECK_MIN_VALUE = 150
_CHECK_MIN_FRACTION = 0.05
_DIMMED_MAX_ART_MEAN = 100

# Folders under the app config dir: the player's templates, and the crops of cards
# that were not recognized (one per card, waiting to be taught in the viewer).
TEMPLATE_DIR_NAME = "clash_of_critters_cards"
UNRECOGNIZED_DIR_NAME = "clash_of_critters_unrecognized"

_DEFAULT_THRESHOLD = 0.4
_DEFAULT_MARGIN = 0.05


def classify_element(icon_bgr: np.ndarray) -> str | None:
    """Tell the element from the colour of a card's element icon.

    Args:
        icon_bgr: The element icon region of a card (BGR).

    Returns:
        One of ELEMENTS, or None if the colour matches none of them.
    """
    hsv = cv2.cvtColor(icon_bgr, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    selected = hsv[(hsv[:, 1] > _MIN_ICON_SATURATION) & (hsv[:, 2] > _MIN_ICON_VALUE)]
    if len(selected) < _MIN_ICON_PIXELS:
        return None
    hue, _, value = np.median(selected, axis=0)
    best_name, best_distance = None, float("inf")
    for name, (ref_hue, ref_value) in _ELEMENT_COLORS.items():
        diff = abs(hue - ref_hue)
        diff = min(diff, _HUE_RANGE - diff)
        distance = diff * _HUE_WEIGHT + abs(value - ref_value) * _VALUE_WEIGHT
        if distance < best_distance:
            best_name, best_distance = name, distance
    return best_name if best_distance <= _MAX_ICON_DISTANCE else None


def is_deployed(card_bgr: np.ndarray) -> bool:
    """Tell whether a tray card is already on the field (dimmed, with a check).

    A green creature alone also shows green pixels, so the card must be dimmed too.

    Args:
        card_bgr: One tray card (BGR).

    Returns:
        True if the card is dimmed and shows the green check mark.
    """
    left, top, right, bottom = CARD_ART_BOX
    if float(card_bgr[top:bottom, left:right].mean()) >= _DIMMED_MAX_ART_MEAN:
        return False
    middle = card_bgr[_CHECK_ROWS[0] : _CHECK_ROWS[1], _CHECK_COLS[0] : _CHECK_COLS[1]]
    hsv = cv2.cvtColor(middle, cv2.COLOR_BGR2HSV)
    green = (
        (hsv[:, :, 0] > _CHECK_HUE[0])
        & (hsv[:, :, 0] < _CHECK_HUE[1])
        & (hsv[:, :, 1] > _CHECK_MIN_SATURATION)
        & (hsv[:, :, 2] > _CHECK_MIN_VALUE)
    )
    return float(green.mean()) >= _CHECK_MIN_FRACTION


def read_image(path: Path) -> np.ndarray | None:
    """Read a BGR image (also from a non-ASCII path), or None if unreadable.

    Args:
        path: The image file.

    Returns:
        The image, or None.
    """
    try:
        data = np.frombuffer(path.read_bytes(), np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def art_match_score(card_bgr: np.ndarray, other_card_bgr: np.ndarray) -> float:
    """Tell how well the art of one full card crop matches another.

    The template of ``other_card_bgr`` (as the template store cuts it) is searched
    in the art box of ``card_bgr``.

    Args:
        card_bgr: One tray card (BGR).
        other_card_bgr: Another tray card of the same size (BGR).

    Returns:
        The best normalized correlation, -1 to 1.
    """
    left, top, right, bottom = CARD_ART_BOX
    template = CardTemplateStore._template_of(other_card_bgr)
    scores = cv2.matchTemplate(
        card_bgr[top:bottom, left:right], template, cv2.TM_CCOEFF_NORMED
    )
    return _best(scores)


class CardTemplateStore:
    """The player's own card templates, one PNG per evolution.

    Files are ``<directory>/<element>/<evolution_id>.png``; each holds the art
    of a card that was recognized from the wiki sprites.
    """

    def __init__(self, directory: Path) -> None:
        """Create the store; templates are read from disk when first needed.

        Args:
            directory: Folder that holds one sub-folder per element.
        """
        self._directory = directory
        self._templates: dict[str, dict[str, np.ndarray]] = {}
        # Files (name, modification time) of each element folder when it was read;
        # another process (the formation viewer) may add or replace templates.
        self._signatures: dict[str, tuple[tuple[str, int], ...]] = {}

    def _signature(self, element: str) -> tuple[tuple[str, int], ...]:
        folder = self._directory / element
        if not folder.is_dir():
            return ()
        files = []
        for path in folder.glob("*.png"):
            try:
                files.append((path.name, path.stat().st_mtime_ns))
            except OSError:
                continue
        return tuple(sorted(files))

    @staticmethod
    def _template_of(card_bgr: np.ndarray) -> np.ndarray:
        left, top, right, bottom = CARD_ART_BOX
        margin = _TEMPLATE_MARGIN
        return card_bgr[top + margin : bottom - margin, left + margin : right - margin]

    def _of_element(self, element: str) -> dict[str, np.ndarray]:
        loaded = self._templates.get(element)
        if loaded is not None:
            return loaded
        loaded = {}
        self._signatures[element] = self._signature(element)
        folder = self._directory / element
        if folder.is_dir():
            for path in sorted(folder.glob("*.png")):
                image = read_image(path)
                if image is None:
                    logging.warning(f"Skipping unreadable card template {path}.")
                    continue
                loaded[path.stem] = image
        self._templates[element] = loaded
        return loaded

    def match(self, card_bgr: np.ndarray, element: str) -> str | None:
        """Find the stored template that a card matches.

        Args:
            card_bgr: One tray card (BGR).
            element: The element of the card; only its templates are compared.

        Returns:
            The evolution id of the best template scoring at least
            ``_TEMPLATE_MIN_SCORE``, or None.
        """
        found = self._best_template(card_bgr, element)
        if found is None and self._signature(element) != self._signatures.get(element):
            self._templates.pop(element, None)
            found = self._best_template(card_bgr, element)
        return found

    def _best_template(self, card_bgr: np.ndarray, element: str) -> str | None:
        left, top, right, bottom = CARD_ART_BOX
        search = card_bgr[top:bottom, left:right]
        best_id, best_score = None, _TEMPLATE_MIN_SCORE
        for evolution_id, template in self._of_element(element).items():
            scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
            score = float(np.nan_to_num(scores, nan=-1.0, posinf=-1.0).max())
            if score >= best_score:
                best_id, best_score = evolution_id, score
        return best_id

    def save(self, evolution_id: str, card_bgr: np.ndarray) -> None:
        """Store (or replace) the template of an evolution.

        Args:
            evolution_id: The recognized evolution id, such as "water-3-3".
            card_bgr: The card it was recognized from (BGR).
        """
        element = evolution_id.split("-", maxsplit=1)[0]
        templates = self._of_element(element)
        template = self._template_of(card_bgr).copy()
        templates[evolution_id] = template
        folder = self._directory / element
        folder.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".png", template)
        if ok:
            # The signature is left as loaded: another process may have written a
            # file meanwhile, so the next miss reloads the folder once.
            (folder / f"{evolution_id}.png").write_bytes(encoded.tobytes())


def _alpha_from_background(bgr: np.ndarray) -> np.ndarray:
    """Make an alpha mask for a sprite drawn on a plain-coloured background.

    The background is found by flooding inwards from the image border; the dark
    outline of the creature stops the flood.

    Args:
        bgr: The sprite (BGR) with its background.

    Returns:
        A uint8 mask, 0 for background and 255 for the creature.
    """
    height, width = bgr.shape[:2]
    mask = np.zeros((height + 2, width + 2), np.uint8)
    work = bgr.copy()
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    step = _BACKGROUND_SEED_STEP
    seeds = [(x, 0) for x in range(0, width, step)]
    seeds += [(x, height - 1) for x in range(0, width, step)]
    seeds += [(0, y) for y in range(0, height, step)]
    seeds += [(width - 1, y) for y in range(0, height, step)]
    tolerance = (_BACKGROUND_TOLERANCE,) * _BGR_CHANNELS
    for x, y in seeds:
        if mask[y + 1, x + 1] == 0:
            cv2.floodFill(work, mask, (x, y), (0, 0, 0), tolerance, tolerance, flags)
    return np.where(mask[1:-1, 1:-1] > 0, 0, 255).astype(np.uint8)


def _best(scores: np.ndarray) -> float:
    """Highest finite score of a template matching result."""
    return float(np.nan_to_num(scores, nan=-1.0, posinf=-1.0, neginf=-1.0).max())


def _dark_map(bgr: np.ndarray) -> np.ndarray:
    return (bgr.max(axis=2) < _DARK_VALUE).astype(np.float32)


class _Candidate:
    """Scores of one sprite on a card (best over the sprite sizes)."""

    def __init__(self, sprite: Sprite) -> None:
        self.sprite = sprite
        self.outline = -1.0
        self.colour = -1.0

    @property
    def score(self) -> float:
        """Mean of the outline score and the colour score."""
        return (self.outline + self.colour) / 2


class CardRecognizer:
    """Maps tray card images to ``tatari_db`` evolution ids."""

    def __init__(
        self,
        db: TatariDb,
        templates: CardTemplateStore,
        threshold: float = _DEFAULT_THRESHOLD,
        margin: float = _DEFAULT_MARGIN,
        debug_dir: Path | None = None,
    ) -> None:
        """Create a recognizer.

        Args:
            db: The tatari database.
            templates: The player's card templates; new ones are saved here.
            threshold: Minimum outline score of the best sprite.
            margin: Minimum lead of the best tatari over every other tatari.
            debug_dir: Where the crops of unrecognized cards are saved, if set.
        """
        self._db = db
        self._templates = templates
        self._threshold = threshold
        self._margin = margin
        self._debug_dir = debug_dir
        self._images: dict[str, np.ndarray | None] = {}

    def recognize(self, card_bgr: np.ndarray, element: str | None = None) -> str | None:
        """Recognize one tray card.

        Args:
            card_bgr: One tray card (BGR), as cut with ``card_box``.
            element: The element of the card when the caller knows it (the tray of
                a Võ Đường only holds one element). Without it the element is read
                from the colour of the icon, which a card whose background bleeds
                into the icon box can fool.

        Returns:
            The evolution id (glitter ids end in "g"), or None when the card is
            deployed or not recognized with enough confidence.
        """
        told_element = element
        if element is None:
            left, top, right, bottom = ELEMENT_ICON_BOX
            element = classify_element(card_bgr[top:bottom, left:right])
        if element not in ELEMENTS or is_deployed(card_bgr):
            return None

        known = self._templates.match(card_bgr, element)
        # A stray file in the template folder must not become an evolution id.
        if known is not None and self._db.get(known) is not None:
            return known
        result = self._match(card_bgr, element)
        if result is None:
            logging.debug(f"A {element} card was not recognized.")
            self._save_unrecognized(card_bgr, told_element)
            return None
        self._templates.save(result, card_bgr)
        return result

    def waiting_count(self) -> int:
        """Number of saved crops of unrecognized cards (0 without a folder)."""
        if self._debug_dir is None or not self._debug_dir.is_dir():
            return 0
        return sum(1 for _ in self._debug_dir.glob("*.png"))

    def _save_unrecognized(
        self, card_bgr: np.ndarray, element: str | None = None
    ) -> None:
        """Save the crop of an unrecognized card, unless that card is saved already.

        Args:
            card_bgr: The card crop.
            element: The element the caller told (a Võ Đường tray holds one element).
                It goes into the file name (``<element>_<hash>.png``) because the
                icon colour of such a card can read as another element.
        """
        if self._debug_dir is None:
            return
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        for path in self._debug_dir.glob("*.png"):
            saved = read_image(path)
            if saved is None or saved.shape != card_bgr.shape:
                continue
            if art_match_score(card_bgr, saved) >= _TEMPLATE_MIN_SCORE:
                self._name_with_element(path, element)
                return
        name = hashlib.sha1(card_bgr.tobytes()).hexdigest()[:12]
        if element in ELEMENTS:
            name = f"{element}_{name}"
        ok, encoded = cv2.imencode(".png", card_bgr)
        if ok:
            (self._debug_dir / f"{name}.png").write_bytes(encoded.tobytes())

    @staticmethod
    def _name_with_element(path: Path, element: str | None) -> None:
        """Give a saved crop without an element prefix the element the caller told.

        A crop saved before the prefix existed can have been listed under the wrong
        element (the icon colour of such a card is unreliable); seeing the same card
        again with its element known fixes the name once.
        """
        if element not in ELEMENTS or path.stem.split("_", 1)[0] in ELEMENTS:
            return
        try:
            path.rename(path.with_name(f"{element}_{path.name}"))
        except OSError as error:
            logging.debug(f"Could not rename the crop {path.name}: {error!r}")

    def _load(self, sprite: Sprite) -> np.ndarray | None:
        """Read a sprite as BGRA, or None if its file cannot be read."""
        if sprite.evolution_id in self._images:
            return self._images[sprite.evolution_id]
        image = cv2.imread(str(sprite.image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            logging.warning(f"Cannot read the sprite {sprite.image_path}, skipping it.")
        else:
            if image.ndim == _GRAY_DIMENSIONS:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            if image.shape[2] == _BGR_CHANNELS:  # no alpha channel
                image = np.dstack([image, _alpha_from_background(image)])
        self._images[sprite.evolution_id] = image
        return image

    def _match(self, card_bgr: np.ndarray, element: str | None) -> str | None:
        """Match the card against the sprites of one element."""
        region = card_bgr[_ART_TOP:_ART_BOTTOM]
        template = _dark_map(region)
        template[
            _SKILL_ICON_ROWS[0] : _SKILL_ICON_ROWS[1],
            _SKILL_ICON_COLS[0] : _SKILL_ICON_COLS[1],
        ] = 0
        size = (
            int(template.shape[1] * _SEARCH_SCALE),
            int(template.shape[0] * _SEARCH_SCALE),
        )
        template = cv2.resize(template, size, interpolation=cv2.INTER_AREA)
        if template.std() < _FLAT_STD:
            return None
        colour_size = (
            int(region.shape[1] * _COLOUR_SCALE),
            int(region.shape[0] * _COLOUR_SCALE),
        )
        region_colour = cv2.resize(region, colour_size, interpolation=cv2.INTER_AREA)

        candidates = [
            self._score(sprite, template, region_colour)
            for sprite in self._db.sprites_for_element(element or "")
        ]
        if not candidates:
            return None

        # Compare tatari (a normal sprite and its glitter twin count as one); the twin
        # has the same outline, so within the best tatari colour alone decides.
        families: dict[tuple[str, int], list[_Candidate]] = {}
        for candidate in candidates:
            sprite = candidate.sprite
            families.setdefault((sprite.tatari_id, sprite.tier), []).append(candidate)
        ranked = sorted(
            families.values(), key=lambda f: max(c.score for c in f), reverse=True
        )
        best = max(c.score for c in ranked[0])
        runner_up = max(c.score for c in ranked[1]) if len(ranked) > 1 else -1.0
        if best < self._threshold or best - runner_up < self._margin:
            return None
        return max(ranked[0], key=lambda c: c.colour).sprite.evolution_id

    def _score(
        self, sprite: Sprite, template: np.ndarray, region_colour: np.ndarray
    ) -> _Candidate:
        """Score a sprite on the card by outline and by colour."""
        candidate = _Candidate(sprite)
        image = self._load(sprite)
        if image is None:
            return candidate
        height, width = image.shape[:2]
        th, tw = template.shape
        for long_side in _SPRITE_SIZES:
            scale = long_side * _SEARCH_SCALE / max(height, width)
            resized = cv2.resize(
                image,
                (max(4, int(width * scale)), max(4, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
            alpha = resized[:, :, 3] >= _ALPHA_MIN

            outline = _dark_map(resized[:, :, :3]) * alpha
            padded = cv2.copyMakeBorder(
                outline,
                th // 2,
                th // 2,
                tw // 2,
                tw // 2,
                cv2.BORDER_CONSTANT,
                value=0,
            )
            scores = cv2.matchTemplate(padded, template, cv2.TM_CCOEFF_NORMED)
            candidate.outline = max(candidate.outline, _best(scores))

            # Colour: the sprite's own pixels against the card (the card background
            # is outside the sprite's mask), at a coarse scale. The art is often larger
            # than the card, so the card is padded by repeating its border.
            colour_scale = long_side * _COLOUR_SCALE / max(height, width)
            coarse = cv2.resize(
                image,
                (max(4, int(width * colour_scale)), max(4, int(height * colour_scale))),
                interpolation=cv2.INTER_AREA,
            )
            coarse_alpha = coarse[:, :, 3] >= _ALPHA_MIN
            sh, sw = coarse_alpha.shape
            card_padded = cv2.copyMakeBorder(
                region_colour, sh // 2, sh // 2, sw // 2, sw // 2, cv2.BORDER_REPLICATE
            )
            mask = cv2.merge([coarse_alpha.astype(np.uint8) * 255] * _BGR_CHANNELS)
            scores = cv2.matchTemplate(
                card_padded, coarse[:, :, :3], cv2.TM_CCOEFF_NORMED, mask=mask
            )
            candidate.colour = max(candidate.colour, _best(scores))
        return candidate
