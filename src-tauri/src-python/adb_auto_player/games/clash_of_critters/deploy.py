"""Tray scanning and formation deployment on the battle preparation screen."""

import logging
import re
from dataclasses import dataclass
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
    cell_at,
    find_card_lefts,
    plan_drag,
)
from adb_auto_player.games.clash_of_critters.card_recognition import (
    TEMPLATE_DIR_NAME,
    UNRECOGNIZED_DIR_NAME,
    CardRecognizer,
    CardTemplateStore,
)
from adb_auto_player.games.clash_of_critters.deployment_plan import plan_deployment
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    FormationUnit,
)
from adb_auto_player.games.clash_of_critters.tatari_db import TatariDb
from adb_auto_player.models.geometry import Point
from adb_auto_player.ocr import RapidOCRBackend

_DRAG_SECONDS = 0.6
# A drag is checked against the deployed counter and repeated once if it failed.
_DRAG_ATTEMPTS = 2
# A unit moved inside the field is seen by the target cell changing on screen
# (mean pixel difference of a square of 2 * _CELL_HALF_SIZE around its centre).
_CELL_HALF_SIZE = 40
_CELL_CHANGE_MIN_DIFF = 10.0
# Measured on the emulator: a dropped card is settled well within a second.
_DRAG_SETTLE_SECONDS = 1.0
_SCROLL_SECONDS = 1.5
_CLEAR_SETTLE_SECONDS = 1.0
# After a swipe the tray keeps gliding for about 1.5 s. Cards are only read once two
# frames, auto_battle.tray_settle_poll_seconds apart, differ by no more than
# _STABLE_MAX_DIFF (mean pixel difference of the tray), for at most _STABLE_MAX_POLLS
# polls.
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
# Rounds that try again the units that could not be placed (the field is not cleared).
_FILL_ATTEMPTS = 5


@dataclass(frozen=True)
class DeployResult:
    """What a deployment left on the field.

    Attributes:
        count: Tatari on the field (the counter, or the number placed if the
            counter cannot be read).
        needed: Cells of the formation that have an owned tatari to put on them.
    """

    count: int
    needed: int

    @property
    def complete(self) -> bool:
        """Whether every cell that could be filled has a tatari."""
        return self.count >= self.needed


