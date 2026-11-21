"""Tray scanning and formation deployment on the battle preparation screen."""

import logging
import re
from time import sleep

import numpy as np
from adb_auto_player.file_loader import SettingsLoader
from adb_auto_player.game import Game
from adb_auto_player.games.clash_of_critters.battle_layout import (
    ALL_FILTER_POINT,
    CLEAR_FIELD_POINT,
    COUNTER_BOX,
    ELEMENT_FILTER_POINTS,
    MAX_DEPLOYED,
    CARD_SIZE,
    TRAY_BOX,
    TRAY_ROWS_Y,
    card_box,
    cell_center,
    find_card_lefts,
)
from adb_auto_player.games.clash_of_critters.card_recognition import (
    CardRecognizer,
    RecognitionCache,
)
from adb_auto_player.games.clash_of_critters.deployment_plan import plan_deployment
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
)
from adb_auto_player.games.clash_of_critters.tatari_db import TatariDb
from adb_auto_player.models.geometry import Point
from adb_auto_player.ocr import RapidOCRBackend

_CACHE_FILE_NAME = "clash_of_critters_cards.json"
_DRAG_SECONDS = 0.6
# Measured on the emulator: a dropped card is settled well within a second.
_DRAG_SETTLE_SECONDS = 1.0
_SCROLL_SECONDS = 1.5
_CLEAR_SETTLE_SECONDS = 1.0
# After a swipe the tray keeps gliding for about 1.5 s. Cards are only read once two
# frames, _STABLE_POLL_SECONDS apart, differ by no more than _STABLE_MAX_DIFF (mean
# pixel difference of the tray), for at most _STABLE_MAX_POLLS polls.
_STABLE_POLL_SECONDS = 0.5
_STABLE_MAX_POLLS = 8
_STABLE_MAX_DIFF = 0.3
# Swipe along the gap between the two tray rows; forward reveals cards on the right.
# The tray keeps moving after the finger lifts (about 1.25x the swipe), so a page
# still overlaps the previous one.
_SCROLL_Y = 1383
_SCROLL_FROM_X, _SCROLL_TO_X = 900, 400
# Mean absolute pixel difference of the tray that counts as "the tray moved".
_TRAY_MOVED_MIN_DIFF = 3.0
_COUNTER_PATTERN = re.compile(r"(\d+)\s*/\s*\d+")


