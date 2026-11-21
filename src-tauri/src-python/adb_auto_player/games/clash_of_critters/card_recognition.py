"""Recognize which tatari a tray card shows, by matching the wiki sprites.

The card art is the same drawing as the wiki sprite, but cropped by the card and
partly covered by the level text, the skill icon and the stars on a coloured
background. Matching therefore compares the dark outlines (independent of the
background colour) of the card against the sprites of the card's element, and
only then uses colour to tell a normal sprite from its glitter twin.
"""

import hashlib
import json
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
# Long side of the sprite on a card, in full-resolution pixels. The art on a card
# is often larger than the card itself.
_SPRITE_SIZES = (110, 130, 150, 170, 190, 210, 240)
_ALPHA_MIN = 128
_HASH_SIZE = 8
_FLAT_STD = 1e-3
_BGR_CHANNELS = 3

_DEFAULT_THRESHOLD = 0.35
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


def card_art_key(card_bgr: np.ndarray) -> str:
    """Return a short stable key (average hash) of a card's art.

    Args:
        card_bgr: One tray card (BGR).

    Returns:
        A hex string that is equal for identical crops of the same card.
    """
    left, top, right, bottom = CARD_ART_BOX
    gray = cv2.cvtColor(card_bgr[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (_HASH_SIZE, _HASH_SIZE), interpolation=cv2.INTER_AREA)
    bits = (small > small.mean()).astype(np.uint8).tobytes()
    return hashlib.sha1(bits).hexdigest()[:16]


class RecognitionCache:
    """JSON file mapping card art keys to evolution ids."""

    def __init__(self, path: Path) -> None:
        """Load the cache; a missing or corrupt file gives an empty cache.

        Args:
            path: The JSON file.
        """
        self._path = path
        self._data: dict[str, str] = {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data = {str(k): str(v) for k, v in loaded.items()}
        except (OSError, ValueError):
            pass

    def get(self, key: str) -> str | None:
        """Return the evolution id stored for a key, or None."""
        return self._data.get(key)

    def put(self, key: str, evolution_id: str) -> None:
        """Store an evolution id for a key."""
        self._data[key] = evolution_id

    def save(self) -> None:
        """Write the cache to its file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=1), encoding="utf-8")


def _dark_map(bgr: np.ndarray) -> np.ndarray:
    return (bgr.max(axis=2) < _DARK_VALUE).astype(np.float32)


class _Candidate:
    """Best alignment of one sprite on the card."""

    def __init__(self, sprite: Sprite) -> None:
        self.sprite = sprite
        self.score = -1.0
        self.sprite_bgr: np.ndarray | None = None
        self.sprite_alpha: np.ndarray | None = None
        self.offset = (0, 0)  # sprite (0, 0) in template coordinates


class CardRecognizer:
    """Maps tray card images to ``tatari_db`` evolution ids."""

    def __init__(
        self,
        db: TatariDb,
        cache: RecognitionCache,
        threshold: float = _DEFAULT_THRESHOLD,
        margin: float = _DEFAULT_MARGIN,
        debug_dir: Path | None = None,
    ) -> None:
        """Create a recognizer.

        Args:
            db: The tatari database.
            cache: Cache of earlier results (the caller saves it).
            threshold: Minimum outline score of the best sprite.
            margin: Minimum lead of the best tatari over every other tatari.
            debug_dir: Where the crops of unrecognized cards are saved, if set.
        """
        self._db = db
        self._cache = cache
        self._threshold = threshold
        self._margin = margin
        self._debug_dir = debug_dir
        self._images: dict[str, np.ndarray] = {}

    def recognize(self, card_bgr: np.ndarray) -> str | None:
        """Recognize one tray card.

        Args:
            card_bgr: One tray card (BGR), as cut with ``card_box``.

        Returns:
            The evolution id (glitter ids end in "g"), or None when the card is
            not recognized with enough confidence.
        """
        key = card_art_key(card_bgr)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        left, top, right, bottom = ELEMENT_ICON_BOX
        element = classify_element(card_bgr[top:bottom, left:right])
        result = self._match(card_bgr, element) if element in ELEMENTS else None
        if result is None:
            logging.debug(f"Card {key} not recognized (element {element}).")
            if self._debug_dir is not None:
                self._debug_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(self._debug_dir / f"{key}.png"), card_bgr)
            return None
        self._cache.put(key, result)
        return result

    def _load(self, sprite: Sprite) -> np.ndarray:
        image = self._images.get(sprite.evolution_id)
        if image is None:
            image = cv2.imread(str(sprite.image_path), cv2.IMREAD_UNCHANGED)
            if (
                image.shape[2] == _BGR_CHANNELS
            ):  # no alpha channel: use the whole rectangle
                alpha = np.full(image.shape[:2], 255, np.uint8)
                image = np.dstack([image, alpha])
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
        region_small = cv2.resize(region, size, interpolation=cv2.INTER_AREA)

        candidates = [
            self._align(sprite, template, region_small)
            for sprite in self._db.sprites_for_element(element or "")
        ]
        if not candidates:
            return None

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
        twins = ranked[0]
        if len(twins) == 1:
            return twins[0].sprite.evolution_id
        return min(
            twins, key=lambda c: self._color_error(c, region_small)
        ).sprite.evolution_id

    def _align(
        self, sprite: Sprite, template: np.ndarray, region_small: np.ndarray
    ) -> _Candidate:
        """Find the best size and position of a sprite on the card."""
        candidate = _Candidate(sprite)
        image = self._load(sprite)
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
            scores[~np.isfinite(scores)] = -1.0
            y, x = np.unravel_index(int(scores.argmax()), scores.shape)
            score = float(scores[y, x])
            if score > candidate.score:
                candidate.score = score
                candidate.sprite_bgr = resized[:, :, :3]
                candidate.sprite_alpha = alpha
                candidate.offset = (tw // 2 - int(x), th // 2 - int(y))
        return candidate

    @staticmethod
    def _color_error(candidate: _Candidate, region_small: np.ndarray) -> float:
        """Mean colour difference between a sprite and the card at its alignment."""
        if candidate.sprite_bgr is None or candidate.sprite_alpha is None:
            return float("inf")
        ox, oy = candidate.offset
        sh, sw = candidate.sprite_alpha.shape
        rh, rw = region_small.shape[:2]
        x0, y0 = max(ox, 0), max(oy, 0)
        x1, y1 = min(ox + sw, rw), min(oy + sh, rh)
        if x1 <= x0 or y1 <= y0:
            return float("inf")
        sprite_part = candidate.sprite_bgr[y0 - oy : y1 - oy, x0 - ox : x1 - ox]
        card_part = region_small[y0:y1, x0:x1]
        valid = candidate.sprite_alpha[y0 - oy : y1 - oy, x0 - ox : x1 - ox]
        if not valid.any():
            return float("inf")
        diff = np.abs(sprite_part.astype(np.int16) - card_part.astype(np.int16))
        return float(diff[valid].mean())
