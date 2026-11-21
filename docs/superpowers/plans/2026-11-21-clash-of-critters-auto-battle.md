# Clash of Critters Auto Battle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old "Tu Chien Dau" loop with an `auto_battle` command that reads the stage, uses Quick Deploy first, and deploys the prepared formation by drag and drop on boss stages or after a loss.

**Architecture:** Pure-logic modules (stage parsing, formation loading, deployment planning, tatari database, screen layout) are tested without a device. Two Game mixins (`DeployMixin` for tray/field work, `AutoBattleMixin` for the screen state machine) use them; `ClashOfCritters` in `main.py` registers the command. Card recognition filters `tatari_db` sprites by element, then matches the card art, with a per-profile JSON cache.

**Tech Stack:** Python 3.12, OpenCV/numpy, RapidOCR (`RapidOCRBackend`), pydantic settings, pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-clash-of-critters-auto-battle-design.md` (real screens in `docs/superpowers/specs/assets/`).

## Global Constraints

- All paths below are relative to the repo root `N:/00_PersonalProject/AdbAuto-CoC/GIT/AdbAutoPlayer`; package dir `P = src-tauri/src-python/adb_auto_player/games/clash_of_critters`; tests dir `T = src-tauri/src-python/tests/games/clash_of_critters`.
- Run pytest from `src-tauri/` on the targeted files only, never the full suite: `uv run pytest src-python/tests/games/clash_of_critters/<file>.py -q`. Report the pass count of the targeted files at the end.
- Before every commit run from the repo root: `uvx ruff check --fix` then `uvx ruff format`.
- Ruff rules: line length 88, Google docstrings (not required under `games/` and `tests/`), no `time.time` (use `time.monotonic`), no bare literals in comparisons (module constants), modern type hints (`X | None`, `list[str]`).
- Game resolution is fixed 1080x1920 (`base_resolution`). Stage format `"<chapter>-<number>"`, boss = `number % 10 == 0`.
- Never edit or delete `P/tatari_db/` or `P/tatari_formations/` (user data, untracked in git).
- Keep `_tap_common_button`, `_COMMON_BUTTONS`, Artifact Adventure, Zobo Hunt, `_open_pinball_screen` and their templates working; `T/test_artifact_adventure.py` must keep passing.
- Commit messages end with the attribution line given by the session's system reminder.

## Review Focus

Inputs the spec implies but its main flow does not exercise; each is pinned by a test in the task named.

- Stage has no formation file (chapter 4 has 1 file, chapter 5 has 58): fall back to Quick Deploy, do not crash (Task 3, Task 8).
- `shared_with` points to a missing file or to itself: use the stage's own file, or none (Task 3).
- OCR returns garbage or empty text for the stage ("15-5O", ""): stage unknown, boss rule not applied, Quick Deploy mode (Task 2, Task 8).
- A planned tatari is not owned at all, or the formation lists more than 15 units: empty cell logged, at most 15 drags (Task 4, Task 7).
- The formation was already tried `max_formation_attempts` times and lost again, or an unknown (win) screen is shown: stop with a warning instead of looping (Task 8).

---

### Task 1: Remove the old battle handling and add the new settings

**Files:**
- Modify: `P/main.py`, `P/settings.py`, `src-tauri/settings/ClashOfCritters.toml`, `P/README.md`, `P/CLAUDE.md`
- Delete: `T/test_keep_game_running.py`, `P/templates/auto_battling.png`, `P/templates/auto_battle_button.png`, `P/templates/dislike_icon.png`
- Test: `T/test_auto_battle_settings.py`

**Interfaces:**
- Produces: `AutoBattleSettings` in `P/settings.py` with fields `poll_interval_seconds` (int 1-60, default 2), `startup_wait_seconds` (int 5-300, default 30), `idle_limit_seconds` (int 30-900, default 120), `max_formation_attempts` (int 1-20, default 3); `Settings.auto_battle: AutoBattleSettings` (title "Tự Động Chiến Đấu").

- [ ] **Step 1: Write the failing test** `test_auto_battle_settings.py`: `test_defaults` asserts the four defaults above; `test_bounds_rejected` asserts `AutoBattleSettings(max_formation_attempts=0)` and `AutoBattleSettings(idle_limit_seconds=10)` raise `pydantic.ValidationError`; `test_old_keep_alive_removed` asserts `"keep_alive" not in Settings.model_fields`.
- [ ] **Step 2: Run it** `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_settings.py -q`. Expected: FAIL (`AutoBattleSettings` not importable).
- [ ] **Step 3: Delete from `main.py`**: `keep_game_running`, `_keep_alive_tick`, `_quick_deploy_if_needed`, `_quick_deploy_done`, `_NAVIGATION_LOG`, `_FORMATION_FIELD_CROP`, constants `AUTO_BATTLING`, `AUTO_BATTLE_BUTTON`, `DISLIKE_ICON`, and the imports they leave unused (`NoReturn`, `CropRegions`). Keep `STAGE_START_BUTTON`, `HUB_BATTLE_BUTTON`, `QUICK_DEPLOY_BUTTON`, `_tap_common_button`. Delete `KeepAliveSettings` and its `*Seconds`/`DislikeIconThreshold` aliases from `settings.py`; add `AutoBattleSettings` and the `auto_battle` field. In `ClashOfCritters.toml` replace the `[keep_alive]` block with `[auto_battle]` holding the four defaults. Delete the listed old test and templates. Remove the Battle row and the keep-alive text in `P/CLAUDE.md` and `P/README.md`.
- [ ] **Step 4: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_settings.py src-python/tests/games/clash_of_critters/test_artifact_adventure.py -q`. Expected: all pass (the adventure tests prove the shared code survived). Also run `Grep` for `keep_alive|_quick_deploy|AUTO_BATTLING|DISLIKE_ICON` under `P/` and `T/`: no matches.
- [ ] **Step 5: Commit** `refactor: remove old Clash of Critters auto battle loop`.

