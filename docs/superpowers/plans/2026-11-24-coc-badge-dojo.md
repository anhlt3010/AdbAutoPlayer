# CoC Võ Đường Huy Hiệu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `badge_dojo` command (category "Chế Độ") plays the yellow-button Võ Đường of the Huy Hiệu mode stage after stage with the formations of `tatari_dojo/`, gives a stage up after every formation lost `max_formation_attempts` times, goes to the next element, and logs a summary of all fights.

**Architecture:** The geometry of the preparation screen moves into a `PrepLayout` object (`BATTLE_LAYOUT` = today's values, `DOJO_LAYOUT` = the Võ Đường values); `DeployMixin` reads it from `self._layout`, so the tested deploy logic is reused. A new `BadgeDojoMixin` (`badge_dojo.py`, between `ClashOfCritters` and `AutoBattleMixin`) holds the navigation and the per-stage state machine and reuses the plan fields and `_play_plan_step` of `AutoBattleMixin`.

**Tech Stack:** Python 3.12, OpenCV, numpy, pytest, ruff; Clash of Critters game module in `src-tauri/src-python/adb_auto_player/games/clash_of_critters/`.

**Spec:** `docs/superpowers/specs/2026-11-24-coc-badge-dojo-design.md` (captures in `docs/superpowers/specs/assets/dojo_*.png`).

## Global Constraints

- Work from `N:/00_PersonalProject/AdbAuto-CoC/GIT/AdbAutoPlayer`; run pytest from `src-tauri/` as `uv run pytest src-python/tests/games/clash_of_critters/<file> -q`; run ruff as `uvx ruff check --fix` and `uvx ruff format` from the repo root. Run only the targeted test files, never the full suite; end every task with the pass count.
- Banned: `time.time` (use `monotonic`), `cv2.split`. No bare literals in comparisons (PLR2004): module constants. `X | None` typing.
- **`Point` equality is always true**: compare `(p.x, p.y)` in code and tests.
- Auto battle must behave as before: `test_battle_layout.py`, `test_deploy.py`, `test_formation_*.py`, `test_auto_battle_*.py` stay green.
- 1080x1920 only. Logs are Vietnamese like the rest of the module. No new settings (reuse `auto_battle.max_formation_attempts`, `idle_limit_seconds`, `poll_interval_seconds`).
- Edit files with CJK text through a small Python `replace` script when `Edit` fails to match.
- Do not commit unless the user asks; each task ends with a checkpoint (show the pass count), not a commit.
- Tests that need real captures read `docs/superpowers/specs/assets/` through `Path(__file__).parents[5] / "docs/superpowers/specs/assets"`.

## Review Focus

- A stage label that OCR cannot read on the dojo preparation screen: never fight blind; leave the Võ Đường after 3 unreadable polls (Task 6).
- A stage with no formation file: leave without fighting (Task 6).
- "Tiếp tục" after the last stage leads to a screen nobody knows: the idle limit ends only that element and the command goes on with the next one (Task 6).
- The field kept from the previous stage is never trusted: after a win the next stage clears and deploys even though the counter is above 0 (Task 6).
- Every tab grey: the command finishes without a fight and the summary lists all five as skipped (Task 7).

---

### Task 1: `PrepLayout`, `BATTLE_LAYOUT`, `DOJO_LAYOUT`

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/battle_layout.py`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_battle_layout.py` (add tests; existing ones unchanged)

**Interfaces:**
- Produces: `@dataclass(frozen=True) class PrepLayout` with fields `field_columns_x: tuple[int, ...]`, `field_rows_y: tuple[int, ...]`, `max_deployed: int`, `tray_columns_x: tuple[int, ...]`, `tray_rows_y: tuple[int, ...]`, `card_size: tuple[int, int]`, `tray_box: tuple[int, int, int, int]`, `card_band_rows: tuple[int, int]`, `card_width_range: tuple[int, int]`, `scroll_y: int`, `scroll_from_x: int`, `scroll_to_x: int`, `clear_field_point: Point`, `counter_box: tuple[int, int, int, int]`, `stage_label_box: tuple[int, int, int, int]`, `has_element_filter: bool`.
- Produces: `BATTLE_LAYOUT` (built from the existing module constants, which keep their names) and `DOJO_LAYOUT`. Dojo values: columns x `(429, 541, 654)`, rows y `(634, 747, 860, 974)`, `max_deployed=5`, tray columns x `(132, 337, 554, 771, 989)`, tray rows y `(1354, 1598)`, `card_size=(194, 232)`, `tray_box=(20, 1230, 1050, 1725)`, `card_band_rows=(1255, 1420)`, `card_width_range=(178, 198)`, `scroll_y=1468`, `scroll_from_x=900`, `scroll_to_x=400`, clear point `(1000, 1040)`, `counter_box=(100, 1130, 630, 1210)`, `stage_label_box=(500, 45, 640, 110)`, `has_element_filter=False`.
- Produces: the helpers `cell_center`, `tray_slots`, `card_box`, `find_card_lefts`, `cell_at`, `plan_drag` gain a **last** parameter `layout: PrepLayout = BATTLE_LAYOUT` (existing positional calls unchanged); `cell_center` raises `ValueError` outside the layout's rows and columns.

- [ ] **Step 1: Write the failing tests** in `test_battle_layout.py`: `test_dojo_cell_center_corners` (`(1,1)` is `(429, 634)`, `(4,3)` is `(654, 974)`); `test_dojo_cell_center_out_of_range` (`(5,1)` and `(1,4)` raise `ValueError` with `DOJO_LAYOUT`); `test_battle_layout_matches_module_constants` (`BATTLE_LAYOUT.field_columns_x == FIELD_COLUMNS_X`, `max_deployed == MAX_DEPLOYED`, `tuple(CARD_SIZE) == BATTLE_LAYOUT.card_size`); `test_dojo_tray_slots` (10 slots, first `(132, 1354)`, last `(989, 1598)`); `test_dojo_find_card_lefts_on_capture` (read `dojo_prep_cleared.png`; `find_card_lefts(img, DOJO_LAYOUT)` returns lefts whose first three are within 6 px of `35, 240, 457`; the clipped fifth card (left ~892) is absent); `test_dojo_plan_drag_is_steep_or_goes_through_free_cell` (a card at `(132, 1354)` to cell `(1, 3)` gives a path whose every first-to-last step satisfies `|dx| <= 0.5 |dy|` or has 3 points).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_battle_layout.py -q`. Expected: the new tests FAIL (names not defined).
- [ ] **Step 3: Implement** `PrepLayout`, the two layouts and the `layout` parameter in `battle_layout.py`; `find_card_lefts` takes `card_band_rows` and `card_width_range` from the layout (module constants `_CARD_BAND_ROWS`, `_CARD_WIDTH_RANGE` stay as the battle values).
- [ ] **Step 4: Run** the same command. Expected: all tests of the file PASS. Adjust the dojo card values only if the capture test shows they are off, and note the change in the spec.
- [ ] **Step 5: Checkpoint:** `uvx ruff check --fix` and `uvx ruff format` on the two files; show the pass count.

### Task 2: `DeployMixin` reads the layout

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/deploy.py`, `.../auto_battle.py` (`_read_stage` only)
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_deploy.py` (add tests; existing ones unchanged)

**Interfaces:**
- Consumes: Task 1 `PrepLayout`, `BATTLE_LAYOUT`, `DOJO_LAYOUT`, the `layout` parameter of the helpers.
- Produces: class attribute `DeployMixin._layout: PrepLayout = BATTLE_LAYOUT`. Every use of a layout constant in `deploy.py` (field cells and `MAX_DEPLOYED`, tray slots and rows, `TRAY_BOX`, scroll `y`/`x`, clear point, `COUNTER_BOX`, element filter) goes through `self._layout`. `_select_element` does nothing when `not self._layout.has_element_filter`. `_visible_cards` crops cards with `card_box(center, self._layout)` and, when `self._layout.card_size != BATTLE_LAYOUT.card_size`, resizes the crop with `cv2.resize(crop, BATTLE_LAYOUT.card_size)` before `recognizer.recognize`. `AutoBattleMixin._read_stage` uses `self._layout.stage_label_box`.

- [ ] **Step 1: Write the failing tests** in `test_deploy.py` (same bot fixture style as the file): `test_select_element_taps_nothing_without_filter` (`_layout = DOJO_LAYOUT`, `bot._select_element("grass")`, `bot.tap.assert_not_called()`); `test_dojo_visible_cards_resize_crop_to_battle_card_size` (mock `get_screenshot` to return `dojo_prep_cleared.png`, recognizer mock records the crop; every crop has shape `(190, 160, 3)` and there is one call per whole card per row); `test_dojo_clear_field_taps_dojo_point` (a `_deploy_formation` run with a mocked recognizer and zero-unit plan taps `(1000, 1040)`, compare `(x, y)`); `test_read_deployed_count_uses_layout_box` (OCR mock records the crop; with `DOJO_LAYOUT` its width is 530, with the default 200).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_deploy.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the changes above in `deploy.py` and `auto_battle.py`.
- [ ] **Step 4: Run** `test_deploy.py`, `test_auto_battle_flow.py`, `test_auto_battle_command.py`, `test_battle_layout.py`, `test_formation_stage.py`. Expected: all PASS (auto battle unchanged).
- [ ] **Step 5: Checkpoint:** ruff on the changed files; show the pass counts.

### Task 3: `load_dojo_formations`

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/formation.py`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_formation_load.py` (add tests)

**Interfaces:**
- Produces: `load_dojo_formations(root: Path, element: str, stage: StageId) -> tuple[Formation, ...]`. It reads `root / element / f"{stage}.json"`, follows `shared_with` (for example `"4-1 – 4-10"`) inside the same element folder for at most `_MAX_SHARE_HOPS` hops, and returns the formations with `Formation.stage` set to the asked stage. `load_formations` behaves as before (share the loop through a private helper taking the file path builder).

- [ ] **Step 1: Write the failing tests** with `tmp_path` JSON: `test_dojo_formations_read_the_element_folder` (`water/4-1.json` with one formation of 5 units, ask `("water", StageId(4, 1))` gives 1 formation with 5 units); `test_dojo_formations_follow_shared_with` (`grass/4-2.json` has `"formations": []` and `"shared_with": "4-1 – 4-10"`, `grass/4-1.json` has formations; asking stage 4-2 returns them and `.stage == StageId(4, 2)`); `test_dojo_formations_ignore_other_elements` (`fire/4-1.json` exists, asking grass returns `()`); `test_dojo_formations_missing_file_is_empty`; `test_dojo_real_data_has_five_units_in_grid` (real `tatari_dojo/` folder: for every element and every file name `<dojo>-<stage>` of that element, the loaded formations are non-empty, every formation has 5 units, rows within 1-4 and cols within 1-3).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_formation_load.py -q`. Expected: new tests FAIL.
- [ ] **Step 3: Implement** `load_dojo_formations` and the shared helper in `formation.py`.
- [ ] **Step 4: Run** `test_formation_load.py` and `test_formation_stage.py`. Expected: all PASS.
- [ ] **Step 5: Checkpoint:** ruff; show the pass counts.

### Task 4: Dojo helpers: tabs, button colour, summary

**Files:**
- Create: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/badge_dojo.py` (module-level parts only in this task)
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_badge_dojo_helpers.py`

**Interfaces:**
- Produces in `badge_dojo.py`: `DOJO_ELEMENTS = ("water", "fire", "grass", "rock", "lightning")`; `DOJO_ELEMENT_NAMES: dict[str, str]` (`Thủy`, `Hỏa`, `Thảo`, `Thạch`, `Lôi`); `DOJO_TAB_POINTS: dict[str, Point]` (x `125, 330, 540, 745, 955`, y `1720`); `CHALLENGE_POINT = Point(540, 1495)`; `DOJO_CLOSE_POINT = Point(540, 1845)`; `PREP_BACK_POINT = Point(85, 1800)`; `NEW_TRAIT_CLOSE_POINT = Point(540, 1600)`; `challenge_button_is_yellow(screenshot: np.ndarray) -> bool` (mean HSV of `screenshot[1445:1475, 345:420]`: hue 15-35, saturation above 150, value above 150); `@dataclass(frozen=True) class DojoFight: element: str; stage: str; formation: int; attempt: int; won: bool`; `format_dojo_summary(fights: Sequence[DojoFight], skipped: Sequence[str]) -> list[str]`.

- [ ] **Step 1: Write the failing tests:** `test_yellow_button_on_grass_capture` (`dojo_tabs_grass_yellow.png` gives True); `test_grey_button_on_rock_capture` (`dojo_tabs_rock_grey.png` gives False); `test_tab_points_cover_five_elements_in_order` (keys equal `DOJO_ELEMENTS`, x strictly increasing); `test_summary_lists_each_fight_and_totals`: for fights `[DojoFight("grass", "4-2", 1, 1, False), DojoFight("grass", "4-2", 1, 2, True), DojoFight("grass", "4-3", 1, 1, True)]` and skipped `["water", "fire"]`, the returned lines contain `"Thảo 4-2 | đội hình 1 | lần 1 | Thua"`, `"Thảo 4-2 | đội hình 1 | lần 2 | Thắng"`, `"Thảo 4-3 | đội hình 1 | lần 1 | Thắng"`, `"Thảo: 2 thắng, 1 thua"`, and `"Bỏ qua (nút Thử Thách xám): Thủy, Hỏa"`; `test_summary_without_fights` (no fights and all five skipped still returns a header and the skipped line, no crash).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_badge_dojo_helpers.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the module-level names above (docstrings are not required in `games/`).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Checkpoint:** ruff; show the pass count.

### Task 5: Templates

**Files:**
- Create: `templates/dojo_start_button.png`, `dojo_screen_title.png`, `dojo_retry_button.png`, `dojo_continue_button.png`, `dojo_defeat_back_button.png`, `dojo_new_trait_title.png` (all under `.../games/clash_of_critters/templates/`)
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_dojo_templates.py`

**Interfaces:**
- Produces: the six PNGs, cropped (text/static art only) from the captures; start approximate boxes `(left, top, right, bottom)` in the source capture: `dojo_start_button` from `dojo_stage_list.png` `(420, 1240, 660, 1305)`; `dojo_screen_title` from `dojo_tabs_grass_yellow.png` `(25, 20, 445, 105)` ("Võ Đường", the first word of every element's title); `dojo_retry_button` from `dojo_defeat.png` `(270, 1625, 510, 1700)`; `dojo_continue_button` from `dojo_victory.png` `(735, 1755, 960, 1825)`; `dojo_defeat_back_button` from `dojo_defeat.png` `(745, 1625, 950, 1700)`; `dojo_new_trait_title` from `dojo_new_trait_popup.png` `(755, 395, 1035, 520)`. Tighten a box if its test fails.

- [ ] **Step 1: Write the failing test** `test_template_matches_its_capture_and_not_the_others` parametrised over (template, source capture, other captures): `cv2.matchTemplate(..., TM_CCOEFF_NORMED)` max is at least 0.95 on the source and below 0.7 on every other capture of the list (`dojo_stage_list`, `dojo_defeat`, `dojo_victory`, `dojo_new_trait_popup`, `dojo_prep_cleared`, `dojo_tabs_grass_yellow`); extra case `test_screen_title_matches_rock_capture` (`dojo_screen_title` on `dojo_tabs_rock_grey.png` at least 0.9); `test_existing_templates_match_dojo_screens` (`victory_title.png` on `dojo_victory.png` at least 0.9, `defeat_title.png` on `dojo_defeat.png` at least 0.9, `quick_deploy_button.png` and `fight_button.png` on `dojo_prep_cleared.png` at least 0.9).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_dojo_templates.py -q`. Expected: FAIL (files missing).
- [ ] **Step 3: Crop** the six PNGs with a short throwaway script in the scratchpad directory (not in the repo): `cv2.imread` the capture, slice `[top:bottom, left:right]`, `cv2.imwrite` into `templates/`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Checkpoint:** show the pass count.

### Task 6: `BadgeDojoMixin`: the stage loop

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/badge_dojo.py`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_badge_dojo_flow.py`

**Interfaces:**
- Consumes: Tasks 1-5; from `AutoBattleMixin`: `_read_stage() -> StageId | None`, `_plan_stage`, `_plan_steps`, `_plan_pos`, `_plan_fights`, `_prep_phase`, `_play_plan_step(stage, is_boss, quick_deploy_button) -> bool`, `_tap_fight()`, `_wait_on_unknown_screen() -> bool`, `_tap_common_button()`; `load_dojo_formations`; templates `DEFEAT_TITLE`, `VICTORY_TITLE`, `QUICK_DEPLOY_BUTTON`, `FIGHT_BUTTON` from `auto_battle.py`.
- Produces: `class BadgeDojoMixin(AutoBattleMixin)` with `_play_dojo(self, element: str, fights: list[DojoFight]) -> None` and `_dojo_step(self, element: str, fights: list[DojoFight]) -> str` returning `"go"` or `"done"`; module constants `DOJO_START_BUTTON`, `DOJO_SCREEN_TITLE`, `DOJO_RETRY_BUTTON`, `DOJO_CONTINUE_BUTTON`, `DOJO_DEFEAT_BACK_BUTTON`, `DOJO_NEW_TRAIT_TITLE` (the file names of Task 5).
- Behaviour of `_dojo_step` (one `find_any_template([DEFEAT_TITLE, VICTORY_TITLE, QUICK_DEPLOY_BUTTON, DOJO_NEW_TRAIT_TITLE])` per call, after `_tap_common_button()`):
  - nothing found: `"done"` when `_wait_on_unknown_screen()` is False, else `"go"`.
  - new-trait popup: tap `NEW_TRAIT_CLOSE_POINT`; `"go"`.
  - preparation screen (quick-deploy button seen): if `_prep_phase` is not None, `_tap_fight()` and `"go"`. Otherwise read the stage; unreadable 3 polls in a row (counter `_dojo_unreadable`) leaves: tap `PREP_BACK_POINT`, `"done"`. A new stage (different from `_plan_stage`) loads `load_dojo_formations(self.template_dir.parent / "tatari_dojo", element, stage)`; none: warn, tap `PREP_BACK_POINT`, `"done"`; else set `_plan_stage`, `_plan_steps = list(formations)`, `_plan_pos = 0`, `_plan_fights = 0`. Then `_play_plan_step(stage, False, None)`; False: tap `PREP_BACK_POINT`, `"done"`.
  - victory: append `DojoFight(element, str(plan_stage), _plan_pos + 1, _plan_fights, True)`, set `_plan_stage = None` and `_prep_phase = None`, tap `DOJO_CONTINUE_BUTTON` if found; `"go"`.
  - defeat: append the same record with `won=False`, `_prep_phase = None`; if the plan is exhausted (`_plan_pos >= len(_plan_steps) - 1` and `_plan_fights >= settings.auto_battle.max_formation_attempts`) tap `DOJO_DEFEAT_BACK_BUTTON` and `"done"`, else tap `DOJO_RETRY_BUTTON` and `"go"`.
- `_play_dojo`: reset `_plan_stage = None`, `_plan_steps = None`, `_prep_phase = None`, `_idle_since = None`, `_dojo_unreadable = 0`; tap `CHALLENGE_POINT`; `wait_for_template(DOJO_START_BUTTON, timeout=10, ...)` and tap it; then loop `while self._dojo_step(...) == "go": sleep(poll_interval_seconds)`.

- [ ] **Step 1: Write the failing tests** (bot fixture: `object.__new__(ClashOfCritters)` with `find_any_template`, `wait_for_template`, `tap`, `_tap_common_button`, `_read_stage`, `_play_plan_step`, `_tap_fight`, `get_settings` mocked, `_layout` default; patch `badge_dojo.sleep` and `load_dojo_formations`): `test_new_trait_popup_is_tapped_away`; `test_prep_screen_loads_plan_and_plays_step` (stage `StageId(4, 2)`, loader returns one formation: `_play_plan_step` called with `(StageId(4, 2), False, None)` and `_plan_steps` has that formation); `test_unreadable_stage_leaves_after_three_polls` (Review Focus 1: three `_dojo_step` calls with `_read_stage` None, no fight tapped, the third returns `"done"` and taps `PREP_BACK_POINT`); `test_stage_without_formation_file_leaves_without_fighting` (Review Focus 2); `test_victory_records_and_continues` (record `DojoFight("grass", "4-2", 1, 1, True)`, continue button tapped, `_plan_stage` is None); `test_win_then_next_stage_deploys_although_field_has_units` (Review Focus 4: after a victory `_plan_stage` is None so the next preparation screen reloads the plan and calls `_play_plan_step` for the new stage, whatever the counter says); `test_defeat_retries_while_formations_remain` (taps retry, returns `"go"`); `test_defeat_on_exhausted_plan_goes_back_and_ends_dojo` (two formations, `_plan_pos == 1`, `_plan_fights == 3`: taps back button, `"done"`); `test_unknown_screen_idle_ends_only_the_element` (Review Focus 3: nothing found and `_wait_on_unknown_screen` returns False gives `"done"`, no exception); `test_play_dojo_taps_challenge_then_start`.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_badge_dojo_flow.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `BadgeDojoMixin` (`_play_dojo`, `_dojo_step`, helper `_plan_exhausted() -> bool`).
- [ ] **Step 4: Run** the same command and `test_artifact_adventure.py`. Expected: PASS.
- [ ] **Step 5: Checkpoint:** ruff; show the pass counts.

### Task 7: Navigation, tabs and the command

**Files:**
- Modify: `badge_dojo.py` (add `_open_badge_dojo`, `_enter_dojo_tab`, `_return_to_dojo_screen`, `_badge_dojo`, and move `MODES_BUTTON`, `BADGE_DOJO_BANNER`, `_MODES_TIMEOUT_SECONDS` here from `main.py`), `main.py` (inherit `BadgeDojoMixin` instead of `AutoBattleMixin`; `badge_dojo` calls `self._badge_dojo()`), `src-tauri/tauri.bundle.templates.json`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_badge_dojo.py` (rewrite to the new split), `test_badge_dojo_navigation.py`

**Interfaces:**
- Consumes: Tasks 4-6.
- Produces: `_open_badge_dojo(self) -> None` (wait for `MODES_BUTTON`, tap, wait for `BADGE_DOJO_BANNER`, tap: the body of today's command); `_enter_dojo_tab(self, element: str) -> bool` (tap `DOJO_TAB_POINTS[element]`, sleep 1 s, return `challenge_button_is_yellow(self.get_screenshot())`); `_return_to_dojo_screen(self) -> bool` (up to 15 polls of `find_any_template([DOJO_SCREEN_TITLE, DOJO_START_BUTTON, BADGE_DOJO_BANNER, MODES_BUTTON, DOJO_DEFEAT_BACK_BUTTON])`: title: True; start button (stage list): tap `DOJO_CLOSE_POINT`; banner: tap it; modes button: `_open_badge_dojo()`; back button: tap it; common buttons tapped first; False after the polls); `_badge_dojo(self) -> None` (`open_eyes(device_streaming=False)`, `self._layout = DOJO_LAYOUT` and back to `BATTLE_LAYOUT` in `finally`, `_open_badge_dojo()`, then for each element in `DOJO_ELEMENTS`: `_return_to_dojo_screen()` (False: log an error and stop), `_enter_dojo_tab` (False: remember the element name as skipped, continue), `_play_dojo`; at the end `logging.info` every line of `format_dojo_summary(fights, skipped_names)` with names from `DOJO_ELEMENT_NAMES`). The bundle file gets `"src-python/adb_auto_player/games/clash_of_critters/tatari_dojo/": "./games/clash_of_critters/tatari_dojo/"`.

- [ ] **Step 1: Write the failing tests:** `test_open_badge_dojo_taps_modes_then_banner` (from the current `test_taps_modes_button_then_banner`, calling `_open_badge_dojo`); `test_does_not_open_pinball_screen` and `test_command_is_in_che_do_category` kept (command name `badge_dojo`); `test_grey_tab_is_skipped_without_challenge_tap` (`challenge_button_is_yellow` patched False: `_enter_dojo_tab` returns False and `CHALLENGE_POINT` is never tapped); `test_all_tabs_grey_ends_without_a_fight` (Review Focus 5: `_play_dojo` never called, the summary lines include `"Bỏ qua (nút Thử Thách xám): Thủy, Hỏa, Thảo, Thạch, Lôi"`, use `caplog`); `test_layout_is_restored_after_the_run` (`_layout` is `BATTLE_LAYOUT` after `_badge_dojo`, also when `_play_dojo` raises); `test_return_to_dojo_screen_from_camp` (MODES_BUTTON seen first, then the title: `_open_badge_dojo` called, returns True); `test_return_to_dojo_screen_gives_up` (nothing ever found: False after 15 polls); `test_bundle_lists_tatari_dojo` (read `tauri.bundle.templates.json`, the key is present).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_badge_dojo.py src-python/tests/games/clash_of_critters/test_badge_dojo_navigation.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the methods, the move of the constants, the `main.py` change and the bundle entry.
- [ ] **Step 4: Run** the two files plus `test_badge_dojo_flow.py`, `test_badge_dojo_helpers.py`, `test_artifact_adventure.py`, `test_fishing_contest.py`. Expected: PASS.
- [ ] **Step 5: Checkpoint:** ruff on all changed files; show the pass counts.

### Task 8: Documentation and one live run (with the user)

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md`, `docs/superpowers/specs/2026-11-24-coc-badge-dojo-design.md` (a "Live run" section)

**Interfaces:**
- Consumes: Task 7 command `badge_dojo`.

- [ ] **Step 1: Update `CLAUDE.md`:** the category row of `badge_dojo`, a "Võ Đường Huy Hiệu" section (layouts, `tatari_dojo/` loader, template list, the flow, "Tiếp tục" goes straight to the next preparation screen and keeps the field, prep back arrow goes to the camp screen, the patch zip must also carry `badge_dojo.py` and the `tatari_dojo/` folder: add them to the file list of "Packaging a Patch Zip" and to `scripts/build_coc_patch.py` if it lists files by name).
- [ ] **Step 2: Ask the user** before touching the emulator, then run the command on the MuMu from the camp screen (`uv run python -m adb_auto_player` flow used for other commands, or the app) for one yellow Võ Đường and watch one stage: tab check, "Thử Thách", "Bắt đầu", stage read, clear and deploy (counter 5/5, row 1 is the row nearest the enemy), "Chiến Đấu", result handling. Record in the spec: where the prep back arrow and "Trở Về" lead, whether `DOJO_CLOSE_POINT` from the stage list returns to the Võ Đường screen, and any template or box that needed a change.
- [ ] **Step 3: Fix** what the live run shows (a failing behaviour gets a regression test first), then rerun the targeted test files and show the pass counts.
- [ ] **Step 4: Report** to the user: what was verified live, what was not (other elements, loss path, last stage), and offer the patch zip (`coc-patch` skill). Commit only if the user asks.
