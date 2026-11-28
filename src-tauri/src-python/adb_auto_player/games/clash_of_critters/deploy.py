"""Tray scanning and formation deployment on the battle preparation screen."""

import logging
import re
from dataclasses import dataclass
from time import monotonic, sleep

import cv2
import numpy as np
from adb_auto_player.file_loader import SettingsLoader
from adb_auto_player.game import Game
from adb_auto_player.games.clash_of_critters.battle_layout import (
    ALL_FILTER_POINT,
    BATTLE_LAYOUT,
    DOJO_LAYOUT,
    ELEMENT_FILTER_POINTS,
    PrepLayout,
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
from adb_auto_player.games.clash_of_critters.quick_formation import (
    QuickDeployer,
    QuickDeployError,
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
# The swipe along the gap between the two tray rows (``layout.scroll_y``) moves the
# tray forward to reveal cards on the right. The tray keeps moving after the finger
# lifts (about 1.25x the swipe), so a page still overlaps the previous one.
# Mean absolute pixel difference of the tray that counts as "the tray moved".
_TRAY_MOVED_MIN_DIFF = 3.0
_COUNTER_PATTERN = re.compile(r"(\d+)\s*/\s*\d+")
# Rounds that try again the units that could not be placed (the field is not cleared).
_FILL_ATTEMPTS = 5
# How often the folder of unrecognized cards is checked while the user teaches them.
_TEACH_POLL_SECONDS = 1.0
# Times the user is asked again because a pass saved new unrecognized cards.
_TEACH_ROUNDS = 3
# "Triển Khai Nhanh" button of the preparation screen (1080x1920).
_QUICK_DEPLOY_POINT = Point(390, 1800)


@dataclass(frozen=True)
class DeployResult:
    """What a deployment left on the field.

    Attributes:
        count: Tatari on the field (the counter, or the number placed if the
            counter cannot be read).
        needed: Cells of the formation that have an owned tatari to put on them.
        blocked: Unrecognized tray cards were still waiting for the user when the
            wait ended, so the formation cannot be trusted to be complete.
    """

    count: int
    needed: int
    blocked: bool = False

    @property
    def complete(self) -> bool:
        """Whether every cell that could be filled has a tatari."""
        return not self.blocked and self.count >= self.needed


class DeployMixin(Game):
    """Reads the tray of owned tatari and deploys formations by drag and drop."""

    # Geometry of the preparation screen (a Võ Đường command sets DOJO_LAYOUT).
    _layout: PrepLayout = BATTLE_LAYOUT
    # The element of every card in the tray when it is known (Võ Đường), else None:
    # the element is then read from the icon colour of each card.
    _tray_element: str | None = None
    _recognizer: CardRecognizer | None = None
    # Last value read from the deployed counter (None if unknown or unreadable).
    _deployed_count: int | None = None
    # Cells of the field that hold a unit (set while a formation is deployed).
    _occupied: set[tuple[int, int]] | None = None
    _quick_deployer: QuickDeployer | None = None

    def _get_quick_deployer(self) -> QuickDeployer:
        if self._quick_deployer is None:
            self._quick_deployer = QuickDeployer(
                shell=lambda cmd: self.device.d.shell(cmd, encoding=None),
                press_quick_deploy=lambda: self.tap(
                    self._apply_vertical_offset(_QUICK_DEPLOY_POINT), log=False
                ),
                read_deployed_count=self._read_deployed_count,
                state_dir=SettingsLoader.get_app_config_dir(),
            )
        return self._quick_deployer

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
        layout = self._layout
        lefts = find_card_lefts(screenshot, layout)
        cards: list[tuple[Point, str | None]] = []
        for row_y in layout.tray_rows_y:
            for card_left in lefts:
                center = Point(card_left + layout.card_size[0] // 2, row_y)
                left, top, right, bottom = card_box(center, layout)
                crop = screenshot[top:bottom, left:right]
                if layout.card_size != BATTLE_LAYOUT.card_size:
                    # The recognizer's boxes are measured on the battle card size.
                    crop = cv2.resize(crop, BATTLE_LAYOUT.card_size)
                cards.append(
                    (center, recognizer.recognize(crop, element=self._tray_element))
                )
        return cards

    def _wait_tray_stable(self) -> np.ndarray:
        """Wait until the tray has stopped moving.

        Returns:
            The first screenshot whose tray equals the one before it (or the last
            one taken if the tray never settles within the time limit).
        """
        left, top, right, bottom = self._layout.tray_box
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
        layout = self._layout
        left, top, right, bottom = layout.tray_box
        before = self.get_screenshot()[top:bottom, left:right].astype(np.int16)
        start_x, end_x = (
            (layout.scroll_from_x, layout.scroll_to_x)
            if forward
            else (layout.scroll_to_x, layout.scroll_from_x)
        )
        self.device.swipe(
            self._apply_vertical_offset(Point(start_x, layout.scroll_y)),
            self._apply_vertical_offset(Point(end_x, layout.scroll_y)),
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
        left, top, right, bottom = self._layout.counter_box
        crop = self.get_screenshot()[top:bottom, left:right]
        text = RapidOCRBackend().extract_text(crop)
        match = _COUNTER_PATTERN.search(text)
        return int(match.group(1)) if match else None

    def _select_element(self, element: str | None) -> None:
        """Show only the tray cards of one element (None shows all)."""
        if not self._layout.has_element_filter:
            return
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
            path = plan_drag(card, row, col, occupied, self._layout)
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
                    middle = cell_at(path[1], self._layout)
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
        """Deploy a formation at once, falling back to drag and drop.

        The quick deploy is only used on the normal preparation screen (the Võ Đường
        layout is not supported) and must be confirmed by the deployed counter.

        Args:
            formation: The formation to deploy.

        Returns:
            The tatari on the field and how many the formation can have.
        """
        if self._layout is BATTLE_LAYOUT:
            try:
                result = self._get_quick_deployer().deploy(formation.units)
                if result.verified:
                    self._deployed_count = result.count
                    return DeployResult(result.count, result.needed)
                logging.warning(
                    "Quick deploy could not be confirmed by the counter, "
                    "deploying by drag and drop."
                )
            except QuickDeployError as error:
                logging.warning(
                    f"Quick deploy is not available ({error}), "
                    "deploying by drag and drop."
                )
        return self._deploy_formation_by_drag(formation)

    def _deploy_formation_by_drag(self, formation: Formation) -> DeployResult:
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

        clear_point = self._layout.clear_field_point
        self.tap(clear_point, log=False)
        sleep(_CLEAR_SETTLE_SECONDS)
        count = self._read_deployed_count()
        if count not in (0, None):
            logging.warning(
                f"Field not empty after clearing ({count}), clearing again."
            )
            self.tap(clear_point, log=False)
            sleep(_CLEAR_SETTLE_SECONDS)
            count = self._read_deployed_count()
        self._deployed_count = count
        self._occupied = set()

        by_element: dict[str, list[FormationUnit]] = {}
        max_deployed = self._layout.max_deployed
        for unit in formation.units[:max_deployed]:
            by_element.setdefault(unit.tatari_id.split("-")[0], []).append(unit)

        missing: dict[str, dict[str, FormationUnit]] = {}
        needed, absent = self._deploy_elements(formation, by_element, missing)

        # A card the bot did not recognize looks like a tatari the player lacks:
        # wait for the user to teach those cards, then place the units still absent.
        # A pass can save new crops (a card of the same tatari at another tier), so
        # repeat while units are absent and crops are waiting.
        teach_rounds = 0
        while absent and self._get_recognizer().waiting_count() > 0:
            if teach_rounds >= _TEACH_ROUNDS or not self._await_card_teaching():
                self._select_element(None)
                count = self._units_on_field(needed, missing)
                self._deployed_count = count
                logging.warning(
                    f"Đã xếp {count}/{needed} quân, còn thẻ chưa nhận ra: "
                    "bỏ đội hình này."
                )
                return DeployResult(count, needed, blocked=True)
            teach_rounds += 1
            retry: dict[str, list[FormationUnit]] = {}
            for unit in absent:
                retry.setdefault(unit.tatari_id.split("-")[0], []).append(unit)
            more_needed, absent = self._deploy_elements(formation, retry, missing)
            needed += more_needed

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
        return DeployResult(count, needed)

    def _deploy_elements(
        self,
        formation: Formation,
        by_element: dict[str, list[FormationUnit]],
        missing: dict[str, dict[str, FormationUnit]],
    ) -> tuple[int, list[FormationUnit]]:
        """Scan the tray and place the units of each element.

        Args:
            formation: The formation being deployed.
            by_element: The units to place, grouped by element.
            missing: Updated with the units that could not be placed, by element.

        Returns:
            The number of units that have an owned tatari to put on them, and the
            units whose tatari is not in the tray (not owned, or not recognized).
        """
        needed = 0
        absent_units: list[FormationUnit] = []
        for element, units in by_element.items():
            self._select_element(element)
            owned = self._scan_owned()
            plan = plan_deployment(
                Formation(formation.stage, tuple(units)),
                owned,
                self._layout.max_deployed,
            )
            wanted = {p.evolution_id: p.unit for p in plan if p.evolution_id}
            absent = [p.unit.evolution_id for p in plan if not p.evolution_id]
            absent_units.extend(p.unit for p in plan if not p.evolution_id)
            summary = (
                f"Hệ {element}: nhận diện {len(owned)} tatari trong tray, "
                f"có {len(wanted)}/{len(plan)} tatari cần"
            )
            if absent:
                logging.warning(f"{summary}, thiếu {', '.join(absent)}")
            else:
                logging.info(f"{summary}, đủ {len(plan)}/{len(plan)}")
            needed += len(wanted)
            missing[element] = {
                **missing.get(element, {}),
                **self._place_wanted(wanted),
            }
            logging.info(
                f"Hệ {element}: đã xếp {len(wanted) - len(missing[element])}"
                f"/{len(wanted)}"
            )
        return needed, absent_units

    def _await_card_teaching(self) -> bool:
        """Open the formation window and wait until no unrecognized card is left.

        The log record carries the flag ``open_card_teaching``; the app turns it
        into the event that opens the window on the cards tab. Teaching a card
        deletes its crop, so the folder is polled.

        Returns:
            True when no card is waiting (at once if none was), False when
            ``auto_battle.card_teaching_wait_seconds`` passed first.
        """
        recognizer = self._get_recognizer()
        waiting = recognizer.waiting_count()
        if waiting == 0:
            return True
        logging.info(
            f"Có {waiting} thẻ chưa nhận ra, mở cửa sổ đội hình để chỉ cho bot.",
            extra={
                "open_card_teaching": True,
                # The window opens in the mode of this run (its formation tab
                # reads the stage with the box of that screen).
                "viewer_mode": "dojo" if self._layout is DOJO_LAYOUT else "battle",
            },
        )
        limit = self.settings.auto_battle.card_teaching_wait_seconds
        deadline = monotonic() + limit
        while recognizer.waiting_count() > 0:
            if monotonic() >= deadline:
                logging.warning(f"Chờ {limit}s mà vẫn còn thẻ chưa nhận ra.")
                return False
            sleep(_TEACH_POLL_SECONDS)
        return True