### Task 2: Stage parsing and boss rule

**Files:**
- Create: `P/formation.py`
- Test: `T/test_formation_stage.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) StageId(chapter: int, number: int)` with `__str__` returning `"15-50"`; `parse_stage(text: str) -> StageId | None`; `is_boss_stage(stage: StageId) -> bool`.

- [ ] **Step 1: Write the failing tests**: `parse_stage("15-50") == StageId(15, 50)`; `parse_stage(" 4 - 7 ") == StageId(4, 7)`; `parse_stage("Cấp 399 15-50") == StageId(15, 50)`; garbage `"15-5O"`, `""`, `"abc"` give `None`; `is_boss_stage` is True for `StageId(15, 10)`, `StageId(15, 50)`, `StageId(76, 80)` and False for `StageId(15, 49)`, `StageId(15, 1)`.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_formation_stage.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `StageId`, `parse_stage` (regex `(\d{1,2})\s*-\s*(\d{1,3})`; return the first match or `None`) and `is_boss_stage` (module constant `_BOSS_EVERY = 10`) in `P/formation.py`.
- [ ] **Step 4: Run the same tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: parse Clash of Critters stage ids`.

### Task 3: Formation loading

**Files:**
- Modify: `P/formation.py`
- Test: `T/test_formation_load.py`

**Interfaces:**
- Consumes: `StageId` (Task 2).
- Produces: `@dataclass(frozen=True) FormationUnit(row: int, col: int, tatari_id: str, evolution_id: str, tier: int, glitter: bool)`; `@dataclass(frozen=True) Formation(stage: StageId, units: tuple[FormationUnit, ...])`; `load_formation(root: Path, stage: StageId) -> Formation | None` where `root` is the `tatari_formations` folder and the file is `root/<chapter>/<chapter>-<number>.json`.

- [ ] **Step 1: Write the failing tests** with JSON written to `tmp_path` in the real file shape (`chapter`, `stage`, `level`, `shared_with`, `units[]` with `row`, `col`, `tatari_id`, `evolution_id`, `name`, `tier`, `glitter`): `test_loads_units` (two units, assert `units[0] == FormationUnit(1, 1, "grass-4", "grass-4-2", 2, False)`); `test_missing_file_returns_none`; `test_shared_with_other_stage_loads_that_file` (15-2 says `shared_with: "15-1"` and has no units of its own: result has 15-1's units, `stage == StageId(15, 2)`); `test_shared_with_self_uses_own_units`; `test_shared_with_missing_file_returns_none`; `test_shared_with_loop_returns_none` (A shares B, B shares A). Add `test_real_boss_file_loads` that loads `P/tatari_formations` stage `15-50` and asserts at least one unit and every `1 <= row, col <= 5`; skip it with `pytest.mark.skipif` when the folder is missing.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_formation_load.py -q`. Expected: FAIL (names missing).
- [ ] **Step 3: Implement** `FormationUnit`, `Formation`, `load_formation`. Follow `shared_with` (parse it with `parse_stage`) at most `_MAX_SHARE_HOPS = 5` hops; a file with no `units` and no valid share target yields `None`.
- [ ] **Step 4: Run the same tests.** Expected: PASS (real-file test passes or is skipped).
- [ ] **Step 5: Commit** `feat: load Clash of Critters formations`.

