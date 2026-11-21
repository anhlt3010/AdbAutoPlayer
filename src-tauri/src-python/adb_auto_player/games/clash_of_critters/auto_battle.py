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
    Formation,
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
# The same button on later stages says "Tự Động Chiến Đấu" (two lines).
AUTO_FIGHT_BUTTON = "auto_fight_button.png"
# "Báo Cáo" icon above the tray; only shown once the stage was lost.
PREP_REPORT_ICON = "prep_report_icon.png"
DEFEAT_TITLE = "defeat_title.png"  # "Thất Bại"
RETRY_BUTTON = "retry_button.png"  # "Thử Lại"
VICTORY_TITLE = "victory_title.png"  # "CHIẾN THẮNG!"
CONTINUE_BUTTON = "continue_button.png"  # "Tiếp Tục", back to the stage map

_SCREENS = [
    DEFEAT_TITLE,
    VICTORY_TITLE,
    QUICK_DEPLOY_BUTTON,
    STAGE_MAP_MARKER,
    HUB_BATTLE_BUTTON,
]


_PHASE_QUICK = "quick"  # Quick Deploy was pressed on this preparation screen
_PHASE_FORMATION = "formation"  # the formation was deployed on this one
_PHASE_KEPT = "kept"  # the formation of the last win was kept on this one


