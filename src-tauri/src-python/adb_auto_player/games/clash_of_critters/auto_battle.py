"""Auto battle of Clash of Critters: from the camp to the fight, again and again.

On a normal stage the game's own Quick Deploy is used. After a lost fight (the
"Báo Cáo" icon shows) and on boss stages the prepared formation is deployed by
drag and drop instead.
"""

import logging
from time import monotonic, sleep

from adb_auto_player.games.clash_of_critters.battle_layout import STAGE_LABEL_BOX
from adb_auto_player.games.clash_of_critters.deploy import DeployMixin
from adb_auto_player.games.clash_of_critters.formation import (
    StageId,
    is_boss_stage,
    load_formation,
    parse_stage,
)
from adb_auto_player.models.geometry import Point
from adb_auto_player.ocr import RapidOCRBackend

HUB_BATTLE_BUTTON = "hub_battle_button.png"  # "Chiến Đấu" on the camp screen
# "Bản Đồ" button, shown on the stage map (the big yellow start button changes its
# label, so it is pressed at a fixed point instead).
STAGE_MAP_MARKER = "stage_map_marker.png"
STAGE_MAP_START_POINT = Point(540, 1690)
QUICK_DEPLOY_BUTTON = "quick_deploy_button.png"  # "Triển Khai Nhanh"
FIGHT_BUTTON = "fight_button.png"  # "Chiến Đấu" on the preparation screen
# "Báo Cáo" icon above the tray; only shown once the stage was lost.
PREP_REPORT_ICON = "prep_report_icon.png"
DEFEAT_TITLE = "defeat_title.png"  # "Thất Bại"
RETRY_BUTTON = "retry_button.png"  # "Thử Lại"

_SCREENS = [DEFEAT_TITLE, QUICK_DEPLOY_BUTTON, STAGE_MAP_MARKER, HUB_BATTLE_BUTTON]


class AutoBattleMixin(DeployMixin):
    """The screen state machine of the auto battle."""

    _quick_deployed: bool = False
    _formation_stage: StageId | None = None
    _formation_attempts: int = 0
    _idle_since: float | None = None

    def _tap_common_button(self) -> bool:
        """Tap a button that may appear on any screen (see ``ClashOfCritters``)."""
        raise NotImplementedError

    def _run_auto_battle(self) -> None:
        """Play until the game stops making progress or an attempt limit is hit."""
        self.open_eyes(device_streaming=False)
        self._quick_deployed = False
        self._formation_stage = None
        self._formation_attempts = 0
        self._idle_since = None
        while self._auto_battle_step():
            sleep(self.settings.auto_battle.poll_interval_seconds)
        logging.info("Auto battle stopped.")

    def _read_stage(self) -> StageId | None:
        """Read the stage number ("15-50") from the preparation screen."""
        left, top, right, bottom = STAGE_LABEL_BOX
        crop = self.get_screenshot()[top:bottom, left:right]
        return parse_stage(RapidOCRBackend().extract_text(crop))

    def _auto_battle_step(self) -> bool:
        """Look at the screen once and do what it asks for.

        Returns:
            False when the auto battle should stop.
        """
        if not self.is_game_running():
            logging.warning("Clash of Critters is not running, restarting.")
            self.start_game()
            sleep(self.settings.auto_battle.startup_wait_seconds)
            return True

        if self._tap_common_button():
            self._idle_since = None
            return True

        screen = self.find_any_template(_SCREENS)
        if screen is None:
            return self._wait_on_unknown_screen()
        self._idle_since = None

        if screen.template == QUICK_DEPLOY_BUTTON:
            return self._prepare_and_fight(screen)

        # Any other known screen means the next preparation screen is a new visit.
        self._quick_deployed = False
        if screen.template == DEFEAT_TITLE:
            retry = self.find_any_template([RETRY_BUTTON])
            if retry is not None:
                logging.info("Defeated, trying again.")
                self.tap(retry, log=False)
        elif screen.template == STAGE_MAP_MARKER:
            logging.info("On the stage map, opening the battle preparation.")
            self.tap(STAGE_MAP_START_POINT, log=False)
        else:
            logging.info("On the camp screen, opening the stage map.")
            self.tap(screen, log=False)
        return True

    def _wait_on_unknown_screen(self) -> bool:
        """Count the time without a known screen (a fight, a win screen, ...)."""
        self._quick_deployed = False
        now = monotonic()
        if self._idle_since is None:
            self._idle_since = now
            return True
        if now - self._idle_since >= self.settings.auto_battle.idle_limit_seconds:
            logging.warning("No known screen for a long time, stopping.")
            return False
        return True

    def _prepare_and_fight(self, quick_deploy_button: object) -> bool:
        """Handle the battle preparation screen.

        Args:
            quick_deploy_button: The match of the Quick Deploy button.

        Returns:
            False when the auto battle should stop.
        """
        stage = self._read_stage()
        lost_before = self.find_any_template([PREP_REPORT_ICON]) is not None
        wants_formation = lost_before or (stage is not None and is_boss_stage(stage))

        formation = None
        if wants_formation and stage is not None:
            formation = load_formation(
                self.template_dir.parent / "tatari_formations", stage
            )
            if formation is None:
                logging.warning(f"No formation for stage {stage}, using Quick Deploy.")
        elif wants_formation:
            logging.warning("Stage unreadable, using Quick Deploy.")

        if formation is None or stage is None:
            return self._quick_deploy_and_fight(quick_deploy_button)

        if stage != self._formation_stage:
            self._formation_stage = stage
            self._formation_attempts = 0
        limit = self.settings.auto_battle.max_formation_attempts
        if self._formation_attempts >= limit:
            logging.warning(f"Stage {stage} was lost {limit} times with the formation.")
            return False

        logging.info(f"Stage {stage}: deploying the prepared formation.")
        if self._deploy_formation(formation) == 0:
            logging.warning("No tatari could be deployed, stopping.")
            return False
        self._formation_attempts += 1
        self._tap_fight()
        return True

    def _quick_deploy_and_fight(self, quick_deploy_button: object) -> bool:
        if not self._quick_deployed:
            logging.info("Quick Deploy.")
            self.tap(quick_deploy_button, log=False)
            self._quick_deployed = True
            return True
        self._tap_fight()
        return True

    def _tap_fight(self) -> None:
        fight = self.find_any_template([FIGHT_BUTTON])
        if fight is None:
            logging.warning("Fight button not found.")
            return
        logging.info("Fight.")
        self.tap(fight, log=False)