### Task 4: Deployment planning with substitution

**Files:**
- Create: `P/deployment_plan.py`
- Test: `T/test_deployment_plan.py`

**Interfaces:**
- Consumes: `Formation`, `FormationUnit` (Task 3).
- Produces: `split_evolution_id(evolution_id: str) -> tuple[str, int, bool]` (`"water-3-2g"` gives `("water-3", 2, True)`, `"grass-4-2"` gives `("grass-4", 2, False)`); `@dataclass(frozen=True) Placement(unit: FormationUnit, evolution_id: str | None)`; `plan_deployment(formation: Formation, owned: Collection[str], max_units: int = 15) -> list[Placement]`. `owned` holds `tatari_db` evolution ids (glitter ids end in `g`). Each owned id is used at most once; placements keep the file order and are cut to `max_units`.

- [ ] **Step 1: Write the failing tests** (build units with a helper): exact id owned gives that id; glitter wanted but only normal owned gives the normal id; wanted `grass-4-2` and owned `grass-4-3` gives `grass-4-3`; wanted tier 2 with owned tiers 1 and 3 gives tier 3 (higher wins a tie); wanted tier 3 with owned tiers 1 and 2 gives tier 2 (nearest); same `tatari_id` not owned gives `evolution_id is None`; two units wanting the same id, one owned copy: the first unit gets it and the second gets `None` (or a substitute of the same family if another is owned); 17 units with everything owned returns 15 placements; `split_evolution_id` examples above.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_deployment_plan.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** with the priority from the spec: exact id and glitter, then same evolution ignoring glitter, then same `tatari_id` by smallest tier distance with higher tier winning ties. Log a warning per `None` placement.
- [ ] **Step 4: Run the same tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: plan Clash of Critters formation deployment`.

### Task 5: Tatari database and screen layout

**Files:**
- Create: `P/tatari_db.py`, `P/battle_layout.py`
- Test: `T/test_tatari_db.py`, `T/test_battle_layout.py`

**Interfaces:**
- Produces in `tatari_db.py`: `@dataclass(frozen=True) Sprite(evolution_id: str, tatari_id: str, element: str, tier: int, glitter: bool, image_path: Path)` (`element` lowercase: `fire`, `water`, `grass`, `rock`, `lightning`); `TatariDb.load(root: Path) -> TatariDb` reading `root/tatari_db.json`; `TatariDb.sprites_for_element(element: str) -> list[Sprite]` (normal and glitter forms, glitter id keeps the `g`); `TatariDb.get(evolution_id: str) -> Sprite | None`.
- Produces in `battle_layout.py` (all `Point` values 1080x1920): `cell_center(row: int, col: int) -> Point` (1-based; x from `(300, 420, 540, 660, 780)`, y from `(490, 610, 730, 850, 970)`, `ValueError` outside 1-5); `tray_slots() -> list[Point]` (row-major, x `(110, 288, 466, 644, 822, 1000)`, y `(1285, 1480)`); `CLEAR_FIELD_POINT = Point(1000, 880)`; `MAX_DEPLOYED = 15`; `STAGE_LABEL_BOX`, `COUNTER_BOX`, `CARD_ART_SIZE`, `ELEMENT_ICON_OFFSET` as pixel boxes/offsets (calibrate in Step 3 against `docs/superpowers/specs/assets/prep_screen_cleared.png` and `prep_screen_deployed.png`).

- [ ] **Step 1: Write the failing tests**: `test_db_loads_real_file` (skip if missing) asserts 260 evolutions across 5 elements, `get("water-3-3g")` has `glitter is True` and `tier == 3`, every `image_path` exists; `test_db_small_json` in `tmp_path` using the real schema (`tatari_id`, `type: "Water"`, `has_glitter`, `evolutions[].normal/glitter{id,name,image}`) asserts element lowercasing and that `sprites_for_element("water")` contains both `water-3-1` and `water-3-1g`; `test_cell_center_corners` asserts `cell_center(1, 1) == Point(300, 490)` and `cell_center(5, 5) == Point(780, 970)`; `test_cell_center_out_of_range` asserts `ValueError` for `(0, 1)` and `(1, 6)`; `test_tray_slots_count_and_order` asserts 12 slots, first `Point(110, 1285)`, seventh `Point(110, 1480)`.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_tatari_db.py src-python/tests/games/clash_of_critters/test_battle_layout.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** both modules. Crop the boxes from the asset screenshots with a throwaway script to confirm the stage label, counter ("Đã triển khai: n/15") and a card art region contain what they should; record the confirmed boxes in `battle_layout.py`.
- [ ] **Step 4: Run the same tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add tatari database and battle screen layout`.

