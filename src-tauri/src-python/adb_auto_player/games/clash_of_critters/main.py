"""Clash of Critters Main Module."""

import logging
import re
from time import monotonic, sleep

import cv2
import numpy as np
from adb_auto_player.decorators import register_command, register_game
from adb_auto_player.games.clash_of_critters.auto_battle import AutoBattleMixin
from adb_auto_player.games.clash_of_critters.settings import Settings
from adb_auto_player.models.decorators import GameGUIMetadata, GUIMetadata
from adb_auto_player.models.device import Resolution
from adb_auto_player.models.geometry import Point
from adb_auto_player.models.template_matching import TemplateMatchResult
from adb_auto_player.ocr import RapidOCRBackend

PINBALL_TAB = "pinball_tab.png"  # shown on the camp screen
# Shown on the pinball screen; the crop excludes the optional pinball-ball bubble.
CAMP_TAB = "camp_tab.png"
# Cat card on the pinball screen. Cropped to the ear/eye area only: the torch count,
# the number in the middle and the "ends in N days" label all change.
ARTIFACT_ADVENTURE_ICON = "artifact_adventure_icon.png"
# Trophy card of the Zobo Hunt event on the pinball screen. Cropped to the Zobo face on
# the trophy only: the coin bubble, the number and the "ends in N days" label change.
ZOBO_HUNT_ICON = "zobo_hunt_icon.png"
# Fish card of the Fishing Contest event on the pinball screen. Cropped to the fish
# head and eye only: the rod count bubble, the number and the "ends in N days" label
# change.
FISHING_CONTEST_ICON = "fishing_contest_icon.png"
# "Cuộc Thi Câu Cá" title of the event screen.
FISHING_CONTEST_TITLE = "fishing_contest_title.png"
# "người chơi trên máy" text of the catch result screen ("Đánh bại N% người chơi trên
# máy chủ!"). It stays until tapped; a tap on the dimmed top area closes it (a tap
# on the fish does not).
FISHING_CONTEST_RESULT = "fishing_contest_result.png"
_FISHING_RESULT_CLOSE = Point(540, 250)
# Round fishing button. Its rod picture, the rod count and the "x1" badge change, so
# its state is read from the colour of the left edge of the circle: green = cast,
# grey = waiting for a bite, purple = a fish bites (tap to reel in).
_FISHING_BUTTON = Point(540, 1580)
_FISHING_STATE_PATCH = (slice(1560, 1600), slice(415, 435))  # rows, cols
_FISHING_STATE_POLL_SECONDS = 0.2
# Green that stays this long after a cast means no cast happened (out of rods).
_FISHING_CAST_TIMEOUT_SECONDS = 10
_GREY_MAX_SATURATION = 40
_MIN_SATURATION, _MIN_VALUE = 100, 100
_GREEN_HUE = range(35, 71)  # OpenCV hue, 0-179
_PURPLE_HUE = range(125, 156)
# Text of the "Bắt Đầu Ngay" button on the Zobo Hunt screen.
ZOBO_HUNT_START_BUTTON = "zobo_hunt_start_button.png"
# "X" close button at the bottom of the arena; shown for the whole hunt.
ZOBO_HUNT_ARENA_CLOSE = "zobo_hunt_arena_close.png"
# Buff labels. While a buff runs its label is replaced by a countdown, so a visible
# label means the buff is ready to be pressed again.
ZOBO_HUNT_RAGE_BUTTON = "zobo_hunt_rage_button.png"  # "Cuồng Nộ"
ZOBO_HUNT_TARGET_LOCK_BUTTON = "zobo_hunt_target_lock_button.png"  # "Khóa Mục Tiêu"
_ZOBO_HUNT_BUFF_LOG = {
    ZOBO_HUNT_RAGE_BUTTON: "Activating Cuồng Nộ.",
    ZOBO_HUNT_TARGET_LOCK_BUTTON: "Activating Khóa Mục Tiêu.",
}
# Holding the arena keeps shooting; buffs are re-checked after every hold.
_ZOBO_HUNT_HOLD_POINT = Point(540, 950)
_ZOBO_HUNT_HOLD_SECONDS = 3
# "Tiến Lên" text of the button on the stage screen. The torch icon (changes with the
# torch type) above it and the torch count below it are dynamic and excluded.
ARTIFACT_ADVENTURE_ADVANCE_BUTTON = "artifact_adventure_advance_button.png"
# "Chạm điểm bất kì để tiếp tục" hint shown after every stage event.
ARTIFACT_ADVENTURE_TAP_TO_CONTINUE = "artifact_adventure_tap_to_continue.png"
# Text part of the start button; the "1x" speed badge above it is dynamic.
ARTIFACT_ADVENTURE_START_BUTTON = "artifact_adventure_start_button.png"
# Fight-or-retreat choice. Both cards are cropped to icon + title; the description
# and the win rate below them are not part of the templates.
ARTIFACT_ADVENTURE_RETREAT_BUTTON = "artifact_adventure_retreat_button.png"
ARTIFACT_ADVENTURE_FIGHT_BUTTON = "artifact_adventure_fight_button.png"
# "Tỷ lệ thắng 80% + 5%" line on the Fight card (y ~1635-1705 of 1920).
_WIN_RATE_LEFT, _WIN_RATE_RIGHT = 0.54, 0.92
_WIN_RATE_TOP, _WIN_RATE_BOTTOM = 0.85, 0.89
_WIN_RATE_PATTERN = re.compile(r"(\d{1,3})\s*%")
# "Chấp Nhận" button on the "Phiêu Lưu Kết Thúc" reward screen.
ARTIFACT_ADVENTURE_ACCEPT_BUTTON = "artifact_adventure_accept_button.png"
# "Nhận Ngay" button of the "Bàn Tay Vàng" popup shown mid-adventure.
ARTIFACT_ADVENTURE_CLAIM_BUTTON = "artifact_adventure_claim_button.png"
# Buttons that can show up on any screen of the game; whenever one is seen it is
# tapped, in every command. Text only (the "10/25" badge next to "Mở thêm nhóm" is
# dynamic).
OPEN_ALL_BUTTON = "open_all_button.png"  # "Mở Tất Cả"
OK_BUTTON = "ok_button.png"  # "OK" on the "Phần Thưởng!" reward screen
# "Mở thêm nhóm" when it is the only button on the screen (text only; the "5/6" badge
# above it is dynamic). Listed after "Mở Tất Cả" so that one wins if both are shown.
MORE_GROUP_BUTTON = "more_group_button.png"
_COMMON_BUTTONS = [OPEN_ALL_BUTTON, OK_BUTTON, MORE_GROUP_BUTTON]
_COMMON_BUTTON_LOG = {
    OPEN_ALL_BUTTON: "Mở Tất Cả button shown, pressing it.",
    OK_BUTTON: "OK button shown, pressing it.",
    MORE_GROUP_BUTTON: "Mở thêm nhóm button shown, pressing it.",
}
_EVENT_ICON_TIMEOUT_SECONDS = 10
# Pause on the "new adventure" screen before pressing the start button.
_START_SCREEN_WAIT_SECONDS = 20
_ADVENTURE_POLL_SECONDS = 1
# Let the stage event start before looking again, so "Tiến Lên" is not pressed twice.
_ADVANCE_SETTLE_SECONDS = 3
# Stop when none of the adventure screens was seen for this long (e.g. out of torches).
_ADVENTURE_IDLE_LIMIT_SECONDS = 60

