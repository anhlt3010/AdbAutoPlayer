"""Võ Đường Huy Hiệu of Clash of Critters: five Võ Đường, one per element.

Each Võ Đường with a yellow "Thử Thách" button is played stage after stage with the
prepared formations of ``tatari_dojo/``. A stage is given up when every formation of
it lost ``auto_battle.max_formation_attempts`` times; then the next element follows.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from time import sleep

import cv2
import numpy as np
from adb_auto_player.exceptions import GameTimeoutError
from adb_auto_player.games.clash_of_critters.auto_battle import (
    DEFEAT_TITLE,
    QUICK_DEPLOY_BUTTON,
    VICTORY_TITLE,
    AutoBattleMixin,
)
from adb_auto_player.games.clash_of_critters.battle_layout import (
    BATTLE_LAYOUT,
    DOJO_LAYOUT,
)
from adb_auto_player.games.clash_of_critters.formation import (
    StageId,
    load_dojo_formations,
)
from adb_auto_player.models.geometry import Point

DOJO_ELEMENTS = ("water", "fire", "grass", "rock", "lightning")
DOJO_ELEMENT_NAMES = {
    "water": "Thủy",
    "fire": "Hỏa",
    "grass": "Thảo",
    "rock": "Thạch",
    "lightning": "Lôi",
}
# Element tabs along the bottom of the Võ Đường screen.
_TAB_Y = 1720
DOJO_TAB_POINTS = {
    element: Point(x, _TAB_Y)
    for element, x in zip(DOJO_ELEMENTS, (125, 330, 540, 745, 955), strict=True)
}
CHALLENGE_POINT = Point(540, 1495)  # "Thử Thách"
DOJO_CLOSE_POINT = Point(540, 1845)  # X of the bottom bar
PREP_BACK_POINT = Point(85, 1800)  # arrow of the preparation screen (leaves to camp)
NEW_TRAIT_CLOSE_POINT = Point(540, 1600)  # empty area closing "Đặc Điểm Mới!"
REVEAL_BUTTON_POINT = Point(540, 1710)  # "Mở Thêm Nhóm" of the reveal after a win
DIALOG_TAP_POINT = Point(540, 1760)  # the speech box of the Võ Đường master

# "Chế Độ" button, shown on both the camp and the pinball screen (the template must
# match on both). Text/icon only: any badge or red dot on it is dynamic.
MODES_BUTTON = "modes_button.png"
# "Võ Đường Huy Hiệu" banner on the "Chế Độ" screen. Cropped to the static title/art
# only: the counters and timers on the banner change.
BADGE_DOJO_BANNER = "badge_dojo_banner.png"
_MODES_TIMEOUT_SECONDS = 10
_TAB_SETTLE_SECONDS = 1.5
_RETURN_POLLS = 15
_RETURN_POLL_SECONDS = 1

# Templates (text only; the dynamic parts of the screens are left out).
DOJO_START_BUTTON = "dojo_start_button.png"  # "Bắt đầu" under the current stage
# "Huy Hiệu của tôi" button: on every Võ Đường screen, whatever the element (the
# title is rescaled per element name, so it cannot be matched).
DOJO_SCREEN_MARKER = "dojo_my_badges_button.png"
DOJO_RETRY_BUTTON = "dojo_retry_button.png"  # white "Thử Lại" of the defeat screen
DOJO_CONTINUE_BUTTON = "dojo_continue_button.png"  # green "Tiếp tục" of the win screen
DOJO_DEFEAT_BACK_BUTTON = "dojo_defeat_back_button.png"  # "Trở Về" of the defeat screen
# White "Trở Về" of the win screen: next to "Tiếp tục", or alone after the last stage
# on offer (text only, so it matches both layouts).
DOJO_VICTORY_BACK_BUTTON = "dojo_victory_back_button.png"
# Green "Nhận Huy Hiệu" of the win screen of stage 10: it ends the Võ Đường.
DOJO_CLAIM_BADGE_BUTTON = "dojo_claim_badge_button.png"
# After the badge is claimed: a speech box (tapped away), the word "Nhận" on the
# statue (tap it to receive the badge), then the badge screen with "Tuyệt vời!".
DOJO_RECEIVE_TEXT = "dojo_receive_text.png"
DOJO_GREAT_BUTTON = "dojo_great_button.png"
DOJO_NEW_TRAIT_TITLE = "dojo_new_trait_title.png"  # "Đặc Điểm Mới!" popup
_DOJO_SCREENS = [
    DEFEAT_TITLE,
    VICTORY_TITLE,
    QUICK_DEPLOY_BUTTON,
    DOJO_NEW_TRAIT_TITLE,
    DOJO_START_BUTTON,  # the stage list again: the next stage can be started
    DOJO_SCREEN_MARKER,  # back on the Võ Đường screen: this Võ Đường is over
]

_RETURN_SCREENS = [
    DOJO_SCREEN_MARKER,
    DOJO_START_BUTTON,
    BADGE_DOJO_BANNER,
    MODES_BUTTON,
    DOJO_DEFEAT_BACK_BUTTON,
    DOJO_CLAIM_BADGE_BUTTON,  # a win screen left behind: claim, then go back
    DOJO_VICTORY_BACK_BUTTON,
    DOJO_RECEIVE_TEXT,
    DOJO_GREAT_BUTTON,
]

_PHASE_KEPT = "kept"  # the field of the last win is used on this preparation screen
_AGAIN = "again"  # the last stage on offer was won: enter the Võ Đường again
# Times one Võ Đường is entered again after such a win (a safety cap).
MAX_REPLAYS = 12
# Polls with a win screen and no "Tiếp tục" before "Trở Về" is pressed.
_NO_CONTINUE_LIMIT = 2
_GO = "go"
_DONE = "done"
_START_TIMEOUT_SECONDS = 10
# Polls in a row with an unreadable stage label before the Võ Đường is left.
_UNREADABLE_LIMIT = 3

# Edge of the "Thử Thách" button, away from its text: yellow when it can be pressed,
# grey when the Võ Đường is not open yet. Measured mean HSV: yellow (24, 244, 253),
# grey (0, 0, ~130).
_CHALLENGE_PATCH = (slice(1445, 1475), slice(345, 420))  # rows, cols
_YELLOW_HUE = range(15, 36)  # OpenCV hue, 0-179
_MIN_SATURATION, _MIN_VALUE = 150, 150


# "Mở Thêm Nhóm" reveal screen after a win (5/15, 10/15, 15/15): one lime button
# across the whole bottom of the screen. It pulses, so a template of its text only
# matches one size; its colour does not change. Measured: 0.78-0.80 of the band is
# green on the reveal screens, at most 0.22 on every other screen seen.
_REVEAL_BAND = (slice(1655, 1765), slice(60, 1020))  # rows, cols
_REVEAL_HUE = range(30, 56)
_REVEAL_MIN_SATURATION, _REVEAL_MIN_VALUE = 140, 150
_REVEAL_MIN_FRACTION = 0.6


def more_group_reveal_shown(screenshot: np.ndarray) -> bool:
    """Tell whether the "Mở Thêm Nhóm" reveal screen is shown.

    Args:
        screenshot: BGR screenshot at 1080x1920.

    Returns:
        True when a lime button spans the bottom of the screen.
    """
    band = cv2.cvtColor(screenshot[_REVEAL_BAND], cv2.COLOR_BGR2HSV)
    hue, saturation, value = band[..., 0], band[..., 1], band[..., 2]
    green = (
        (hue >= _REVEAL_HUE.start)
        & (hue < _REVEAL_HUE.stop)
        & (saturation > _REVEAL_MIN_SATURATION)
        & (value > _REVEAL_MIN_VALUE)
    )
    return float(green.mean()) >= _REVEAL_MIN_FRACTION


# Speech box of the Võ Đường master ("Xuất sắc. ...") shown after the badge is
# claimed: a white box across the bottom of the Võ Đường screen. Measured: 0.83 of the
# band is near white there, at most 0.26 on every other screen seen.
_DIALOG_BAND = (slice(1690, 1830), slice(40, 1040))  # rows, cols
_DIALOG_MAX_SATURATION, _DIALOG_MIN_VALUE = 40, 235
_DIALOG_MIN_FRACTION = 0.6


def master_dialog_shown(screenshot: np.ndarray) -> bool:
    """Tell whether the speech box of the Võ Đường master is shown.

    Args:
        screenshot: BGR screenshot at 1080x1920.

    Returns:
        True when a white box fills the bottom band of the screen.
    """
    band = cv2.cvtColor(screenshot[_DIALOG_BAND], cv2.COLOR_BGR2HSV)
    white = (band[..., 1] < _DIALOG_MAX_SATURATION) & (band[..., 2] > _DIALOG_MIN_VALUE)
    return float(white.mean()) >= _DIALOG_MIN_FRACTION


def challenge_button_is_yellow(screenshot: np.ndarray) -> bool:
    """Tell whether the "Thử Thách" button of a Võ Đường can be pressed.

    Args:
        screenshot: BGR screenshot at 1080x1920 of the Võ Đường screen.

    Returns:
        True when the button is yellow, False when it is grey.
    """
    patch = cv2.cvtColor(screenshot[_CHALLENGE_PATCH], cv2.COLOR_BGR2HSV)
    hue, saturation, value = (int(v) for v in patch.reshape(-1, 3).mean(axis=0))
    return hue in _YELLOW_HUE and saturation > _MIN_SATURATION and value > _MIN_VALUE


@dataclass(frozen=True)
class DojoFight:
    """One fight of a Võ Đường stage."""

    element: str
    stage: str
    # 1-based position of the formation in the stage's plan, 0 = the field kept from
    # the last win (not part of the plan).
    formation: int
    attempt: int  # 1-based fight count with that formation
    won: bool


def format_dojo_summary(
    fights: Sequence[DojoFight], skipped: Sequence[str]
) -> list[str]:
    """Build the log lines that sum up a whole Võ Đường run.

    Args:
        fights: Every fight in the order they were played.
        skipped: Elements whose "Thử Thách" button was grey.

    Returns:
        The lines to log, header first.
    """
    lines = ["Tổng kết Võ Đường Huy Hiệu:"]
    totals: dict[str, list[int]] = {}
    for fight in fights:
        name = DOJO_ELEMENT_NAMES.get(fight.element, fight.element)
        result = "Thắng" if fight.won else "Thua"
        formation = (
            "giữ nguyên đội hình"
            if fight.formation == 0
            else f"đội hình {fight.formation}"
        )
        lines.append(
            f"{name} {fight.stage} | {formation} | lần {fight.attempt} | {result}"
        )
        wins_losses = totals.setdefault(name, [0, 0])
        wins_losses[0 if fight.won else 1] += 1
    if not fights:
        lines.append("Không có trận nào được đánh.")
    lines.extend(
        f"{name}: {wins} thắng, {losses} thua"
        for name, (wins, losses) in totals.items()
    )
    if skipped:
        names = ", ".join(DOJO_ELEMENT_NAMES.get(e, e) for e in skipped)
        lines.append(f"Bỏ qua (nút Thử Thách xám): {names}")
    return lines


class BadgeDojoMixin(AutoBattleMixin):
    """The stage loop of one Võ Đường (see the module docstring)."""

    _dojo_unreadable: int = 0
    # The result screen of the current fight was already recorded (it can be seen
    # again on the next poll while the game changes screens).
    _dojo_result_recorded: bool = False
    # The fight in progress uses the field kept from the last win, not a deploy.
    _dojo_kept_fight: bool = False
    # Polls in a row on a win screen without a "Tiếp tục" button.
    _dojo_no_continue: int = 0

    def _open_badge_dojo(self) -> None:
        """Press "Chế Độ" (camp or pinball screen), then the Võ Đường banner.

        Raises:
            GameTimeoutError: The button or the banner was not found in time.
        """
        modes = self.wait_for_template(
            MODES_BUTTON,
            timeout=_MODES_TIMEOUT_SECONDS,
            timeout_message="Chế Độ button not found (camp or pinball screen).",
        )
        logging.info("Opening Chế Độ.")
        self.tap(modes, log=False)
        banner = self.wait_for_template(
            BADGE_DOJO_BANNER,
            timeout=_MODES_TIMEOUT_SECONDS,
            timeout_message="Võ Đường Huy Hiệu banner not found on Chế Độ screen.",
        )
        logging.info("Opening Võ Đường Huy Hiệu.")
        self.tap(banner, log=False)

    def _enter_dojo_tab(self, element: str) -> bool:
        """Open the tab of an element and tell whether its challenge can start.

        Args:
            element: One of ``DOJO_ELEMENTS``.

        Returns:
            True when the "Thử Thách" button is yellow, False when it is grey.
        """
        self.tap(DOJO_TAB_POINTS[element], log=False)
        sleep(_TAB_SETTLE_SECONDS)
        return challenge_button_is_yellow(self.get_screenshot())

    def _return_to_dojo_screen(self) -> bool:
        """Get back to a Võ Đường screen from wherever the last Võ Đường left us.

        Returns:
            True when a Võ Đường screen is shown, False when it was not found.
        """
        for _ in range(_RETURN_POLLS):
            if self._tap_common_button() or self._tap_overlay_screens():
                sleep(_RETURN_POLL_SECONDS)
                continue
            screen = self.find_any_template(_RETURN_SCREENS)
            if screen is not None:
                if screen.template == DOJO_SCREEN_MARKER:
                    return True
                self._step_towards_dojo_screen(screen)
            sleep(_RETURN_POLL_SECONDS)
        return False

    def _step_towards_dojo_screen(self, screen: object) -> None:
        """Do the one tap that brings the screen seen closer to a Võ Đường screen."""
        template = screen.template  # type: ignore[attr-defined]
        if template == DOJO_START_BUTTON:  # the stage list: its X goes back
            self.tap(DOJO_CLOSE_POINT, log=False)
        elif template == MODES_BUTTON:  # the camp or pinball screen
            self._open_badge_dojo()
        else:  # the banner (Chế Độ screen) or the "Trở Về" of a defeat screen
            self.tap(screen, log=False)

    def _play_element(self, element: str, fights: list[DojoFight]) -> None:
        """Play a Võ Đường, entering it again after a win of its last stage on offer.

        Args:
            element: One of ``DOJO_ELEMENTS``.
            fights: Every fight played so far.
        """
        resume = False
        for _ in range(MAX_REPLAYS + 1):
            if not self._play_dojo(element, fights, resume=resume):
                return
            if not self._return_to_dojo_screen() or not self._enter_dojo_tab(element):
                return  # the button is grey again: the Võ Đường is complete
            resume = True

    def _badge_dojo(self) -> None:
        """Play every Võ Đường with a yellow "Thử Thách" button, then log a summary."""
        self.open_eyes(device_streaming=False)
        fights: list[DojoFight] = []
        skipped: list[str] = []
        self._layout = DOJO_LAYOUT
        try:
            # _return_to_dojo_screen opens Chế Độ and the banner from the camp or
            # pinball screen, and does nothing when a Võ Đường screen is shown.
            for element in DOJO_ELEMENTS:
                if not self._return_to_dojo_screen():
                    logging.error("Võ Đường screen not found, stopping.")
                    break
                name = DOJO_ELEMENT_NAMES[element]
                if not self._enter_dojo_tab(element):
                    logging.info(f"Võ Đường hệ {name}: nút Thử Thách xám, bỏ qua.")
                    skipped.append(element)
                    continue
                logging.info(f"Võ Đường hệ {name}: bắt đầu.")
                self._play_element(element, fights)
        finally:
            self._layout = BATTLE_LAYOUT
            self._tray_element = None
            for line in format_dojo_summary(fights, skipped):
                logging.info(line)

    def _play_dojo(
        self, element: str, fights: list[DojoFight], resume: bool = False
    ) -> bool:
        """Press "Thử Thách" and "Bắt đầu", then play stages until the Võ Đường ends.

        Args:
            element: The element of the Võ Đường, for example "grass".
            fights: Every fight played so far; this run appends to it.
            resume: Enter the Võ Đường again after a win of its last stage on offer:
                the field of that win is kept for the next stage.

        Returns:
            True when the Võ Đường ended with a win and has to be entered again.
        """
        self._plan_stage = None
        self._plan_steps = None
        self._plan_pos = 0
        self._plan_fights = 0
        self._prep_phase = None
        self._idle_since = None
        self._same_screen = None
        self._dojo_unreadable = 0
        self._dojo_result_recorded = False
        if not resume:
            self._keep_field = False  # the first stage of a Võ Đường deploys
        self._dojo_kept_fight = False
        self._dojo_no_continue = 0
        self._tray_element = element  # the tray holds this element only
        self.tap(CHALLENGE_POINT, log=False)
        try:
            start = self.wait_for_template(
                DOJO_START_BUTTON,
                timeout=_START_TIMEOUT_SECONDS,
                timeout_message="Bắt đầu button not found on the stage list.",
            )
        except GameTimeoutError as error:
            logging.warning(f"{error} Skipping this Võ Đường.")
            self.tap(DOJO_CLOSE_POINT, log=False)  # leave the stage list
            return False
        self.tap(start, log=False)
        result = self._dojo_step(element, fights)
        while result == _GO:
            sleep(self.settings.auto_battle.poll_interval_seconds)
            result = self._dojo_step(element, fights)
        return result == _AGAIN

    def _dojo_step(self, element: str, fights: list[DojoFight]) -> str:
        """Look at the screen once and do what it asks for.

        Args:
            element: The element being played.
            fights: Every fight played so far; results are appended to it.

        Returns:
            "go" to poll again, "done" when this Võ Đường is over.
        """
        if self._tap_common_button() or self._tap_overlay_screens():
            self._idle_since = None
            return _GO
        screen = self.find_any_template(_DOJO_SCREENS)
        if screen is None:
            self._dojo_result_recorded = False
            self._dojo_no_continue = 0
            return _GO if self._wait_on_unknown_screen() else _DONE
        self._idle_since = None
        if self._is_stuck(screen.template):
            # A known screen the taps cannot get past (a missing button, a popup).
            return _DONE
        return self._dojo_on_screen(screen, element, fights)

    def _dojo_on_screen(
        self, screen: object, element: str, fights: list[DojoFight]
    ) -> str:
        """Do what a known screen asks for (see ``_dojo_step`` for the result)."""
        template = screen.template  # type: ignore[attr-defined]
        if template == DOJO_SCREEN_MARKER:
            logging.info("Back on the Võ Đường screen.")
            return _DONE
        if template == DOJO_START_BUTTON:
            logging.info("Stage list shown, pressing Bắt đầu.")
            self.tap(screen, log=False)
            return _GO
        if template == DOJO_NEW_TRAIT_TITLE:
            logging.info("Đặc Điểm Mới! popup shown, closing it.")
            self.tap(NEW_TRAIT_CLOSE_POINT, log=False)
            return _GO
        if template == QUICK_DEPLOY_BUTTON:
            self._dojo_result_recorded = False
            self._dojo_no_continue = 0
            return self._dojo_prepare(element)
        # A result screen: the next preparation screen is a new visit.
        self._prep_phase = None
        if template == VICTORY_TITLE:
            return self._dojo_won(element, fights)
        return self._dojo_lost(element, fights)

    def _tap_overlay_screens(self) -> bool:
        """Tap through the screens that only show a button or a speech box.

        One screenshot is checked for the "Mở Thêm Nhóm" reveal after a win and for
        the speech box of the Võ Đường master.

        Returns:
            True if something was tapped.
        """
        screenshot = self.get_screenshot()
        if more_group_reveal_shown(screenshot):
            logging.info("Mở Thêm Nhóm shown, pressing it.")
            self.tap(REVEAL_BUTTON_POINT, log=False)
            return True
        if master_dialog_shown(screenshot):
            logging.info("Hộp thoại của sư phụ Võ Đường hiện ra, đóng lại.")
            self.tap(DIALOG_TAP_POINT, log=False)
            return True
        return False

    def _leave_preparation(self) -> str:
        """Leave the preparation screen (the arrow goes back to the camp screen)."""
        self.tap(PREP_BACK_POINT, log=False)
        return _DONE

    def _dojo_prepare(self, element: str) -> str:
        """Handle the preparation screen: read the stage, deploy, fight.

        Args:
            element: The element being played.

        Returns:
            "go" or "done" like ``_dojo_step``.
        """
        if self._prep_phase is not None:
            # This visit already started its fight; the fight has not begun yet.
            self._tap_fight()
            return _GO
        stage = self._read_stage()
        if stage is None:
            return self._dojo_unreadable_stage()
        self._dojo_unreadable = 0
        if (stage != self._plan_stage or self._plan_steps is None) and not (
            self._load_dojo_plan(element, stage)
        ):
            return self._leave_preparation()
        if self._keep_field and self._field_has_units():
            self._fight_with_the_kept_field(stage)
            return _GO
        if not self._play_plan_step(stage, False, None):
            return self._leave_preparation()
        return _GO

    def _dojo_unreadable_stage(self) -> str:
        """Count a poll with an unreadable stage label; leave after a few."""
        self._dojo_unreadable += 1
        logging.warning("Stage unreadable on the Võ Đường preparation screen.")
        if self._dojo_unreadable < _UNREADABLE_LIMIT:
            return _GO
        logging.warning("Stage still unreadable, leaving this Võ Đường.")
        return self._leave_preparation()

    def _load_dojo_plan(self, element: str, stage: StageId) -> bool:
        """Make the formations of a stage the current plan.

        Returns:
            False when the stage has no formation file.
        """
        root = self.template_dir.parent / "tatari_dojo"
        formations = load_dojo_formations(root, element, stage)
        if not formations:
            logging.warning(f"No formation for Võ Đường stage {stage}, leaving.")
            return False
        self._plan_stage = stage
        self._plan_steps = list(formations)
        self._plan_pos = 0
        self._plan_fights = 0
        return True

    def _fight_with_the_kept_field(self, stage: StageId) -> None:
        """Fight with the field the game kept after the last win.

        Only a loss deploys the formations of the stage; a kept fight is not part
        of the plan.
        """
        logging.info(f"Giữ nguyên đội hình của stage trước cho stage {stage}.")
        self._prep_phase = _PHASE_KEPT
        self._dojo_kept_fight = True
        self._tap_fight()

    def _record_fight(self, element: str, fights: list[DojoFight], won: bool) -> None:
        stage = str(self._plan_stage) if self._plan_stage is not None else "?"
        if self._dojo_kept_fight:
            fight = DojoFight(element, stage, 0, 1, won)  # formation 0: kept field
        else:
            fight = DojoFight(
                element, stage, self._plan_pos + 1, self._plan_fights, won
            )
        fights.append(fight)
        self._dojo_kept_fight = False
        self._dojo_result_recorded = True

    def _dojo_won(self, element: str, fights: list[DojoFight]) -> str:
        """Record a win and press "Tiếp tục", "Nhận Huy Hiệu" or "Trở Về".

        Returns:
            "go"; "again" after "Nhận Huy Hiệu" (stage 10 won) or when only "Trở Về"
            is shown (stage 9 won): the Võ Đường is entered again if its "Thử Thách"
            button is still yellow (stage 10, or the next tier).
        """
        if not self._dojo_result_recorded:
            self._record_fight(element, fights, True)
            self._keep_field = True
            logging.info(f"Thắng stage {self._plan_stage}.")
            # The next stage is a new plan; the field kept by the game is not used.
            self._plan_stage = None
        button = self.find_any_template([DOJO_CONTINUE_BUTTON])
        if button is not None:
            self._dojo_no_continue = 0
            self.tap(button, log=False)
            return _GO
        claim = self.find_any_template([DOJO_CLAIM_BADGE_BUTTON])
        if claim is not None:
            logging.info("Stage cuối đã thắng, nhận huy hiệu.")
            self.tap(claim, log=False)
            return _AGAIN  # the next tier of this Võ Đường may be open
        self._dojo_no_continue += 1
        if self._dojo_no_continue < _NO_CONTINUE_LIMIT:
            return _GO  # "Tiếp tục" may not be drawn yet
        back = self.find_any_template([DOJO_VICTORY_BACK_BUTTON])
        if back is None:
            return _GO
        logging.info("Win screen without Tiếp tục, pressing Trở Về.")
        self.tap(back, log=False)
        return _AGAIN

    def _dojo_lost(self, element: str, fights: list[DojoFight]) -> str:
        if not self._dojo_result_recorded:
            self._record_fight(element, fights, False)
            self._keep_field = False
            logging.info(f"Thua stage {self._plan_stage}.")
        if self._plan_exhausted():
            logging.warning(
                f"Stage {self._plan_stage} lost with every formation, leaving."
            )
            back = self.find_any_template([DOJO_DEFEAT_BACK_BUTTON])
            if back is not None:
                self.tap(back, log=False)
            return _DONE
        retry = self.find_any_template([DOJO_RETRY_BUTTON])
        if retry is not None:
            self.tap(retry, log=False)
        return _GO

    def _plan_exhausted(self) -> bool:
        """Tell whether every formation of the stage was lost the allowed times."""
        steps = self._plan_steps
        if not steps:
            return False
        limit = self.settings.auto_battle.max_formation_attempts
        return self._plan_pos >= len(steps) - 1 and self._plan_fights >= limit