### Task 6: Card recognition

**Files:**
- Create: `P/card_recognition.py`, `T/data/prep_screen_cleared.png` (copy of the spec asset)
- Test: `T/test_card_recognition.py`

**Interfaces:**
- Consumes: `TatariDb`, `Sprite` (Task 5); layout constants (Task 5).
- Produces: `ELEMENTS: tuple[str, ...]`; `classify_element(icon_bgr: np.ndarray) -> str | None` (colour of the top-left element icon); `card_art_key(card_bgr: np.ndarray) -> str` (stable perceptual hash of the art region); `RecognitionCache(path: Path)` with `get(key: str) -> str | None`, `put(key: str, evolution_id: str) -> None`, `save() -> None` (JSON, tolerant of a missing or corrupt file); `CardRecognizer(db: TatariDb, cache: RecognitionCache, threshold: float = 0.6)` with `recognize(card_bgr: np.ndarray) -> str | None` (cache hit, else element filter then multi-scale alpha-masked match against that element's sprites, best score at or above `threshold`, else `None` and the crop saved under a debug folder).

- [ ] **Step 1: Write the failing tests** using card crops cut from `T/data/prep_screen_cleared.png` with `tray_slots()` and the layout card size: `test_classify_element_of_visible_cards` asserts the 12 visible cards classify, in row-major order, as `rock, rock, water, water, lightning, water, lightning, grass, fire, grass, rock, water` (read from the screenshot; the 6th and 12th cards are cut off at the right edge, verify them visually first and correct the list if the icon says otherwise); `test_recognize_known_cards` asserts the third card (white and blue yeti) returns `"water-3-3"` and the 11th card (brown dino with blue crest) returns `"rock-3-2"`, and that every other visible card returns an id whose `Sprite.element` equals its classified element (verify the two named ids visually against `tatari_db/images` first; if the matcher disagrees with a sprite that truly differs, fix the matcher, not the expectation); `test_recognize_returns_none_for_blank_card` (flat orange image gives `None`); `test_cache_roundtrip` (put, save, reload from the same path, get returns the id; corrupt file loads as empty); `test_cache_hit_skips_matching` (spy on the matcher: second `recognize` of the same crop does not call it).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_card_recognition.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `card_recognition.py`. Choose the matcher (alpha-masked `cv2.matchTemplate` over a few scales vs ORB features) by trying both on the 12 real cards; evolutions of one family look alike, so check each result against its neighbours' scores. Pick the threshold from the observed score gap and note it in a code comment.
- [ ] **Step 4: Run the same tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: recognize Clash of Critters tray cards`.

### Task 7: Tray scanning and formation deployment

**Files:**
- Create: `P/deploy.py`
- Test: `T/test_deploy.py`

**Interfaces:**
- Consumes: `Formation`, `plan_deployment`, `Placement` (Tasks 3-4); `CardRecognizer`, layout constants (Tasks 5-6).
- Produces `DeployMixin` (Game mixin; `get_screenshot`, `tap`, `device.swipe`, `_apply_vertical_offset`, `sleep` come from `Game`/the module) with:
  - `_visible_cards() -> list[tuple[Point, str | None]]`: slot centre and recognized id for each visible tray card.
  - `_scroll_tray(forward: bool) -> bool`: swipe the tray horizontally, return False when the tray did not move (compare the tray region before and after).
  - `_scan_owned() -> set[str]`: scroll from the start to the end collecting ids, then scroll back to the start.
  - `_locate_card(evolution_id: str) -> Point | None`: scan visible cards, scrolling until found or the end.
  - `_drag_card(card: Point, cell: Point) -> None`: `self.device.swipe(...)` from the card to the cell with a drag duration constant calibrated in Step 3.
  - `_read_deployed_count() -> int | None`: OCR of `COUNTER_BOX`, parse `(\d+)\s*/\s*15`.
  - `_deploy_formation(formation: Formation) -> int`: tap `CLEAR_FIELD_POINT`, confirm count 0, `plan_deployment(formation, self._scan_owned())`, locate and drag each placed card to `cell_center(unit.row, unit.col)`, log expected vs actual count, return the actual count (0 when nothing could be placed).

- [ ] **Step 1: Write the failing tests** with a stub class (`object.__new__` plus `MagicMock` for `tap`, `device`, `_visible_cards`, `_scroll_tray`, `_read_deployed_count`, `_apply_vertical_offset`, patched `sleep`): `test_clear_tapped_before_any_drag` (first call is `tap(CLEAR_FIELD_POINT, ...)`); `test_drags_each_owned_unit_to_its_cell` (two placements, assert two `_drag_card` calls with `cell_center(1, 1)` and `cell_center(2, 3)`); `test_unowned_unit_is_skipped` (placement with `None`: no drag for it, others still dragged); `test_scrolls_until_card_found` (card visible only after two scrolls: `_scroll_tray` called twice); `test_scroll_stops_at_tray_end` (`_scroll_tray` returns False: `_locate_card` returns `None`); `test_nothing_deployable_returns_zero_and_no_drag` (all `None`); `test_at_most_15_drags` (17 units fully owned); `test_read_deployed_count_parses` (OCR text `"Đã triển khai: 12/15"` gives 12, garbage gives `None`).
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_deploy.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `deploy.py`. Calibrate the scroll swipe distance, the drag duration and settle delays against the live emulator (`127.0.0.1:16384`, adb binary `src-tauri/src-python/adb_auto_player/binaries/adb.exe`): deploy one real card by drag and confirm the counter changes. Record the confirmed constants in `battle_layout.py`.
- [ ] **Step 4: Run the same tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: deploy Clash of Critters formations by drag and drop`.

### Task 8: Auto battle state machine

**Files:**
- Create: `P/auto_battle.py`; new templates in `P/templates/`: `prep_report_icon.png` ("Báo cáo" icon), `defeat_title.png` ("Thất Bại"), `retry_button.png` ("Thử Lại" text), `fight_button.png` ("Chiến Đấu" on the prep screen); re-check `hub_battle_button.png`, `stage_start_button.png`, `quick_deploy_button.png` against the assets and re-crop any that no longer match.
- Test: `T/test_auto_battle_flow.py`

**Interfaces:**
- Consumes: `parse_stage`, `is_boss_stage`, `load_formation` (Tasks 2-3), `DeployMixin._deploy_formation` (Task 7), `AutoBattleSettings` (Task 1), `_tap_common_button`.
- Produces `AutoBattleMixin` with `_read_stage() -> StageId | None` (OCR of `STAGE_LABEL_BOX`, then `parse_stage`), `_auto_battle_step() -> bool` (one iteration; False means stop) and `_run_auto_battle() -> None` (loop: `open_eyes`, step, `sleep(poll_interval_seconds)`). Template constants in `main.py`: `PREP_REPORT_ICON`, `DEFEAT_TITLE`, `RETRY_BUTTON`, `FIGHT_BUTTON`. Step order: game not running (`is_game_running`, then `start_game` and `sleep(startup_wait_seconds)`); common buttons; `DEFEAT_TITLE` then tap `RETRY_BUTTON`; preparation screen (recognized by `QUICK_DEPLOY_BUTTON`); `STAGE_START_BUTTON`; `HUB_BATTLE_BUTTON`; nothing recognized: keep waiting until `idle_limit_seconds`, then log a warning and return False.
- Preparation screen: read the stage with `RapidOCRBackend` on `STAGE_LABEL_BOX` and `parse_stage`; formation mode when the stage is a boss or `PREP_REPORT_ICON` is visible, otherwise tap `QUICK_DEPLOY_BUTTON` once per visit; then tap `FIGHT_BUTTON`. Formation mode loads `tatari_formations` via `self.template_dir.parent / "tatari_formations"`; no formation file means Quick Deploy mode plus a warning. Track `(stage, formation_attempts)`: each formation fight increments it, a different stage resets it, and exceeding `max_formation_attempts` logs a warning and returns False. A formation deploy that placed 0 cards does not press fight and returns False.

- [ ] **Step 1: Capture templates.** Crop the text-only regions from `docs/superpowers/specs/assets/defeat_screen.png`, `prep_screen_cleared.png` and `stage_map_screen.png` with a throwaway script (keep the dynamic parts out, as `P/CLAUDE.md` describes for other templates). `prep_report_icon.png` is not in the assets: on the live emulator the game is at the defeat screen of 15-50; tap "Thử Lại", screenshot the preparation screen, and crop the "Báo cáo" icon above the tray. Verify each template matches its source screenshot with `find_template` and does not match the other screens.
- [ ] **Step 2: Write the failing tests** with a stub (`find_any_template`, `tap`, `is_game_running`, `start_game`, `get_screenshot`, `_deploy_formation`, `_read_stage` as mocks, patched `sleep`, `monotonic`, `load_formation`): `test_restarts_game_when_not_running`; `test_taps_hub_then_stage_start`; `test_normal_stage_uses_quick_deploy_once_then_fight` (stage 15-49, no report icon: taps `QUICK_DEPLOY_BUTTON` then `FIGHT_BUTTON`, no `_deploy_formation`; a second step in the same visit does not tap quick deploy again); `test_boss_stage_deploys_formation` (15-50); `test_report_icon_forces_formation_on_normal_stage` (15-49 with report icon); `test_unreadable_stage_falls_back_to_quick_deploy` (`_read_stage` returns `None`); `test_missing_formation_falls_back_to_quick_deploy` (`load_formation` returns `None`); `test_defeat_taps_retry`; `test_formation_attempts_capped` (`max_formation_attempts=2`: third formation visit on the same stage returns False); `test_attempts_reset_on_new_stage`; `test_zero_deployed_does_not_fight` (`_deploy_formation` returns 0: no tap on `FIGHT_BUTTON`, step returns False); `test_common_button_takes_priority`; `test_stops_after_idle_limit_on_unknown_screen` (nothing recognized for longer than `idle_limit_seconds` returns False; before that it returns True).
- [ ] **Step 3: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_flow.py -q`. Expected: FAIL.
- [ ] **Step 4: Implement** `auto_battle.py` and the template constants in `main.py`.
- [ ] **Step 5: Run the same tests.** Expected: PASS.
- [ ] **Step 6: Commit** `feat: add Clash of Critters auto battle state machine`.

### Task 9: Register the command, bundle the data, update docs, verify live

**Files:**
- Modify: `P/main.py`, `src-tauri/tauri.bundle.templates.json`, `P/CLAUDE.md`, `P/README.md`
- Test: `T/test_auto_battle_command.py`

**Interfaces:**
- Consumes: `AutoBattleMixin._run_auto_battle` (Task 8), `DeployMixin` (Task 7).
- Produces: `ClashOfCritters(AutoBattleMixin, DeployMixin, Game)` (follow the mixin pattern in `games/afk_journey`) and the command `auto_battle` with `GUIMetadata(label="Tự Động Chiến Đấu", category="Battle", tooltip=...)`.

- [ ] **Step 1: Write the failing test** `test_auto_battle_is_registered`: after importing `main`, `COMMAND_REGISTRY` (see `adb_auto_player/registries`) contains a Clash of Critters command named `auto_battle` with label `"Tự Động Chiến Đấu"` and category `"Battle"`, and no command named `keep_game_running`.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_command.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the class composition and the registered `auto_battle` method calling `self._run_auto_battle()`. Add two entries to `tauri.bundle.templates.json` mapping `src-python/adb_auto_player/games/clash_of_critters/tatari_db/` and `.../tatari_formations/` to `./games/clash_of_critters/tatari_db/` and `./games/clash_of_critters/tatari_formations/`. Update `P/CLAUDE.md`: the command table, a section describing the flow and the new templates, and the patch-zip section (add the new `.py` modules, the new templates, and the two data folders). Do **not** `git add` the two data folders; tell the user they are still untracked and must be committed for CI builds, and that `tatari_db` is about 70 MB.
- [ ] **Step 4: Run all targeted files** `uv run pytest src-python/tests/games/clash_of_critters -q`. Expected: all pass; report the pass count.
- [ ] **Step 5: Live check on the emulator** with the adb binary above: with the game on the camp screen, run `auto_battle` through `uv run python -m adb_auto_player.main_cli` (or the app's task runner) for one normal stage and for 15-50, watching the log. Confirm: Quick Deploy path, defeat then "Thử Lại", formation path with the counter reaching the expected count, stop on the win screen. Record anything surprising for the user, since the win screen is out of scope.
- [ ] **Step 6: Commit** `feat: register Clash of Critters auto battle command`.
