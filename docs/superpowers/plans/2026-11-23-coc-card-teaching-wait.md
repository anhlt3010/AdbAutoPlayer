# CoC Card Teaching Wait Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the tray holds cards the bot cannot recognize, the bot opens the formation window on the "Thẻ chưa nhận ra" tab, waits for the user to teach them, then places the missing tatari before fighting.

**Architecture:** `DeployMixin._deploy_formation` waits (bounded by a new setting) while `CardRecognizer.waiting_count() > 0`, signalling the UI with a flagged log record. `TauriQueueHandler` (main process) turns the flag into the Tauri event `formation-viewer:open-cards`; the main window opens the viewer.

**Tech Stack:** Python 3.12 (pydantic, pytest), PyTauri `Emitter`, SvelteKit 3 + Svelte 5, Tauri window API.

**Spec:** `docs/superpowers/specs/2026-11-23-coc-card-teaching-wait-design.md`

## Global Constraints

- Setting `auto_battle.card_teaching_wait_seconds`, default 180, new field in `AutoBattleSettings` and `src-tauri/settings/ClashOfCritters.toml`.
- Event name `formation-viewer:open-cards`, payload `{ profile_index: int }`.
- Log flag name `open_card_teaching` (a `logging` `extra` key).
- Wait ends when `recognizer.waiting_count() == 0`; the field is never cleared while waiting or afterwards.
- Timeout means the formation is incomplete: the plan moves to the next formation (existing `_deploy_current_step` path).
- Python: ruff rules of CLAUDE.md (`time.monotonic`, no bare magic numbers, Google docstrings outside `games/`); run `uvx ruff check --fix` / `uvx ruff format` from the repo root. Imports in Svelte use `#lib/...` with the file extension.
- Run only the targeted test files (from `src-tauri/`: `uv run pytest src-python/tests/games/clash_of_critters/<file> -q`).
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- A patch zip cannot carry this change (frontend and `__main__.py`); say so in the final report.

## Review Focus

- The user teaches only some cards and the wait times out: no fight with a short field, next formation tried.
- The wait is skipped when `waiting_count() == 0` (no event, no sleep), so normal runs are unchanged.
- Teaching clears the folder while the bot polls: the bot must not need the viewer to answer anything.
- Units already placed before the wait must not be dragged again after it (deployed cards are not recognized in the tray).
- The viewer is already open (or minimized): the event brings it to front on the cards tab and reloads the list.

---

### Task 1: Setting `card_teaching_wait_seconds`

**Files:**
- Modify: `adb_auto_player/games/clash_of_critters/settings.py` (class `AutoBattleSettings`, next to `tray_settle_poll_seconds`)
- Modify: `src-tauri/settings/ClashOfCritters.toml` (`[auto_battle]`)
- Test: `tests/games/clash_of_critters/test_auto_battle_settings.py`

**Interfaces:**
- Produces: `AutoBattleSettings.card_teaching_wait_seconds: int` (default 180, allowed 10..3600), read as `self.settings.auto_battle.card_teaching_wait_seconds`.