class DeployMixin(Game):
    """Reads the tray of owned tatari and deploys formations by drag and drop."""

    _recognizer: CardRecognizer | None = None
    # Last value read from the deployed counter (None if unknown or unreadable).
    _deployed_count: int | None = None
    # Cells of the field that hold a unit (set while a formation is deployed).
    _occupied: set[tuple[int, int]] | None = None

    def _get_recognizer(self) -> CardRecognizer:
        if self._recognizer is None:
            data_root = self.template_dir.parent / "tatari_db"
            config_dir = SettingsLoader.get_app_config_dir()
            self._recognizer = CardRecognizer(
                TatariDb.load(data_root),
                CardTemplateStore(config_dir / TEMPLATE_DIR_NAME),
                debug_dir=config_dir / UNRECOGNIZED_DIR_NAME,
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
        return cards

    def _wait_tray_stable(self) -> np.ndarray:
        """Wait until the tray has stopped moving.

        Returns:
            The first screenshot whose tray equals the one before it (or the last
            one taken if the tray never settles within the time limit).
        """
        left, top, right, bottom = TRAY_BOX
        previous = self.get_screenshot()
        poll_seconds = self.settings.auto_battle.tray_settle_poll_seconds
        for _ in range(_STABLE_MAX_POLLS):
            sleep(poll_seconds)
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
            The recognized evolution ids. The tray is left at its end, so the
            cards can then be picked while walking back to the start.
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
        logging.debug(f"Recognized {len(owned)} owned tatari in the tray.")
        return owned

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

    def _find_card(self, evolution_id: str) -> Point | None:
        """Find a card on the visible part of the tray (None if it is not there)."""
        for card, found in self._visible_cards():
            if found == evolution_id:
                return card
        return None

    def _field_move(self, source: Point, target: Point) -> bool:
        """Move a unit inside the field and check that it arrived.

        A move that did not register is repeated once.

        Args:
            source: The centre of the unit's current cell.
            target: The centre of the cell to move it to.

        Returns:
            False if the target cell did not change on screen.
        """
        for _ in range(_DRAG_ATTEMPTS):
            before = self.get_screenshot()
            self._drag_card(source, target)
            after = self.get_screenshot()
            top, bottom = target.y - _CELL_HALF_SIZE, target.y + _CELL_HALF_SIZE
            left, right = target.x - _CELL_HALF_SIZE, target.x + _CELL_HALF_SIZE
            diff = np.abs(
                after[top:bottom, left:right].astype(np.int16)
                - before[top:bottom, left:right].astype(np.int16)
            ).mean()
            if float(diff) > _CELL_CHANGE_MIN_DIFF:
                return True
            logging.warning("The unit did not move, trying again.")
        return False

    def _place_card(self, card: Point, row: int, col: int, evolution_id: str) -> bool:
        """Put a tray card on a cell and check that the field really got one more.

        A drag that did not register is repeated once, after finding the card on
        screen again (a failed drag may have scrolled the tray). A drag that would
        be too sideways for the tray goes through an intermediate cell.

        Args:
            card: The centre of the card in the tray.
            row: Target row 1-5.
            col: Target column 1-5.
            evolution_id: The card's evolution id, to find it again.

        Returns:
            False if the unit could not be put on its cell.
        """
        occupied = self._occupied if self._occupied is not None else set()
        for attempt in range(_DRAG_ATTEMPTS):
            path = plan_drag(card, row, col, occupied)
            before = self._deployed_count
            self._drag_card(card, path[1])
            after = self._read_deployed_count()
            self._deployed_count = after
            logging.debug(
                f"Dragged card at ({card.x}, {card.y}) to ({path[1].x}, {path[1].y}): "
                f"{before} -> {after} on the field."
            )
            if before is None or after is None or after > before:
                if len(path) == 3:  # noqa: PLR2004
                    middle = cell_at(path[1])
                    if not self._field_move(path[1], path[2]):
                        if middle is not None:
                            occupied.add(middle)
                        return False
                occupied.add((row, col))
                return True
            logging.warning(
                f"The drag from ({card.x}, {card.y}) did not register, trying again."
            )
            if attempt + 1 < _DRAG_ATTEMPTS:
                card = self._find_card(evolution_id) or card
        return False

    def _place_wanted(
        self, wanted: dict[str, FormationUnit]
    ) -> dict[str, FormationUnit]:
        """Walk back through the tray and drag the wanted cards to their cells.

        Args:
            wanted: Evolution id of each card to place, with its formation unit.

        Returns:
            The cards that could not be placed (not found in the tray, or the
            drag did not work); empty when everything was placed.
        """
        wanted = dict(wanted)
        failed: dict[str, FormationUnit] = {}
        while True:
            for card, evolution_id in self._visible_cards():
                unit = wanted.get(evolution_id or "")
                if unit is None:
                    continue
                del wanted[evolution_id or ""]
                logging.debug(
                    f"Placing {evolution_id} at row {unit.row}, col {unit.col}."
                )
                if not self._place_card(card, unit.row, unit.col, evolution_id or ""):
                    logging.warning(f"Could not place {evolution_id}.")
                    failed[evolution_id or ""] = unit
            if not wanted or not self._scroll_tray(False):
                break
        for evolution_id in wanted:
            logging.warning(f"{evolution_id} was not found in the tray.")
        return {**failed, **wanted}

    def _units_on_field(self, needed: int, missing: dict[str, dict]) -> int:
        """Count the tatari on the field (the placed ones if the counter fails)."""
        count = self._read_deployed_count()
        if count is not None:
            return count
        return needed - sum(len(units) for units in missing.values())

    def _deploy_formation(self, formation: Formation) -> DeployResult:
        """Clear the field and deploy a formation one element at a time.

        For each element of the formation the tray is filtered to that element
        (a short tray), scanned to its end to see what the player owns, and then
        walked back to its start while the wanted cards are dragged to their cells.
        Units that could not be placed are tried again for up to _FILL_ATTEMPTS
        rounds, without clearing the field.

        Args:
            formation: The formation to deploy.

        Returns:
            The tatari on the field and how many the formation can have (0 and 0
            if the tatari data cannot be read).
        """
        try:  # before the field is touched: unreadable data must not cost a clear
            self._get_recognizer()
        except (OSError, KeyError, ValueError, TypeError) as error:
            logging.error(f"Cannot read the tatari data ({error!r}); not deploying.")
            return DeployResult(0, 0)

        self.tap(CLEAR_FIELD_POINT, log=False)
        sleep(_CLEAR_SETTLE_SECONDS)
        count = self._read_deployed_count()
        if count not in (0, None):
            logging.warning(
                f"Field not empty after clearing ({count}), clearing again."
            )
            self.tap(CLEAR_FIELD_POINT, log=False)
            sleep(_CLEAR_SETTLE_SECONDS)
            count = self._read_deployed_count()
        self._deployed_count = count
        self._occupied = set()

        by_element: dict[str, list[FormationUnit]] = {}
        for unit in formation.units[:MAX_DEPLOYED]:
            by_element.setdefault(unit.tatari_id.split("-")[0], []).append(unit)

        needed = 0
        missing: dict[str, dict[str, FormationUnit]] = {}
        for element, units in by_element.items():
            self._select_element(element)
            owned = self._scan_owned()
            plan = plan_deployment(
                Formation(formation.stage, tuple(units)), owned, MAX_DEPLOYED
            )
            wanted = {p.evolution_id: p.unit for p in plan if p.evolution_id}
            absent = [p.unit.evolution_id for p in plan if not p.evolution_id]
            summary = (
                f"Hệ {element}: nhận diện {len(owned)} tatari trong tray, "
                f"có {len(wanted)}/{len(plan)} tatari cần"
            )
            if absent:
                logging.warning(f"{summary}, thiếu {', '.join(absent)}")
            else:
                logging.info(f"{summary}, đủ {len(plan)}/{len(plan)}")
            needed += len(wanted)
            missing[element] = self._place_wanted(wanted)
            logging.info(
                f"Hệ {element}: đã xếp {len(wanted) - len(missing[element])}"
                f"/{len(wanted)}"
            )

        count = self._units_on_field(needed, missing)
        for fill_round in range(1, _FILL_ATTEMPTS + 1):
            if count >= needed or not any(missing.values()):
                break
            logging.warning(
                f"Bù quân lần {fill_round}/{_FILL_ATTEMPTS}: còn thiếu "
                f"{needed - count} quân."
            )
            for element, wanted in list(missing.items()):
                if not wanted:
                    continue
                self._select_element(element)
                self._scan_owned()  # leaves the tray at its end
                missing[element] = self._place_wanted(wanted)
            count = self._units_on_field(needed, missing)
        self._select_element(None)
        self._deployed_count = count

        logging.info(f"Đã xếp {count}/{needed} quân của đội hình.")
        waiting = self._get_recognizer().waiting_count()
        if waiting > 0:
            logging.info(
                f"Có {waiting} thẻ chưa nhận ra, mở cửa sổ đội hình để chỉ cho bot."
            )
        return DeployResult(count, needed)
