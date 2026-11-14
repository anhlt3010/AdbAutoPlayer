"""Clash of Critters Main Module."""

import logging
import re
from time import monotonic, sleep
from typing import NoReturn

from adb_auto_player.decorators import register_command, register_game
from adb_auto_player.game import Game
from adb_auto_player.games.clash_of_critters.settings import Settings
from adb_auto_player.models.decorators import GameGUIMetadata, GUIMetadata
from adb_auto_player.models.device import Resolution
from adb_auto_player.models.image_manipulation import CropRegions
from adb_auto_player.models.template_matching import TemplateMatchResult
from adb_auto_player.ocr import RapidOCRBackend

# Templates are checked in this order; the first match decides the next action.
AUTO_BATTLING = "auto_battling.png"
AUTO_BATTLE_BUTTON = "auto_battle_button.png"
STAGE_START_BUTTON = "stage_start_button.png"
HUB_BATTLE_BUTTON = "hub_battle_button.png"
QUICK_DEPLOY_BUTTON = "quick_deploy_button.png"
DISLIKE_ICON = "dislike_icon.png"
PINBALL_TAB = "pinball_tab.png"  # shown on the camp screen
# Shown on the pinball screen; the crop excludes the optional pinball-ball bubble.
CAMP_TAB = "camp_tab.png"
# Cat card on the pinball screen. Cropped to the ear/eye area only: the torch count,
# the number in the middle and the "ends in N days" label all change.
ARTIFACT_ADVENTURE_ICON = "artifact_adventure_icon.png"
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
_EVENT_ICON_TIMEOUT_SECONDS = 10
# Pause on the "new adventure" screen before pressing the start button.
_START_SCREEN_WAIT_SECONDS = 20
_ADVENTURE_POLL_SECONDS = 1
# Let the stage event start before looking again, so "Tiến Lên" is not pressed twice.
_ADVANCE_SETTLE_SECONDS = 3
# Stop when none of the adventure screens was seen for this long (e.g. out of torches).
_ADVENTURE_IDLE_LIMIT_SECONDS = 60

_PINBALL_TAB_TIMEOUT_SECONDS = 10

# Battle field on the preparation screen (y ~384-1094 of 1920); excludes the enemy
# panel and the hero cards, which contain other red icons.
_FORMATION_FIELD_CROP = CropRegions(top=0.2, bottom=0.43)

_NAVIGATION_LOG = {
    HUB_BATTLE_BUTTON: "On main screen, opening stage map.",
    STAGE_START_BUTTON: "On stage map, opening battle preparation.",
    AUTO_BATTLE_BUTTON: "On battle preparation, starting auto battle.",
}


@register_game(
    name="Clash of Critters",
    settings_file="ClashOfCritters.toml",
    gui_metadata=GameGUIMetadata(settings_class=Settings),
)
class ClashOfCritters(Game):
    def __init__(self) -> None:
        """Initialize ClashOfCritters."""
        super().__init__()
        self.base_resolution: Resolution = Resolution.from_string("1080x1920")
        self.package_name_prefixes = ["com.farlightgames.pgame.gp.vn"]
        self._quick_deploy_done = False

    @property
    def settings(self) -> Settings:
        return self.get_settings()

    def get_settings(self) -> Settings:
        return Settings.from_toml(self.settings_file_path)

    @register_command(
        gui=GUIMetadata(
            label="Tự Chiến Đấu",
            category="Battle",
            tooltip=(
                "Restart the game if it closes and re-enter auto battle "
                "from the main screen."
            ),
        )
    )
    def keep_game_running(self) -> NoReturn:
        self.open_eyes(device_streaming=False)
        while True:
            self._keep_alive_tick()
            sleep(self.settings.keep_alive.check_interval_seconds)

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

    def _keep_alive_tick(self) -> None:
        """Run one check: restart the game or re-enter battle if needed."""
        if not self.is_game_running():
            logging.warning("Clash of Critters is not running, restarting.")
            self.start_game()
            sleep(self.settings.keep_alive.startup_wait_seconds)
            return

        result = self.find_any_template(
            [AUTO_BATTLING, AUTO_BATTLE_BUTTON, STAGE_START_BUTTON, HUB_BATTLE_BUTTON]
        )
        if result is not None and result.template != AUTO_BATTLE_BUTTON:
            # Left the battle preparation screen, allow Quick Deploy next time.
            self._quick_deploy_done = False
        if result is None or result.template == AUTO_BATTLING:
            return

        if result.template == AUTO_BATTLE_BUTTON and self._quick_deploy_if_needed():
            return

        logging.info(_NAVIGATION_LOG[result.template])
        self.tap(result, log=False)

    def _quick_deploy_if_needed(self) -> bool:
        """Press Quick Deploy once if the formation shows too many Dislike icons.

        Returns:
            True if Quick Deploy was pressed, False otherwise.
        """
        if self._quick_deploy_done:
            return False

        dislike_count = len(
            self.find_all_template_matches(
                DISLIKE_ICON, crop_regions=_FORMATION_FIELD_CROP
            )
        )
        threshold = self.settings.keep_alive.dislike_icon_threshold
        if dislike_count < threshold:
            return False

        button = self.find_any_template([QUICK_DEPLOY_BUTTON])
        if button is None:
            logging.warning("Quick Deploy button not found.")
            return False

        logging.info(
            f"Unfavorable formation ({dislike_count} Dislike icons), "
            "pressing Quick Deploy."
        )
        self._quick_deploy_done = True
        self.tap(button, log=False)
        return True