class DeployMixin(Game):
    """Reads the tray of owned tatari and deploys formations by drag and drop."""

    _recognizer: CardRecognizer | None = None
    _recognition_cache: RecognitionCache | None = None

    def _get_recognizer(self) -> CardRecognizer:
        if self._recognizer is None:
            data_root = self.template_dir.parent / "tatari_db"
            cache_path = SettingsLoader.get_app_config_dir() / _CACHE_FILE_NAME
            self._recognition_cache = RecognitionCache(cache_path)
            self._recognizer = CardRecognizer(
                TatariDb.load(data_root),
                self._recognition_cache,
                debug_dir=cache_path.parent / "clash_of_critters_unrecognized",
            )
        return self._recognizer

    def _visible_cards(self) -> list[tuple[Point, str | None]]:
        """Recognize the tray cards that are on screen.

        Returns:
            The centre of each whole card on screen with its evolution id, or
            None for a card that is not recognized.
        """
        screenshot = self.get_screenshot()
        recognizer = self._get_recognizer()
        lefts = find_card_lefts(screenshot)
        cards: list[tuple[Point, str | None]] = []
        for row_y in TRAY_ROWS_Y:
            for card_left in lefts:
                center = Point(card_left + CARD_SIZE[0] // 2, row_y)
                left, top, right, bottom = card_box(center)
                cards.append(
                    (center, recognizer.recognize(screenshot[top:bottom, left:right]))
                )
        if self._recognition_cache is not None:
            self._recognition_cache.save()
        return cards

    def _wait_tray_stable(self) -> np.ndarray:
        """Wait until the tray has stopped moving.

        Returns:
            The first screenshot whose tray equals the one before it (or the last
            one taken if the tray never settles within the time limit).
        """
        left, top, right, bottom = TRAY_BOX
        previous = self.get_screenshot()
        for _ in range(_STABLE_MAX_POLLS):
            sleep(_STABLE_POLL_SECONDS)
            current = self.get_screenshot()
            diff = np.abs(
                current[top:bottom, left:right].astype(np.int16)
                - previous[top:bottom, left:right].astype(np.int16)
            ).mean()
            if float(diff) <= _STABLE_MAX_DIFF:
                return current
            previous = current
        logging.warning("The tray did not stop moving, continuing anyway.")
        return previous

    def _scroll_tray(self, forward: bool) -> bool:
        """Swipe the tray one step.

        Args:
            forward: True to reveal the cards on the right, False to go back.

        Returns:
            False if the tray did not move (it is at that end).
        """
        left, top, right, bottom = TRAY_BOX
        before = self.get_screenshot()[top:bottom, left:right].astype(np.int16)
        start_x, end_x = (
            (_SCROLL_FROM_X, _SCROLL_TO_X)
            if forward
            else (_SCROLL_TO_X, _SCROLL_FROM_X)
        )
        self.device.swipe(
            self._apply_vertical_offset(Point(start_x, _SCROLL_Y)),
            self._apply_vertical_offset(Point(end_x, _SCROLL_Y)),
            duration=_SCROLL_SECONDS,
        )
        after = self._wait_tray_stable()[top:bottom, left:right].astype(np.int16)
        return float(np.abs(after - before).mean()) > _TRAY_MOVED_MIN_DIFF

    def _scroll_tray_to_start(self) -> None:
        while self._scroll_tray(False):
            pass

    def _scan_owned(self) -> set[str]:
        """Walk the whole tray and collect the evolution ids of the owned cards.

        Returns:
            The recognized evolution ids. The tray is left at its start.
        """
        self._scroll_tray_to_start()
        owned: set[str] = set()
        while True:
            owned.update(
                evolution_id
                for _, evolution_id in self._visible_cards()
                if evolution_id is not None
            )
            if not self._scroll_tray(True):
                break
        self._scroll_tray_to_start()
        logging.info(f"Recognized {len(owned)} owned tatari in the tray.")
        return owned

    def _locate_card(self, evolution_id: str) -> Point | None:
        """Scroll the tray until the card of an evolution is on screen.

        Args:
            evolution_id: The wanted evolution id.

        Returns:
            The centre of the card, or None if it is not in the tray.
        """
        for attempt in range(2):
            if attempt == 1:
                self._scroll_tray_to_start()
            while True:
                for center, found in self._visible_cards():
                    if found == evolution_id:
                        return center
                if not self._scroll_tray(True):
                    break
        return None

    def _drag_card(self, card: Point, cell: Point) -> None:
        """Drag a tray card onto a field cell."""
        self.device.swipe(
            self._apply_vertical_offset(card),
            self._apply_vertical_offset(cell),
            duration=_DRAG_SECONDS,
        )
        sleep(_DRAG_SETTLE_SECONDS)

    def _read_deployed_count(self) -> int | None:
        """Read n from the "Đã triển khai: n/15" counter, or None if unreadable."""
        left, top, right, bottom = COUNTER_BOX
        crop = self.get_screenshot()[top:bottom, left:right]
        text = RapidOCRBackend().extract_text(crop)
        match = _COUNTER_PATTERN.search(text)
        return int(match.group(1)) if match else None

    def _select_element(self, element: str | None) -> None:
        """Show only the tray cards of one element (None shows all)."""
        point = ALL_FILTER_POINT if element is None else ELEMENT_FILTER_POINTS[element]
        self.tap(point, log=False)
        self._wait_tray_stable()

    def _deploy_formation(self, formation: Formation) -> int:
        """Clear the field and deploy a formation one element at a time.

        For each element of the formation the tray is filtered to that element
        (a short tray, so little scrolling and few cards to recognize), its
        tatari are dragged to their cells, then the next element follows.

        Args:
            formation: The formation to deploy.

        Returns:
            The number of tatari on the field afterwards (0 if none could be
            placed).
        """
        self.tap(CLEAR_FIELD_POINT, log=False)
        sleep(_CLEAR_SETTLE_SECONDS)
        count = self._read_deployed_count()
        if count not in (0, None):
            logging.warning(
                f"Field not empty after clearing ({count}), clearing again."
            )
            self.tap(CLEAR_FIELD_POINT, log=False)
            sleep(_CLEAR_SETTLE_SECONDS)

        by_element: dict[str, list[FormationUnit]] = {}
        for unit in formation.units[:MAX_DEPLOYED]:
            by_element.setdefault(unit.tatari_id.split("-")[0], []).append(unit)

        dragged = 0
        for element, units in by_element.items():
            self._select_element(element)
            placements = plan_deployment(
                Formation(formation.stage, tuple(units)),
                self._scan_owned(),
                MAX_DEPLOYED,
            )
            for placement in placements:
                if placement.evolution_id is None:
                    continue
                card = self._locate_card(placement.evolution_id)
                if card is None:
                    logging.warning(f"{placement.evolution_id} not found in the tray.")
                    continue
                self._drag_card(
                    card, cell_center(placement.unit.row, placement.unit.col)
                )
                dragged += 1
        self._select_element(None)

        count = self._read_deployed_count()
        logging.info(
            f"Deployed {count if count is not None else dragged} of "
            f"{len(formation.units)} formation units."
        )
        return count if count is not None else dragged