_PINBALL_TAB_TIMEOUT_SECONDS = 10

# Tension bar shown after some bites: the red bobber runs back and forth on its own
# (~300 px/s) and the purple button must be tapped while it is in the yellow zone.
# Every hit shrinks the zone, so several hits are needed. Measured at 1080x1920.
_TENSION_BAR_BAND = (slice(1230, 1340), slice(270, 850))  # rows, cols
_TENSION_BAR_LEFT = 270
_BOBBER_MIN_PIXELS = 200  # fewer red pixels: no bobber (e.g. the bite timer bar)
_ZONE_MIN_COLUMNS = 30
_VIVID_SATURATION, _VIVID_VALUE = 150, 150
_RED_HUE_MAX, _RED_HUE_MIN = 8, 170  # red wraps around hue 0
_YELLOW_HUE_MIN, _YELLOW_HUE_MAX = 20, 35
# The bobber hides the yellow under it: the zone is measured only while the bobber
# is at least this far outside of it.
_BOBBER_HALF_WIDTH = 40
# Time from deciding to tap until the game sees the tap; the bobber position is
# predicted that far ahead. Hits need the prediction this far inside the zone.
_TAP_LEAD_SECONDS = 0.15
_ZONE_MARGIN = 20
# The bar is over when the bobber was not seen for this long.
_TENSION_BAR_GONE_SECONDS = 1.5
_TENSION_BAR_POLL_SECONDS = 0.01


