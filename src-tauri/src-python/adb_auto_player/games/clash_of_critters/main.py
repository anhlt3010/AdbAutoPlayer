"""Clash of Critters Main Module."""

import logging
from time import sleep
from typing import NoReturn

from adb_auto_player.decorators import register_command, register_game
from adb_auto_player.game import Game
from adb_auto_player.games.clash_of_critters.settings import Settings
from adb_auto_player.models.decorators import GameGUIMetadata, GUIMetadata
from adb_auto_player.models.device import Resolution
from adb_auto_player.models.image_manipulation import CropRegions

# Templates are checked in this order; the first match decides the next action.
AUTO_BATTLING = "auto_battling.png"
AUTO_BATTLE_BUTTON = "auto_battle_button.png"
STAGE_START_BUTTON = "stage_start_button.png"
HUB_BATTLE_BUTTON = "hub_battle_button.png"
QUICK_DEPLOY_BUTTON = "quick_deploy_button.png"
DISLIKE_ICON = "dislike_icon.png"

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