- [ ] **Step 1: Write the failing tests** `test_card_teaching_wait_default` (`AutoBattleSettings().card_teaching_wait_seconds == 180`) and `test_card_teaching_wait_is_bounded` (`pytest.raises(ValidationError)` for 9 and 3601), same style as the `tray_settle_poll_seconds` tests.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/games/clash_of_critters/test_auto_battle_settings.py -q`; expect the new tests to FAIL.
- [ ] **Step 3: Implement** the field with `Field(default=180, ge=10, le=3600, title="Card Teaching Wait (seconds)", description=...)` (description: how long the bot waits for the user to teach unrecognized cards before trying another formation); add `card_teaching_wait_seconds = 180` to the toml. Follow how `tray_settle_poll_seconds` declares its annotated type.
- [ ] **Step 4: Run** the same file; expect all PASS.
- [ ] **Step 5: Commit** `feat: add the wait for teaching unrecognized CoC cards to the settings`.

### Task 2: Wait for teaching inside the deploy

**Files:**
- Modify: `adb_auto_player/games/clash_of_critters/deploy.py` (`DeployResult`, `_deploy_formation`, new `_await_card_teaching`)
- Modify: `adb_auto_player/games/clash_of_critters/auto_battle.py:373-388` (`_deploy_current_step`)
- Test: `tests/games/clash_of_critters/test_deploy.py`, `tests/games/clash_of_critters/test_auto_battle_flow.py`

**Interfaces:**
- Produces: `DeployResult(count: int, needed: int, blocked: bool = False)`; `complete` is `not blocked and count >= needed`.
- Produces: `DeployMixin._await_card_teaching(self) -> bool`: returns True at once when `waiting_count() == 0`; otherwise logs `Có N thẻ chưa nhận ra, mở cửa sổ đội hình để chỉ cho bot.` once with `extra={"open_card_teaching": True}`, polls `waiting_count()` every `_TEACH_POLL_SECONDS` (1.0, module constant) using `sleep` and `time.monotonic()` until it is 0 (return True) or `card_teaching_wait_seconds` pass (log a warning, return False).
- Consumes: `CardRecognizer.waiting_count() -> int`, `self.settings.auto_battle.card_teaching_wait_seconds`.

- [ ] **Step 1: Write failing tests in `test_deploy.py`** (the `bot` fixture's recognizer is a MagicMock; set `waiting_count.side_effect`; `settings.auto_battle` in the fixture needs `card_teaching_wait_seconds=180`):
  - `test_no_wait_without_waiting_cards`: `waiting_count` returns 0 → `_await_card_teaching()` is True, `sleep` not called, no record has `open_card_teaching`.
  - `test_waits_until_the_cards_are_taught`: `side_effect=[2, 2, 0]` → True; exactly one log record carries `open_card_teaching is True`; `sleep` called with `1.0` twice.
  - `test_wait_times_out`: `waiting_count` always 2 and `deploy.time.monotonic` patched to jump past 180 s → False, warning logged, the flagged record is still logged only once.
  - `test_formation_is_blocked_after_a_timeout`: `_await_card_teaching` patched to False → `_deploy_formation(...)` returns `blocked is True`, `complete is False`, and `_drag_card` was never called after the wait.
  - `test_teaching_places_only_the_missing_units`: formation units A (owned, placed in pass one) and B (card unrecognized in pass one, so absent); `_await_card_teaching` returns True; on the second pass `_scan_owned` reports B only → exactly one more drag (to B's cell), the clear-field tap happened once, and the result is `DeployResult(2, 2)`.
  - Update `test_waiting_unrecognized_cards_are_logged` to the new behaviour (message now comes from `_await_card_teaching`; with a recognizer that reports 2 then 0 the deploy continues and does not return blocked).
- [ ] **Step 2: Write failing tests in `test_auto_battle_flow.py`**: `test_blocked_formation_goes_to_the_next_one` (first `_deploy_formation` returns `DeployResult(0, 0, blocked=True)`, second `DeployResult(15, 15)` → the second formation is deployed and the fight is pressed), and `test_blocked_last_formation_stops` (single formation blocked → `_play_plan_step` returns False, no fight). The blocked check must come before the existing `count == 0` stop.
- [ ] **Step 3: Run** both files; expect the new tests to FAIL.
- [ ] **Step 4: Implement** `DeployResult.blocked` and `_await_card_teaching`. In `_deploy_formation`: after the per-element loop (and before the fill rounds) call `_await_card_teaching()`; if False return `DeployResult(count, needed, blocked=True)` after `_select_element(None)`. If True and the pass found any unit absent (plan entries without an evolution id), run the same per-element pass again over only the units not yet placed (track placed units by their `FormationUnit` in a set while `_place_wanted` succeeds; `_scan_owned` already skips deployed cards), accumulating `needed` and `missing`, without tapping the clear button. Extract the per-element body into a helper so both passes share it. Update the class docstring and the log text accordingly.
- [ ] **Step 5: Implement** in `_deploy_current_step`: handle `result.blocked` first (warning with the formation number, `_plan_pos += 1`, `_plan_fights = 1`, or the existing error and `return False` when it was the last step).
- [ ] **Step 6: Run** both test files; expect all PASS. Run `uvx ruff check --fix` and `uvx ruff format` from the repo root.
- [ ] **Step 7: Commit** `feat: wait for the user to teach unrecognized CoC cards before fighting`.

### Task 3: Turn the flagged log into the `formation-viewer:open-cards` event

**Files:**
- Modify: `adb_auto_player/__main__.py` (`TauriQueueHandler.emit`, new `OpenCardsEvent(BaseModel)` next to `TaskCompletedEventEvent`)
- Test: `tests/test_tauri_queue_handler.py` (new; `tests/test_e2e_flow.py` shows how `__main__` is imported in tests)

**Interfaces:**
- Produces: `OpenCardsEvent(profile_index: int)`; `TauriQueueHandler.emit` additionally calls `Emitter.emit(self.app_handle, "formation-viewer:open-cards", OpenCardsEvent(profile_index=self.profile_index))` when `getattr(record, "open_card_teaching", False)` is true; the normal `log-message` is still emitted. Emit errors are swallowed like the log one.

- [ ] **Step 1: Write failing tests** with `Emitter.emit` patched: `test_flagged_record_emits_open_cards_event` (assert a call with name `"formation-viewer:open-cards"` and `profile_index` equal to the handler's, plus the `log-message` call) and `test_plain_record_emits_no_open_cards_event`.
- [ ] **Step 2: Run** `uv run pytest src-python/tests/test_tauri_queue_handler.py -q`; expect FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run** the file; expect PASS. Run ruff from the repo root.
- [ ] **Step 5: Commit** `feat: open the CoC formation viewer from a task log flag`.

### Task 4: Main window opens the viewer on the cards tab

**Files:**
- Modify: `src/lib/log/eventNames.ts` (add `OPEN_CARDS_VIEWER: "formation-viewer:open-cards"`)
- Modify: `src/lib/formation/viewer.ts` (`openFormationViewer(profileIndex: number, tab?: "cards")`; add exported `FORMATION_VIEWER_TAB_EVENT = "formation-viewer:show-cards"` emitted to the open window, and `&tab=cards` in the new window URL)
- Modify: `src/routes/(app)/+layout.svelte` (listen next to `ProfileStateUpdate`, unlisten on destroy; handler calls `openFormationViewer(event.payload.profile_index, "cards")`)
- Modify: `src/routes/formation-viewer/+page.svelte` (initial `tab` from the `tab` query param; listen to `FORMATION_VIEWER_TAB_EVENT` to set `tab = "cards"` and bump `cardsReload`)

**Interfaces:**
- Consumes: the Python event `{ profile_index: number }` from Task 3.
- Note: the new event has no PyTauri command, so `src/client/` needs no change (never edit it by hand).

- [ ] **Step 1: Implement** the four edits above; the existing refresh path (`FORMATION_VIEWER_REFRESH_EVENT`) stays for the button.
- [ ] **Step 2: Run** `pnpm check` and `pnpm prettier-write` from the repo root; expect no errors.
- [ ] **Step 3: Verify in the app** (`pnpm tauri dev`): a flagged log record (`logging.info("x", extra={"open_card_teaching": True})` from a running task, or a temporary Python test emit) opens the viewer on the cards tab; with the viewer already open and on the formation tab it switches to the cards tab. Report what was and was not exercised.
- [ ] **Step 4: Commit** `feat: open the CoC formation viewer on the cards tab when the bot asks`.

### Task 5: Docs

**Files:**
- Modify: `adb_auto_player/games/clash_of_critters/CLAUDE.md` (the Deploying and Formation viewer bullets: the wait, the new setting, the open-cards event, `DeployResult.blocked`, and "needs a full app build" for the event and UI)

- [ ] **Step 1: Edit** the bullets, keeping the markdown rules of the root CLAUDE.md.
- [ ] **Step 2: Run** the targeted test files of Tasks 1, 2 and 3 together and show the pass count in the report.
- [ ] **Step 3: Commit** `docs: describe the CoC wait for card teaching`.