def read_tension_bar(
    screenshot: np.ndarray,
) -> tuple[int, tuple[int, int] | None] | None:
    """Find the bobber and the yellow zone of the tension bar.

    Args:
        screenshot: BGR screenshot at 1080x1920.

    Returns:
        None if no bobber is shown, else (bobber x, (zone left, zone right) or None
        when no yellow is visible). The zone is partly hidden while the bobber is
        over it.
    """
    band = cv2.cvtColor(screenshot[_TENSION_BAR_BAND], cv2.COLOR_BGR2HSV)
    hue, saturation, value = band[..., 0], band[..., 1], band[..., 2]
    vivid = (saturation > _VIVID_SATURATION) & (value > _VIVID_VALUE)
    red = vivid & ((hue < _RED_HUE_MAX) | (hue > _RED_HUE_MIN))
    _, red_x = np.nonzero(red)
    if len(red_x) < _BOBBER_MIN_PIXELS:
        return None
    bobber = int(red_x.mean()) + _TENSION_BAR_LEFT
    yellow = vivid & (hue > _YELLOW_HUE_MIN) & (hue < _YELLOW_HUE_MAX)
    yellow_x = np.nonzero(yellow.any(axis=0))[0]
    if len(yellow_x) < _ZONE_MIN_COLUMNS:
        return bobber, None
    left, right = int(yellow_x.min()), int(yellow_x.max())
    return bobber, (left + _TENSION_BAR_LEFT, right + _TENSION_BAR_LEFT)


def fishing_button_state(screenshot: np.ndarray) -> str | None:
    """Read the state of the fishing button from its colour.

    Args:
        screenshot: BGR screenshot at 1080x1920.

    Returns:
        "cast" (green), "wait" (grey), "bite" (purple), or None if the button is
        not shown (other screen, popup).
    """
    patch = cv2.cvtColor(screenshot[_FISHING_STATE_PATCH], cv2.COLOR_BGR2HSV)
    hue, saturation, value = (int(v) for v in patch.reshape(-1, 3).mean(axis=0))
    if value < _MIN_VALUE:
        return None
    if saturation < _GREY_MAX_SATURATION:
        return "wait"
    if saturation < _MIN_SATURATION:
        return None
    if hue in _GREEN_HUE:
        return "cast"
    if hue in _PURPLE_HUE:
        return "bite"
    return None


