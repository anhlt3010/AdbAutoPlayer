"""Clash of Critters formation viewer: the prepared formations of a stage for the UI.

The viewer window shows the formations of a stage (read from the device screen or
typed by the user) with the exact tier of every tatari. Nothing here sends input to
the device.
"""

import base64
import io
import logging
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from adb_auto_player.device.adb import AdbController
from adb_auto_player.file_loader import SettingsLoader
from adb_auto_player.game._screenshot_mixin import _ScreenshotMixin
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
    StageId,
    load_formations,
    parse_stage,
)
from adb_auto_player.games.clash_of_critters.tatari_db import TatariDb
from adb_auto_player.image_manipulation import IO
from adb_auto_player.ocr import RapidOCRBackend
from PIL import Image
from pydantic import BaseModel

FormationViewStatus = Literal[
    "ok", "no_device", "stage_unreadable", "stage_invalid", "no_formation"
]

# Longer side of a sprite sent to the UI, in pixels.
_SPRITE_MAX_SIDE = 96
_DATA_URI_PREFIX = "data:image/png;base64,"

_BASE_WIDTH, _BASE_HEIGHT = 1080, 1920
# Stage label at the top centre (left, top, right, bottom on 1080x1920). The fight
# screen label reaches x 555, so this is wider than the auto battle's own box.
VIEW_STAGE_BOX = (380, 25, 600, 95)


class ViewUnit(BaseModel):
    """One tatari of a formation as the viewer shows it."""

    row: int
    col: int
    tatari_id: str
    evolution_id: str
    name: str
    tier: int
    glitter: bool


class ViewFormation(BaseModel):
    """One prepared formation of a stage."""

    level: int | None
    units: list[ViewUnit]


class FormationViewResponse(BaseModel):
    """Answer of the formation viewer command."""

    status: FormationViewStatus
    stage: str | None
    formations: list[ViewFormation]
    # Sprite of each evolution_id used by the formations, sent once per evolution.
    sprites: dict[str, str]


@cache
def sprite_data_uri(path: Path) -> str | None:
    """Encode a sprite as a small PNG data URI.

    Args:
        path: The sprite image file.

    Returns:
        The data URI (alpha kept, longer side at most 96 px), or None if the file
        is missing or cannot be read.
    """
    try:
        with Image.open(path) as image:
            sprite = image.convert("RGBA")
    except (OSError, ValueError):
        return None
    sprite.thumbnail((_SPRITE_MAX_SIDE, _SPRITE_MAX_SIDE))
    buffer = io.BytesIO()
    sprite.save(buffer, format="PNG")
    return _DATA_URI_PREFIX + base64.b64encode(buffer.getvalue()).decode("ascii")


def _view_unit(unit: FormationUnit) -> ViewUnit:
    return ViewUnit(
        row=unit.row,
        col=unit.col,
        tatari_id=unit.tatari_id,
        evolution_id=unit.evolution_id,
        name=unit.name,
        tier=unit.tier,
        glitter=unit.glitter,
    )


def _collect_sprites(formations: tuple[Formation, ...], db: TatariDb) -> dict[str, str]:
    sprites: dict[str, str] = {}
    for formation in formations:
        for unit in formation.units:
            if unit.evolution_id in sprites:
                continue
            sprite = db.get(unit.evolution_id)
            uri = sprite_data_uri(sprite.image_path) if sprite is not None else None
            if uri is not None:
                sprites[unit.evolution_id] = uri
    return sprites


def build_response(
    stage: StageId, formations: tuple[Formation, ...], db: TatariDb
) -> FormationViewResponse:
    """Build the viewer answer for a stage.

    Args:
        stage: The stage the formations belong to.
        formations: The usable formations in file order.
        db: The tatari database the sprites come from.

    Returns:
        Status "ok" with every formation, or "no_formation" if there is none.
    """
    if not formations:
        return FormationViewResponse(
            status="no_formation", stage=str(stage), formations=[], sprites={}
        )
    return FormationViewResponse(
        status="ok",
        stage=str(stage),
        formations=[
            ViewFormation(
                level=formation.level,
                units=[_view_unit(unit) for unit in formation.units],
            )
            for formation in formations
        ],
        sprites=_collect_sprites(formations, db),
    )