class AutoBattleMixin(DeployMixin):
    """The screen state machine of the auto battle."""

    # What was done on the current preparation screen: nothing yet (None), Quick
    # Deploy (_PHASE_QUICK) or the formation (_PHASE_FORMATION). The screen is
    # polled every few seconds, so a visit lasts several steps.
    _prep_phase: str | None = None
    # The fight in progress uses a formation (deployed or kept), not Quick Deploy.
    _formation_in_use: bool = False
    # The last fight was won with a formation: the field is left as it is for the
    # next stages (until a boss, which has its own formation, or a loss).
    _keep_field: bool = False
    # Stages for which Quick Deploy was pressed in this run. A normal stage gets its
    # Quick Deploy first; its prepared formation is only used once that was not enough.
    _quick_deploy_stages: set[StageId] | None = None
    _formation_stage: StageId | None = None
    _formation_attempts: int = 0
    # Preparation screens after a loss, counted per stage whatever way they are
    # played (formation, Quick Deploy or an unreadable stage).
    _loss_stage: StageId | None = None
    _lost_visits: int = 0
    _idle_since: float | None = None
    # The same known screen seen again and again means the taps do nothing.
    _same_screen: str | None = None
    _same_screen_polls: int = 0

    def _tap_common_button(self) -> bool:
        """Tap a button that may appear on any screen (see ``ClashOfCritters``)."""
        raise NotImplementedError

    def _run_auto_battle(self) -> None:
        """Play until the game stops making progress or an attempt limit is hit."""
        self.open_eyes(device_streaming=False)
        self._prep_phase = None
        self._formation_in_use = False
        self._keep_field = False
        self._quick_deploy_stages = set()
        self._formation_stage = None
        self._formation_attempts = 0
        self._loss_stage = None
        self._lost_visits = 0
        self._idle_since = None
        self._same_screen = None
        self._same_screen_polls = 0
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
            self._same_screen = None
            return True

        screen = self.find_any_template(_SCREENS)
        if screen is None:
            return self._wait_on_unknown_screen()
        self._idle_since = None
        if self._is_stuck(screen.template):
            return False

        if screen.template == QUICK_DEPLOY_BUTTON:
            return self._prepare_and_fight(screen)

        # Any other known screen means the next preparation screen is a new visit.
        self._prep_phase = None
        if screen.template == DEFEAT_TITLE:
            self._keep_field = False
            self._formation_in_use = False
            retry = self.find_any_template([RETRY_BUTTON])
            if retry is not None:
                logging.info("Defeated, trying again.")
                self.tap(retry, log=False)
        elif screen.template == VICTORY_TITLE:
            self._keep_field = self._formation_in_use
            button = self.find_any_template([CONTINUE_BUTTON])
            if button is not None:
                logging.info("Victory, continuing to the stage map.")
                self.tap(button, log=False)
        elif screen.template == STAGE_MAP_MARKER:
            logging.info("On the stage map, opening the battle preparation.")
            self.tap(STAGE_MAP_START_POINT, log=False)
        else:
            logging.info("On the camp screen, opening the stage map.")
            self.tap(screen, log=False)
        return True

    def _is_stuck(self, template: str) -> bool:
        """Tell whether one known screen was seen poll after poll for too long."""
        if template != self._same_screen:
            self._same_screen = template
            self._same_screen_polls = 0
            return False
        self._same_screen_polls += 1
        battle = self.settings.auto_battle
        limit = max(
            1, battle.idle_limit_seconds // max(1, battle.poll_interval_seconds)
        )
        if self._same_screen_polls >= limit:
            logging.warning(f"Still on the same screen ({template}), stopping.")
            return True
        return False

    def _wait_on_unknown_screen(self) -> bool:
        """Count the time without a known screen (a fight, a win screen, ...)."""
        self._prep_phase = None
        self._same_screen = None
        now = monotonic()
        if self._idle_since is None:
            self._idle_since = now
            return True
        if now - self._idle_since >= self.settings.auto_battle.idle_limit_seconds:
            logging.warning("No known screen for a long time, stopping.")
            return False
        return True

    def _count_lost_visit(self, stage: StageId | None, lost_before: bool) -> bool:
        """Count a preparation screen that follows a loss.

        Returns:
            False once the stage was lost more often than the limit allows.
        """
        if stage != self._loss_stage:
            self._loss_stage = stage
            self._lost_visits = 0
        if not lost_before:
            return True
        self._lost_visits += 1
        limit = self.settings.auto_battle.max_formation_attempts
        if self._lost_visits > limit:
            logging.warning(f"Stage {stage} was lost {self._lost_visits} times.")
            return False
        return True

    def _prepare_and_fight(self, quick_deploy_button: object) -> bool:
        """Handle the battle preparation screen.

        Args:
            quick_deploy_button: The match of the Quick Deploy button.

        Returns:
            False when the auto battle should stop.
        """
        if self._prep_phase is not None:
            # This visit already started its fight: the fight just has not begun
            # yet (a slow transition). Press Fight again, never deploy again.
            self._tap_fight()
            return True

        stage = self._read_stage()
        lost_before = self.find_any_template([PREP_REPORT_ICON]) is not None
        if not self._count_lost_visit(stage, lost_before):
            return False
        is_boss = stage is not None and is_boss_stage(stage)
        if not lost_before and not is_boss and self._keep_formation():
            return True
        # Boss: its formation. Otherwise the formation only after Quick Deploy was
        # already pressed for this very stage (the report icon alone is not enough: the
        # stage may have been lost with something else).
        wants_formation = is_boss or self._quick_deploy_pressed(stage)

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
            self._quick_deploy(quick_deploy_button, stage)
            return True
        return self._deploy_and_fight(stage, formation)

    def _deploy_and_fight(self, stage: StageId, formation: Formation) -> bool:
        """Deploy the formation of a stage and start the fight.

        Returns:
            False when the auto battle should stop.
        """
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
        self._prep_phase = _PHASE_FORMATION
        self._formation_in_use = True
        self._tap_fight()
        return True

    def _keep_formation(self) -> bool:
        """Fight with the formation of the last win instead of Quick Deploy.

        Returns:
            False if there is nothing to keep (no win with a formation before, or
            the field is empty).
        """
        if not self.settings.auto_battle.keep_formation_after_win:
            return False
        if not self._keep_field or not self._field_has_units():
            return False
        logging.info("Keeping the formation of the last win.")
        self._prep_phase = _PHASE_KEPT
        self._formation_in_use = True
        self._tap_fight()
        return True

    def _quick_deploy_pressed(self, stage: StageId | None) -> bool:
        """Tell whether Quick Deploy was already pressed for a stage in this run."""
        return (
            stage is not None
            and self._quick_deploy_stages is not None
            and stage in self._quick_deploy_stages
        )

    def _quick_deploy(self, quick_deploy_button: object, stage: StageId | None) -> None:
        logging.info("Quick Deploy.")
        if stage is not None:
            if self._quick_deploy_stages is None:
                self._quick_deploy_stages = set()
            self._quick_deploy_stages.add(stage)
        self.tap(quick_deploy_button, log=False)
        self._prep_phase = _PHASE_QUICK
        self._formation_in_use = False

    def _field_has_units(self) -> bool:
        """Tell whether the field still holds the formation (the counter is above 0)."""
        return (self._read_deployed_count() or 0) > 0

    def _tap_fight(self) -> None:
        fight = self.find_any_template([FIGHT_BUTTON, AUTO_FIGHT_BUTTON])
        if fight is None:
            logging.warning("Fight button not found.")
            return
        logging.info("Fight.")
        self.tap(fight, log=False)