@register_game(
    name="Clash of Critters",
    settings_file="ClashOfCritters.toml",
    gui_metadata=GameGUIMetadata(settings_class=Settings),
)
class ClashOfCritters(AutoBattleMixin):
    def __init__(self) -> None:
        """Initialize ClashOfCritters."""
        super().__init__()
        self.base_resolution: Resolution = Resolution.from_string("1080x1920")
        self.package_name_prefixes = ["com.farlightgames.pgame.gp.vn"]

    @property
    def settings(self) -> Settings:
        return self.get_settings()

    def get_settings(self) -> Settings:
        return Settings.from_toml(self.settings_file_path)

    @register_command(
        gui=GUIMetadata(
            label="Tự Động Chiến Đấu",
            category="Battle",
            tooltip=(
                "Play the stages from the camp screen: Quick Deploy first, the "
                "prepared formation on boss stages and after a lost fight."
            ),
        )
    )
    def auto_battle(self) -> None:
        self._run_auto_battle()

    @register_command(
        gui=GUIMetadata(
            label="Phiêu Lưu Cổ Vật",
            category="Events",
            tooltip="Artifact Adventure event (automation not implemented yet).",
        )
    )
    def artifact_adventure(self) -> None:
        self._artifact_adventure(max_advances=None)

    @register_command(
        gui=GUIMetadata(
            label="Phiêu Lưu Cổ Vật Giới Hạn",
            category="Events",
            tooltip=(
                "Artifact Adventure event, stops after a configurable number of "
                "Tiến Lên presses."
            ),
        )
    )
    def artifact_adventure_limited(self) -> None:
        limit = self.settings.artifact_adventure.limited_advance_count
        self._artifact_adventure(max_advances=limit)

    @register_command(
        gui=GUIMetadata(
            label="Săn Bắn Zobo",
            category="Events",
            tooltip=(
                "Zobo Hunt event: start a hunt, keep Cuồng Nộ and Khóa Mục Tiêu "
                "on and hold the screen to shoot."
            ),
        )
    )
    def zobo_hunt(self) -> None:
        self.open_eyes(device_streaming=False)
        if self.find_any_template([ZOBO_HUNT_ARENA_CLOSE]) is None:
            self._start_zobo_hunt()
        else:
            logging.info("Already in the Zobo Hunt arena.")
        self._run_zobo_hunt()

    @register_command(
        gui=GUIMetadata(
            label="Cuộc Thi Câu Cá",
            category="Events",
            tooltip=(
                "Fishing Contest event: cast, wait for a bite and reel in until "
                "out of rods."
            ),
        )
    )
    def fishing_contest(self) -> None:
        # The tension bar needs fresh frames many times a second: stream.
        self.open_eyes(device_streaming=True)
        if self.find_any_template([FISHING_CONTEST_TITLE]) is None:
            self._open_pinball_screen()
            icon = self.wait_for_template(
                FISHING_CONTEST_ICON,
                timeout=_EVENT_ICON_TIMEOUT_SECONDS,
                timeout_message="Fishing Contest icon not found on Pinball screen.",
            )
            logging.info("Opening Fishing Contest.")
            self.tap(icon, log=False)
            self.wait_for_template(
                FISHING_CONTEST_TITLE,
                timeout=_EVENT_ICON_TIMEOUT_SECONDS,
                timeout_message="Fishing Contest screen did not open.",
            )
        else:
            logging.info("Already on Fishing Contest screen.")
        self._run_fishing_contest()

    def _run_fishing_contest(self) -> None:
        """Cast, wait for a bite and reel in, until no cast starts anymore.

        Stops when a cast does not start (out of rods) or when no known state was
        seen for a while. The reward popup ("Nhận Ngay") and common buttons are
        pressed when they show up.
        """
        idle_since = monotonic()
        cast_at: float | None = None
        while monotonic() - idle_since < _ADVENTURE_IDLE_LIMIT_SECONDS:
            screenshot = self.get_screenshot()
            state = fishing_button_state(screenshot)
            if state is None:
                # Popups dim the button: look for them only then, so the bite
                # window is polled fast.
                if self._close_fishing_popup():
                    idle_since = monotonic()
                    sleep(_ADVENTURE_POLL_SECONDS)
                else:
                    sleep(_FISHING_STATE_POLL_SECONDS)
                continue
            idle_since = monotonic()
            if state == "cast":
                if cast_at is None:
                    logging.info("Casting.")
                    self.tap(_FISHING_BUTTON, log=False)
                    cast_at = monotonic()
                elif monotonic() - cast_at > _FISHING_CAST_TIMEOUT_SECONDS:
                    logging.info("Cast did not start (out of rods?), stopping.")
                    return
            elif state == "bite" and read_tension_bar(screenshot) is not None:
                self._play_tension_bar()
                cast_at = None
            elif state == "bite":
                logging.info("Fish bites, reeling in.")
                self.tap(_FISHING_BUTTON, log=False)
                cast_at = None
            else:
                cast_at = None
            sleep(_FISHING_STATE_POLL_SECONDS)

        logging.warning("No Fishing Contest screen detected, stopping.")

    def _play_tension_bar(self) -> None:
        """Tap the purple button each time the bobber runs through the yellow zone.

        The zone is read only while the bobber is outside of it (the bobber hides
        the yellow under it), and after every tap it is read again before the next
        one, since a hit shrinks it. The bobber position is predicted
        `_TAP_LEAD_SECONDS` ahead from its speed. Returns when the bar is gone.
        """
        logging.info("Tension bar shown, timing the taps.")
        zone: tuple[int, int] | None = None
        last_x: int | None = None
        last_at = seen_at = monotonic()
        speed = 0.0
        hits = 0
        while monotonic() - seen_at < _TENSION_BAR_GONE_SECONDS:
            sleep(_TENSION_BAR_POLL_SECONDS)  # lets the stream decoder run
            bar = read_tension_bar(self.get_screenshot())
            now = monotonic()
            if bar is None:
                continue
            seen_at = now
            bobber, seen_zone = bar
            if bobber != last_x:
                if last_x is not None:
                    speed = (bobber - last_x) / (now - last_at)
                last_x, last_at = bobber, now
            if seen_zone is not None and (
                bobber < seen_zone[0] - _BOBBER_HALF_WIDTH
                or bobber > seen_zone[1] + _BOBBER_HALF_WIDTH
            ):
                zone = seen_zone
            if zone is None:
                continue
            ahead = bobber + speed * _TAP_LEAD_SECONDS
            left, right = zone[0] + _ZONE_MARGIN, zone[1] - _ZONE_MARGIN
            if left <= bobber <= right and left <= ahead <= right:
                hits += 1
                logging.info(f"Tap {hits}: bobber {bobber} in zone {zone}.")
                self.tap(_FISHING_BUTTON, log=False)
                zone = None
        logging.info("Tension bar gone.")

    def _close_fishing_popup(self) -> bool:
        """Close a popup of the fishing screen (reward, catch result, common).

        Returns:
            True if a popup was closed, False otherwise.
        """
        if self._tap_common_button():
            return True
        result = self.find_any_template(
            [ARTIFACT_ADVENTURE_CLAIM_BUTTON, FISHING_CONTEST_RESULT]
        )
        if result is None:
            return False
        if result.template == FISHING_CONTEST_RESULT:
            logging.info("Catch result shown, closing it.")
            self.tap(_FISHING_RESULT_CLOSE, log=False)
        else:
            logging.info("Fish caught, pressing Nhận Ngay.")
            self.tap(result, log=False)
        return True

    def _start_zobo_hunt(self) -> None:
        """Open the Zobo Hunt event, wait for the user, then press Bắt Đầu Ngay.

        Raises:
            GameTimeoutError: The icon or the event screen was not found in time.
        """
        if self.find_any_template([ZOBO_HUNT_START_BUTTON]) is None:
            self._open_pinball_screen()
            icon = self.wait_for_template(
                ZOBO_HUNT_ICON,
                timeout=_EVENT_ICON_TIMEOUT_SECONDS,
                timeout_message="Zobo Hunt icon not found on Pinball screen.",
            )
            logging.info("Opening Zobo Hunt.")
            self.tap(icon, log=False)
        else:
            logging.info("Already on Zobo Hunt screen.")
        start = self.wait_for_template(
            ZOBO_HUNT_START_BUTTON,
            timeout=_EVENT_ICON_TIMEOUT_SECONDS,
            timeout_message="Zobo Hunt screen did not open.",
        )
        logging.info(
            f"Chờ {_START_SCREEN_WAIT_SECONDS}s để người dùng thay đổi setting phù hợp"
        )
        sleep(_START_SCREEN_WAIT_SECONDS)
        logging.info("Starting Zobo Hunt.")
        self.tap(start, log=False)

    def _run_zobo_hunt(self) -> None:
        """Keep both buffs on and hold the arena to shoot until it closes.

        Stops when the arena was not seen for a while (hunt over). Common buttons
        ("OK", "Mở Tất Cả", ...) are pressed when they show up.
        """
        idle_since = monotonic()
        while monotonic() - idle_since < _ADVENTURE_IDLE_LIMIT_SECONDS:
            if self._tap_common_button():
                idle_since = monotonic()
                continue
            if self.find_any_template([ZOBO_HUNT_ARENA_CLOSE]) is None:
                sleep(_ADVENTURE_POLL_SECONDS)
                continue

            idle_since = monotonic()
            for buff, message in _ZOBO_HUNT_BUFF_LOG.items():
                result = self.find_any_template([buff])
                if result is not None:
                    logging.info(message)
                    self.tap(result, log=False)
            self.hold(
                _ZOBO_HUNT_HOLD_POINT, duration=_ZOBO_HUNT_HOLD_SECONDS, log=False
            )

        logging.info("Zobo Hunt arena not seen anymore, stopping.")

    def _artifact_adventure(self, max_advances: int | None) -> None:
        """Open the Artifact Adventure event and play it.

        Args:
            max_advances: Stop after this many "Tiến Lên" presses, or None for
                no limit.
        """
        self.open_eyes(device_streaming=False)
        adventure_screens = [
            ARTIFACT_ADVENTURE_TAP_TO_CONTINUE,
            ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
            ARTIFACT_ADVENTURE_START_BUTTON,
            ARTIFACT_ADVENTURE_RETREAT_BUTTON,
            ARTIFACT_ADVENTURE_ACCEPT_BUTTON,
            ARTIFACT_ADVENTURE_CLAIM_BUTTON,
            *_COMMON_BUTTONS,
        ]
        if self.find_any_template(adventure_screens) is None:
            self._open_artifact_adventure_from_pinball(adventure_screens)
        else:
            logging.info("Already on Artifact Adventure screen.")
        self._run_artifact_adventure(adventure_screens, max_advances)

    def _open_artifact_adventure_from_pinball(
        self, adventure_screens: list[str]
    ) -> None:
        """Go to the pinball screen and open the Artifact Adventure event.

        Args:
            adventure_screens: Templates of any Artifact Adventure screen.

        Raises:
            GameTimeoutError: The icon or the event screen was not found in time.
        """
        self._open_pinball_screen()
        icon = self.wait_for_template(
            ARTIFACT_ADVENTURE_ICON,
            timeout=_EVENT_ICON_TIMEOUT_SECONDS,
            timeout_message="Artifact Adventure icon not found on Pinball screen.",
        )
        logging.info("Opening Artifact Adventure.")
        self.tap(icon, log=False)
        self.wait_for_any_template(
            adventure_screens,
            timeout=_EVENT_ICON_TIMEOUT_SECONDS,
            ensure_order=False,
            timeout_message="Artifact Adventure screen did not open.",
        )

    def _run_artifact_adventure(
        self, adventure_screens: list[str], max_advances: int | None = None
    ) -> None:
        """Advance through stages until no adventure screen is seen for a while.

        - Stage screen: press "Tiến Lên".
        - Confirm screen ("Chạm điểm bất kì để tiếp tục"): tap to continue.
        - Fight-or-retreat choice: fight if the win rate reaches the configured
          minimum, otherwise retreat.
        - Adventure ended (reward screen): press "Chấp Nhận".
        - Claim popup: press "Nhận Ngay".
        - "Mở Tất Cả" / "OK" buttons (tapped in every command): press them.
        - New adventure screen: wait, then press "Bắt Đầu Phiêu Lưu!".

        Args:
            adventure_screens: Templates of the adventure screens to react to.
            max_advances: Stop on the next stage/new-adventure screen once
                "Tiến Lên" was pressed this many times; None for no limit.
        """
        advances = 0
        idle_since = monotonic()
        while monotonic() - idle_since < _ADVENTURE_IDLE_LIMIT_SECONDS:
            result = self.find_any_template(adventure_screens)
            if result is None:
                sleep(_ADVENTURE_POLL_SECONDS)
                continue

            idle_since = monotonic()
            limit_reached = max_advances is not None and advances >= max_advances
            if limit_reached and result.template in (
                ARTIFACT_ADVENTURE_ADVANCE_BUTTON,
                ARTIFACT_ADVENTURE_START_BUTTON,
            ):
                logging.info(f"Reached the limit of {max_advances} advances, stopping.")
                return

            if result.template == ARTIFACT_ADVENTURE_TAP_TO_CONTINUE:
                logging.info("Stage event finished, tapping to continue.")
            elif result.template == ARTIFACT_ADVENTURE_ACCEPT_BUTTON:
                logging.info("Adventure ended, accepting rewards.")
            elif result.template == ARTIFACT_ADVENTURE_CLAIM_BUTTON:
                logging.info("Claim popup shown, pressing Nhận Ngay.")
            elif result.template in _COMMON_BUTTON_LOG:
                logging.info(_COMMON_BUTTON_LOG[result.template])
            elif result.template == ARTIFACT_ADVENTURE_RETREAT_BUTTON:
                self._fight_or_retreat(result)
                sleep(_ADVANCE_SETTLE_SECONDS)
                continue
            elif result.template == ARTIFACT_ADVENTURE_ADVANCE_BUTTON:
                advances += 1
                logging.info(f"Advancing to the next stage (advance {advances}).")
                self.tap(result, log=False)
                sleep(_ADVANCE_SETTLE_SECONDS)
                continue
            else:
                logging.info(
                    f"Chờ {_START_SCREEN_WAIT_SECONDS}s để người dùng thay đổi "
                    "setting phù hợp"
                )
                sleep(_START_SCREEN_WAIT_SECONDS)
                logging.info("Starting adventure.")
            self.tap(result, log=False)
            sleep(_ADVENTURE_POLL_SECONDS)

        logging.warning("No Artifact Adventure screen detected, stopping.")

    def _fight_or_retreat(self, retreat: TemplateMatchResult) -> None:
        """Choose Fight or Retreat based on the on-screen win rate.

        Args:
            retreat: Match of the Retreat card, tapped when not fighting.
        """
        minimum = self.settings.artifact_adventure.min_win_rate_percent
        win_rate = self._read_win_rate()
        if win_rate is not None and win_rate >= minimum:
            fight = self.find_any_template([ARTIFACT_ADVENTURE_FIGHT_BUTTON])
            if fight is not None:
                logging.info(f"Win rate {win_rate}% >= {minimum}%, fighting.")
                self.tap(fight, log=False)
                return
            logging.warning("Fight button not found, retreating.")
        elif win_rate is None:
            logging.warning("Could not read the win rate, retreating.")
        else:
            logging.info(f"Win rate {win_rate}% < {minimum}%, retreating.")
        self.tap(retreat, log=False)

    def _read_win_rate(self) -> int | None:
        """Read the win rate from the Fight card (base + bonus).

        Returns:
            The sum of all percentages shown, or None if none could be read.
        """
        screenshot = self.get_screenshot()
        height, width = screenshot.shape[:2]
        crop = screenshot[
            int(height * _WIN_RATE_TOP) : int(height * _WIN_RATE_BOTTOM),
            int(width * _WIN_RATE_LEFT) : int(width * _WIN_RATE_RIGHT),
        ]
        text = RapidOCRBackend().extract_text(crop)
        values = [int(v) for v in _WIN_RATE_PATTERN.findall(text)]
        logging.debug(f"Win rate OCR: {text!r} -> {values}")
        return sum(values) if values else None

    def _open_pinball_screen(self) -> None:
        """Make sure the pinball screen is shown before an Events action.

        The camp screen shows the "Pinball" tab, the pinball screen shows the
        "Camp" tab (with or without the pinball icon above it). If the pinball screen is
        already open it is left as is; if the camp screen is open, switch over.

        Must be the first step of every command in the "Events" category.

        Raises:
            GameTimeoutError: Neither screen was recognised in time.
        """
        result = self.wait_for_any_template(
            [PINBALL_TAB, CAMP_TAB],
            timeout=_PINBALL_TAB_TIMEOUT_SECONDS,
            ensure_order=False,
            timeout_message="Neither camp nor pinball screen detected.",
        )
        if result.template != PINBALL_TAB:
            logging.info("Already on Pinball screen.")
            return

        logging.info("On camp screen, switching to Pinball screen.")
        self.tap(result, log=False)
        self.wait_for_any_template(
            [CAMP_TAB],
            timeout=_PINBALL_TAB_TIMEOUT_SECONDS,
            ensure_order=False,
            timeout_message="Pinball screen did not open.",
        )

    def _tap_common_button(self) -> bool:
        """Tap a button that may appear on any screen ("Mở Tất Cả", "OK").

        Returns:
            True if a button was tapped, False otherwise.
        """
        result = self.find_any_template(_COMMON_BUTTONS)
        if result is None or result.template not in _COMMON_BUTTON_LOG:
            return False
        logging.info(_COMMON_BUTTON_LOG[result.template])
        self.tap(result, log=False)
        return True
