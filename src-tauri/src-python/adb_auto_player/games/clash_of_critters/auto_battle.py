"""Auto battle of Clash of Critters: from the camp to the fight, again and again.

Every stage gets a plan of steps: a normal stage starts with the game's own Quick
Deploy, then comes each prepared formation of the stage (deployed by drag and
drop); a boss stage starts with its first formation. Each step is fought at most
``max_formation_attempts`` times. Fighting a step again never deploys again; the
next step does. When every step was lost the auto battle stops.
"""

import logging
from time import monotonic, sleep

from adb_auto_player.games.clash_of_critters.battle_layout import STAGE_LABEL_BOX
from adb_auto_player.games.clash_of_critters.deploy import DeployMixin
from adb_auto_player.games.clash_of_critters.formation import (
    Formation,
    StageId,
    is_boss_stage,
    load_formations,
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
# Pinball reward upgrade screen, which can open after a boss stage. It is recognised
# by the gem icon in the header of its reward cards (the number next to it changes);
# the "X" of the bottom bar closes it. That bar shows on other screens too (defeat,
# stage map, ...), so the X alone is never tapped.
PINBALL_REWARD_GEM = "pinball_reward_gem.png"
PINBALL_REWARD_CLOSE = "pinball_reward_close.png"
# "Đã Mở Khóa!" banner on a reward card that was just unlocked. It is tapped before
# the X, so the unlocked reward is claimed first.
PINBALL_REWARD_UNLOCKED = "pinball_reward_unlocked.png"
# Popup opened by that tap: the big "Đã Mở Khóa!" title and the "Xác Nhận" button.
# The button is only tapped together with the title ("Xác Nhận" shows elsewhere).
PINBALL_REWARD_UNLOCKED_TITLE = "pinball_reward_unlocked_title.png"
PINBALL_REWARD_CONFIRM = "pinball_reward_confirm.png"

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
    # The plan of the stage being played: its steps (None = Quick Deploy, else a
    # prepared formation), the step in progress and the fights played with it. Each
    # preparation screen that starts a fight counts as one fight.
    _plan_stage: StageId | None = None
    _plan_steps: list[Formation | None] | None = None
    _plan_pos: int = 0
    _plan_fights: int = 0
    # Preparation screens after a loss whose stage could not be read.
    _unreadable_losses: int = 0
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
        self._plan_stage = None
        self._plan_steps = None
        self._plan_pos = 0
        self._plan_fights = 0
        self._unreadable_losses = 0
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

        if self._tap_common_button() or self._close_pinball_reward_screen():
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
            self._plan_stage = None  # the stage is done: a new run of it starts over
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

    def _close_pinball_reward_screen(self) -> bool:
        """Handle the pinball reward upgrade screen.

        A card showing "Đã Mở Khóa!" is tapped first; once none is left the screen
        is closed with the X of the bottom bar.

        Returns:
            True if the screen was open and something was tapped.
        """
        if self.find_any_template([PINBALL_REWARD_UNLOCKED_TITLE]) is not None:
            confirm = self.find_any_template([PINBALL_REWARD_CONFIRM])
            if confirm is not None:
                logging.info("Pinball reward popup shown, confirming it.")
                self.tap(confirm, log=False)
                return True
        if self.find_any_template([PINBALL_REWARD_GEM]) is None:
            return False
        unlocked = self.find_any_template([PINBALL_REWARD_UNLOCKED])
        if unlocked is not None:
            logging.info("Pinball reward unlocked, tapping it.")
            self.tap(unlocked, log=False)
            return True
        close = self.find_any_template([PINBALL_REWARD_CLOSE])
        if close is None:
            return False
        logging.info("Pinball reward upgrade screen shown, closing it.")
        self.tap(close, log=False)
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

    def _count_unreadable_loss(self, lost_before: bool) -> bool:
        """Count a preparation screen after a loss whose stage was not readable.

        Returns:
            False once it happened more often than the limit allows.
        """
        if not lost_before:
            return True
        self._unreadable_losses += 1
        limit = self.settings.auto_battle.max_formation_attempts
        if self._unreadable_losses > limit:
            logging.warning(
                f"Unreadable stage was lost {self._unreadable_losses} times."
            )
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
        if stage is None:
            if not self._count_unreadable_loss(lost_before):
                return False
        else:
            self._unreadable_losses = 0
        is_boss = stage is not None and is_boss_stage(stage)
        if not lost_before and not is_boss and self._keep_formation():
            return True
        if stage is None:
            logging.warning("Stage unreadable, using Quick Deploy.")
            self._quick_deploy(quick_deploy_button)
            return True
        return self._play_plan_step(stage, is_boss, quick_deploy_button)

    def _plan_for(self, stage: StageId, is_boss: bool) -> None:
        """Make the plan of a stage the current one (built once per stage)."""
        if stage == self._plan_stage and self._plan_steps is not None:
            return
        formations = load_formations(
            self.template_dir.parent / "tatari_formations", stage
        )
        steps: list[Formation | None] = [] if is_boss else [None]
        steps.extend(formations)
        if not steps:
            logging.warning(f"No formation for stage {stage}, using Quick Deploy.")
            steps = [None]
        self._plan_stage = stage
        self._plan_steps = steps
        self._plan_pos = 0
        self._plan_fights = 0

    def _play_plan_step(
        self, stage: StageId, is_boss: bool, quick_deploy_button: object
    ) -> bool:
        """Start the next fight of the stage's plan.

        Returns:
            False when the auto battle should stop.
        """
        self._plan_for(stage, is_boss)
        steps = self._plan_steps or []
        if self._plan_fights >= self.settings.auto_battle.max_formation_attempts:
            self._plan_pos += 1
            self._plan_fights = 0
        if self._plan_pos >= len(steps):
            logging.warning(f"Stage {stage} was lost with every prepared formation.")
            return False
        step = steps[self._plan_pos]
        retry = self._plan_fights > 0
        self._plan_fights += 1

        if step is None:
            if not retry:
                self._quick_deploy(quick_deploy_button)
                return True
            self._prep_phase = _PHASE_QUICK
            self._formation_in_use = False
            self._tap_fight()
            return True

        if not retry or not self._field_has_units():
            if not self._deploy_current_step(stage):
                return False
        self._prep_phase = _PHASE_FORMATION
        self._formation_in_use = True
        self._tap_fight()
        return True

    def _deploy_current_step(self, stage: StageId) -> bool:
        """Deploy the current formation of the plan, filled completely.

        A formation that cannot be filled (after the fill rounds of the deploy)
        is dropped for the next formation of the plan, which starts a fresh count
        of fights.

        Args:
            stage: The stage being played.

        Returns:
            False when the auto battle should stop: nothing could be placed, or
            no formation is left that can be filled.
        """
        steps = self._plan_steps or []
        total = sum(1 for step in steps if step is not None)
        while True:
            step = steps[self._plan_pos]
            if step is None:  # Quick Deploy is never after a formation
                return True
            logging.info(
                f"Stage {stage}: đội hình {step.index + 1}/{total}, "
                f"lần đánh {self._plan_fights}/"
                f"{self.settings.auto_battle.max_formation_attempts}."
            )
            result = self._deploy_formation(step)
            if result.count == 0:
                logging.warning("No tatari could be deployed, stopping.")
                return False
            if result.complete:
                return True
            if self._plan_pos + 1 >= len(steps):
                logging.error(
                    f"Stage {stage}: không đội hình nào xếp đủ quân (đội hình "
                    f"{step.index + 1}: {result.count}/{result.needed}), dừng."
                )
                return False
            logging.warning(
                f"Stage {stage}: đội hình {step.index + 1} chỉ có "
                f"{result.count}/{result.needed} quân, đổi đội hình khác."
            )
            self._plan_pos += 1
            self._plan_fights = 1

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

    def _quick_deploy(self, quick_deploy_button: object) -> None:
        logging.info("Quick Deploy.")
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