@cache
def _ocr() -> RapidOCRBackend:
    """Create the OCR backend once; its models are slow to load."""
    return RapidOCRBackend()


def read_stage_from_screenshot(screenshot: np.ndarray) -> StageId | None:
    """Read the stage ("15-50") from the label at the top centre of the screen.

    Args:
        screenshot: BGR screenshot of any screen and any resolution (it is scaled
            to 1080x1920 first).

    Returns:
        The stage, or None if the screen shows no readable stage label.
    """
    # A screenshot of another size is scaled to 1080x1920. A device with another
    # aspect ratio is stretched, so the label can miss the box: that answers
    # "unreadable" (honest), never a wrong stage.
    if screenshot.shape[:2] != (_BASE_HEIGHT, _BASE_WIDTH):
        screenshot = cv2.resize(screenshot, (_BASE_WIDTH, _BASE_HEIGHT))
    left, top, right, bottom = VIEW_STAGE_BOX
    return parse_stage(_ocr().extract_text(screenshot[top:bottom, left:right]))


# Same as ClashOfCritters.package_name_prefixes (no Game object exists here).
_PACKAGE_NAME_PREFIXES = ["com.farlightgames.pgame.gp.vn"]
# Typed stages may use the dashes a phone keyboard or a pasted text brings.
_DASHES = str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"})
_GAME_FOLDER = "clash_of_critters"


def grab_screenshot() -> np.ndarray:
    """Take one screenshot of the device (no input is sent).

    Returns:
        BGR screenshot, shifted by the configured vertical offset like the one a
        running task sees.

    Raises:
        RuntimeError: The device did not answer with a PNG.
    """
    data = AdbController().screenshot(_PACKAGE_NAME_PREFIXES)
    if not isinstance(data, bytes):
        raise RuntimeError("The device did not return a screenshot.")
    return _ScreenshotMixin._apply_vertical_offset_to_screenshot(
        IO.get_bgr_np_array_from_png_bytes(data)
    )


@cache
def load_db(folder: Path) -> TatariDb:
    """Load the tatari database once per folder."""
    return TatariDb.load(folder)


def _empty(status: FormationViewStatus, stage: StageId | None) -> FormationViewResponse:
    return FormationViewResponse(
        status=status, stage=str(stage) if stage else None, formations=[], sprites={}
    )


def load_formation_view(
    stage_text: str | None,
    grab: Callable[[], np.ndarray] = grab_screenshot,
    data_root: Path | None = None,
) -> FormationViewResponse:
    """Find the prepared formations of a stage typed by the user or read from screen.

    Args:
        stage_text: A stage such as "15-50" typed by the user. None reads the stage
            from a screenshot instead.
        grab: Takes the screenshot; only called when stage_text is None.
        data_root: The clash_of_critters folder holding tatari_formations and
            tatari_db. Defaults to the one of the installed app.

    Returns:
        The formations, or a status telling why none can be shown.
    """
    root = data_root or SettingsLoader.games_dir() / _GAME_FOLDER
    if stage_text is not None:
        stage = parse_stage(stage_text.translate(_DASHES))
        if stage is None:
            return _empty("stage_invalid", None)
    else:
        try:
            screenshot = grab()
        except Exception as error:
            logging.debug(f"Formation viewer could not take a screenshot: {error!r}")
            return _empty("no_device", None)
        stage = read_stage_from_screenshot(screenshot)
        if stage is None:
            return _empty("stage_unreadable", None)
    formations = load_formations(root / "tatari_formations", stage)
    return build_response(stage, formations, load_db(root / "tatari_db"))
