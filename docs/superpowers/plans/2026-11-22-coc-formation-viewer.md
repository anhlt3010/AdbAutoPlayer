# Clash of Critters Formation Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A button on the "Tự Động Chiến Đấu" card opens a small window that shows the prepared formations (exact tier) of the stage read from the device screen, or typed by the user.

**Architecture:** One new PyTauri command (`get_formation_view`) takes one screenshot (or a typed stage), reads the stage by OCR, loads `tatari_formations` and returns the formations with base64 sprites. A second Tauri window (label `formation-viewer`, a SvelteKit route outside the main app layout) calls that command itself and renders a 5x5 grid.

**Tech Stack:** Python 3.12 (pydantic, numpy, OpenCV, RapidOCR, PIL), PyTauri, Tauri 2 capabilities, SvelteKit 3 + Svelte 5 (static SPA), TypeScript.

**Spec:** `docs/superpowers/specs/2026-11-22-coc-formation-viewer-design.md`

## Global Constraints

- The viewer only takes a screenshot; it never sends tap, swipe or any input to the device.
- Statuses of the response, exactly: `ok`, `no_device`, `stage_unreadable`, `stage_invalid`, `no_formation`.
- Window label `formation-viewer`, default size about 420x560, resizable, one window only.
- Sprites are downscaled to at most 96 px on the longer side and sent as `data:image/png;base64,...`; CSP gets `img-src 'self' data:`.
- Manual stage `-` / `+` stay inside the chapter and never go below stage 1; no upper limit.
- Formation order is file order; prev/next stop at both ends (no wrap-around); a new stage starts at formation 1.
- `src/client/` is generated: never edit it by hand. Frontend imports use `#lib/...` / `#pytauri/...` with the file extension; every visible text goes through `$t` with a `vn.json` entry.
- Python: Ruff from the repo root (`uvx ruff check --fix`, `uvx ruff format`), `X | None` annotations, no `time.time`. Run only the test files named in the tasks, from `src-tauri/`, and show their pass count.
- Commit steps run only if the user asked for commits in this session; otherwise leave the changes uncommitted. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

- Stage text with a near-miss ("15-5O") must give `stage_unreadable`, never a guessed stage. Test in Task 3.
- A typed stage with an en dash or spaces ("15 – 51") must work like "15-51". Test in Task 4.
- A device whose screenshot is not 1080x1920 must still read the stage (the box is scaled). Test in Task 3.
- A formation file whose units are all malformed must give `no_formation`, not an empty "ok". Test in Task 4.
- Fast clicks on `-` / `+` must not let an older answer overwrite a newer one (request token in the page). Manual check in Task 7.

---

## File Structure

- Create `src-tauri/src-python/adb_auto_player/games/clash_of_critters/formation_view.py`: response models, sprite encoding, stage reading, `load_formation_view`.
- Modify `.../clash_of_critters/formation.py`: `FormationUnit.name`.
- Modify `src-tauri/src-python/adb_auto_player/__main__.py`: the command.
- Create `src-tauri/src-python/tests/games/clash_of_critters/test_formation_view.py`; modify `test_formation_load.py`; add `data/battle_screen.png`.
- Modify `src-tauri/tauri.conf.json`, `src-tauri/capabilities/default.json`.
- Move `src/routes/+layout.svelte` and `+page.svelte` into `src/routes/(app)/`; new small `src/routes/+layout.svelte`.
- Create `src/routes/formation-viewer/+page.svelte`, `src/lib/components/formation/FormationGrid.svelte`, `src/lib/formation/stage.ts`, `src/lib/formation/viewer.ts`.
- Modify `src/lib/components/modern/TaskCard.svelte`, `src/lib/i18n/vn.json`, the game's `CLAUDE.md`.

---

### Task 1: Unit name in formations

**Files:** Modify `formation.py` (`FormationUnit`, `_parse_unit`); Test `tests/games/clash_of_critters/test_formation_load.py`.

**Interfaces:** Produces `FormationUnit.name: str = ""` (last field, default keeps existing constructors valid).

- [ ] **Step 1: Write failing tests** in `test_formation_load.py`, reusing `_write`/`_unit`: `test_unit_keeps_its_name` (unit dict `name` "Orchitoria" gives `load_formations(...)[0].units[0].name == "Orchitoria"`) and `test_unit_without_name_has_empty_name` (dict without `name` gives `""`).
- [ ] **Step 2:** Run `uv run pytest src-python/tests/games/clash_of_critters/test_formation_load.py -q`; expect the two new tests FAIL.
- [ ] **Step 3:** Add the field and read it with `str(raw.get("name", ""))` in `_parse_unit`.
- [ ] **Step 4:** Re-run the same command; expect all PASS.
- [ ] **Step 5:** Commit `feat: keep the tatari name of a formation unit`.

### Task 2: Response models and sprites

**Files:** Create `formation_view.py`; Test `tests/games/clash_of_critters/test_formation_view.py`.

**Interfaces:**
- Produces in `formation_view.py`:
  - `FormationViewStatus = Literal["ok", "no_device", "stage_unreadable", "stage_invalid", "no_formation"]`
  - `ViewUnit(BaseModel)`: `row: int`, `col: int`, `tatari_id: str`, `evolution_id: str`, `name: str`, `tier: int`, `glitter: bool`, `sprite: str | None`
  - `ViewFormation(BaseModel)`: `level: int | None`, `units: list[ViewUnit]`
  - `FormationViewResponse(BaseModel)`: `status: FormationViewStatus`, `stage: str | None`, `formations: list[ViewFormation]`
  - `sprite_data_uri(path: Path) -> str | None` (cached per path; `None` when the file is missing or unreadable)
  - `build_response(stage: StageId, formations: tuple[Formation, ...], db: TatariDb) -> FormationViewResponse` (status `ok`, or `no_formation` when `formations` is empty)

- [ ] **Step 1: Write failing tests** (build a `TatariDb([Sprite(...)])` and a 200x300 RGBA PNG in `tmp_path`): `test_units_keep_file_order_level_and_glitter` (two formations, levels 1475 and 1500, glitter flag kept, `status == "ok"`, `stage == "15-50"`); `test_sprite_is_a_small_png_data_uri` (prefix `data:image/png;base64,`, decoded image mode `RGBA`, `max(size) == 96`); `test_unknown_evolution_has_no_sprite` (`sprite is None`, tier and name kept); `test_no_formations_gives_no_formation`.
- [ ] **Step 2:** Run `uv run pytest src-python/tests/games/clash_of_critters/test_formation_view.py -q`; expect FAIL (import error).
- [ ] **Step 3:** Implement the models, `sprite_data_uri` (PIL, `thumbnail((96, 96))`, PNG, base64, `functools.cache`) and `build_response` in `formation_view.py`.
- [ ] **Step 4:** Re-run; expect 4 PASS.
- [ ] **Step 5:** Commit `feat: build the formation viewer response with sprites`.

### Task 3: Read the stage from a screenshot

**Files:** Modify `formation_view.py`; copy `docs/superpowers/specs/assets/battle_screen.png` to `tests/games/clash_of_critters/data/battle_screen.png`; Test `test_formation_view.py`.

**Interfaces:** Produces `VIEW_STAGE_BOX = (380, 25, 600, 95)` (left, top, right, bottom on 1080x1920; the fight-screen label reaches x 555, wider than the auto battle's `STAGE_LABEL_BOX`) and `read_stage_from_screenshot(screenshot: np.ndarray) -> StageId | None` (BGR; resizes to 1080x1920 first when the shape differs; OCR through a lazily created module-level `RapidOCRBackend`; text through `parse_stage`).

- [ ] **Step 1: Write failing tests** (images via `cv2.imread` from the `data` folder): `test_fight_screen_reads_its_stage` (`battle_screen.png` gives `StageId(15, 50)`); `test_preparation_screens_read_a_stage` (parametrized over the `prep_screen_*.png` captures; first view each image with the Read tool and pin the stage it shows); `test_screens_without_a_label_are_unreadable` (parametrized: `camp_screen`, `defeat_screen`, `victory_screen`, `stage_map_screen`, `map_after_victory` give `None`); `test_half_size_screenshot_still_reads` (battle capture resized to 540x960 gives `StageId(15, 50)`); `test_near_miss_text_is_unreadable` (patch the OCR backend's `extract_text` to return `"15-5O"`, result `None`).
- [ ] **Step 2:** Run the test file; expect the new tests FAIL.
- [ ] **Step 3:** Implement. If a capture does not read, widen or shift `VIEW_STAGE_BOX` (never touch `STAGE_LABEL_BOX`); real OCR must stay in the tests, because the box position is what they prove. If RapidOCR cannot start in the test environment, stop and report instead of mocking.
- [ ] **Step 4:** Re-run; expect all PASS.
- [ ] **Step 5:** Commit `feat: read the stage of any screen that shows its label`.

### Task 4: The lookup

**Files:** Modify `formation_view.py`; Test `test_formation_view.py`.

**Interfaces:**
- Consumes: Tasks 1-3, `formation.load_formations`, `TatariDb.load`.
- Produces: `grab_screenshot() -> np.ndarray` (`AdbController().screenshot(["com.farlightgames.pgame.gp.vn"])`, PNG bytes through `IO.get_bgr_np_array_from_png_bytes`, then `_ScreenshotMixin._apply_vertical_offset_to_screenshot`; raises on non-bytes) and
  `load_formation_view(stage_text: str | None, grab: Callable[[], np.ndarray] = grab_screenshot, data_root: Path | None = None) -> FormationViewResponse`. `data_root` defaults to `SettingsLoader.games_dir() / "clash_of_critters"`; formations from `data_root/"tatari_formations"`, db from `data_root/"tatari_db"`.
  - `stage_text` given: normalise `–`, `—`, `−` to `-`, `parse_stage` it (`None` gives `stage_invalid`), never call `grab`.
  - `stage_text` is `None`: call `grab`; any exception gives `no_device`; unreadable stage gives `stage_unreadable` with `stage=None`.
  - Parsed stage with no usable formation gives `no_formation` with `stage` set.

- [ ] **Step 1: Write failing tests** (`data_root` = the package folder for real data; a `tmp_path` root with `{"tataris": []}` as `tatari_db/tatari_db.json` for synthetic files): `test_typed_stage_skips_the_screenshot` (`grab` raises `AssertionError`; `"73-1"` gives `ok`, one formation, `level == 1475`, 15 units, first unit `evolution_id == "grass-4-4"`, `tier == 4`); `test_typed_stage_with_en_dash_and_spaces` (`"73 – 1"` gives stage `"73-1"`); `test_bad_typed_stage_is_invalid` (`"abc"` gives `stage_invalid`, no formations); `test_typed_stage_without_file` (`"99-99"` gives `no_formation`, `stage == "99-99"`); `test_formation_with_only_bad_units_gives_no_formation` (tmp file whose units are out of the 5x5 field); `test_screen_stage_comes_from_the_capture` (`grab` returns `battle_screen.png`, `stage == "15-50"`); `test_screen_without_label_is_unreadable` (camp capture, `stage_unreadable`, `stage is None`); `test_failing_grab_means_no_device`.
- [ ] **Step 2:** Run the test file; expect the new tests FAIL.
- [ ] **Step 3:** Implement `grab_screenshot` and `load_formation_view`.
- [ ] **Step 4:** Re-run; expect all PASS. Then from the repo root run `uvx ruff check --fix` and `uvx ruff format`.
- [ ] **Step 5:** Commit `feat: look up the formations of a stage read or typed`.

### Task 5: PyTauri command and generated client

**Files:** Modify `__main__.py`; regenerate `src/client/apiClient.ts` and `src/client/_apiTypes.d.ts`.

**Interfaces:** Produces the command `get_formation_view` (TS `getFormationView`), input `FormationViewBody` = `ProfileContext` plus `stage: str | None = None`, output `FormationViewResponse`.

- [ ] **Step 1:** In `__main__.py` add `class FormationViewBody(ProfileContext)` and `@tauri_profile_aware_command async def get_formation_view(app_handle: AppHandle, body: FormationViewBody) -> FormationViewResponse`, running `load_formation_view(body.stage)` in `_executor` with `copy_context()` like `get_profile_state` does.
- [ ] **Step 2:** Regenerate the client: from the project venv with `VIRTUAL_ENV_PROMPT=AdbAutoPlayer` run `pnpm tauri dev`, wait until `src/client/apiClient.ts` contains `getFormationView` and `_apiTypes.d.ts` contains `FormationViewResponse`, then close the app. If generation cannot be run here, stop and ask the user; never hand-edit the client.
- [ ] **Step 3:** Run `uvx ruff check --fix` and `uvx ruff format` from the repo root; run `pnpm check`; expect no errors.
- [ ] **Step 4:** Commit `feat: add the get_formation_view command`.

### Task 6: Window plumbing and layout split

**Files:** Modify `tauri.conf.json`, `capabilities/default.json`; move the two route files; create the root `+layout.svelte`.

**Interfaces:** Produces the route `/formation-viewer` rendered without the app chrome, and permission for a window labelled `formation-viewer`.

- [ ] **Step 1:** CSP in `tauri.conf.json` becomes `default-src 'self'; script-src 'self'; connect-src ipc: http://ipc.localhost; img-src 'self' data:`.
- [ ] **Step 2:** `capabilities/default.json`: `windows` becomes `["main", "formation-viewer"]`; add `core:webview:allow-create-webview-window`, `core:window:allow-show`, `core:window:allow-unminimize`, `core:window:allow-set-focus`.
- [ ] **Step 3:** `git mv src/routes/+layout.svelte "src/routes/(app)/+layout.svelte"` and the same for `+page.svelte`. In the moved layout remove `import "../app.css"` and the `$effect` that sets the theme class and `--accent-h` (they move to the root layout). New `src/routes/+layout.svelte` imports `../app.css` and `ui`, holds that `$effect`, and renders `{@render children()}`. `+layout.ts` stays.
- [ ] **Step 4:** Run `pnpm check` and `pnpm build`; expect no errors and a file `dist/formation-viewer.html` only after Task 7 (for now `pnpm build` must succeed and `dist/index.html` must exist). Start `pnpm tauri dev` and confirm the main window looks and behaves as before (sidebar, theme, task cards).
- [ ] **Step 5:** Commit `refactor: split the app layout from the root layout for a second window`.

### Task 7: The viewer page

**Files:** Create `src/lib/formation/stage.ts`, `src/lib/components/formation/FormationGrid.svelte`, `src/routes/formation-viewer/+page.svelte`; modify `src/lib/i18n/vn.json`.

**Interfaces:**
- `stage.ts`: `stepStage(stage: string, delta: -1 | 1): string | null` (matches `^\s*(\d{1,2})\s*-\s*(\d{1,3})\s*$`; `null` if it does not match or the result number is below 1).
- `FormationGrid.svelte`: props `{ units: ViewUnit[] }` (type from `#pytauri/_apiTypes.d.ts`); 5x5 cells, each occupied cell shows the sprite (or the name as text when `sprite` is null), a badge `T{tier}`, a glitter mark when `glitter`, and the name; empty cells stay empty.
- The page reads `profile` from the URL query, calls `getFormationView({ profile_index, stage })`, and on mount runs `applySettingsFromFile()` (locale, theme) then loads from the screen. It listens to the Tauri event `formation-viewer:refresh` (payload `{ profile_index: number }`) and then reloads from the screen. It never calls `show_window`.

- [ ] **Step 1:** Header: `-` button, stage input (Enter loads that typed stage), `+` button (disabled when `stepStage` gives `null`), `Lv <level>`, `n/total` with prev/next buttons (disabled at the ends), refresh button (reload from the screen, clearing a typed stage). Changing stage resets to formation 1.
- [ ] **Step 2:** Messages from `status`: `no_device`, `stage_unreadable` (tell the user to type a stage), `stage_invalid`, `no_formation` (with the stage). On an invalid typed stage keep the previous formations visible next to the error.
- [ ] **Step 3:** Use an incrementing request token so an older answer is ignored when a newer request was started.
- [ ] **Step 4:** Add to `vn.json` (keys in alphabetical position): "Formation viewer": "Đội Hình Mẫu"; "Formation {{current}}/{{total}}": "Đội hình {{current}}/{{total}}"; "Next formation": "Đội hình sau"; "Previous formation": "Đội hình trước"; "Refresh (read the screen)": "Làm mới (đọc lại màn hình)"; "Reading the screen...": "Đang đọc màn hình..."; "Stage": "Màn"; "Show formation": "Xem đội hình mẫu"; "No device found.": "Không tìm thấy thiết bị."; "Could not read the stage from this screen. Type a stage such as 15-50.": "Không đọc được màn từ màn hình này. Hãy nhập màn, ví dụ 15-50."; "Wrong stage format. Use chapter-number, for example 15-50.": "Sai định dạng màn. Dùng chương-màn, ví dụ 15-50."; "No prepared formation for stage {{stage}}.": "Chưa có đội hình mẫu cho màn {{stage}}.".
- [ ] **Step 5:** Run `pnpm prettier-write`, `pnpm check`, `pnpm build`; expect no errors and `dist/formation-viewer.html` (or `dist/formation-viewer/index.html`) present.
- [ ] **Step 6:** Commit `feat: add the formation viewer page`.

### Task 8: The card button and the documentation

**Files:** Create `src/lib/formation/viewer.ts`; modify `TaskCard.svelte`, `games/clash_of_critters/CLAUDE.md`; check `scripts/build_coc_patch.py`.

**Interfaces:** `viewer.ts` produces `openFormationViewer(profileIndex: number): Promise<void>`: if a window labelled `formation-viewer` exists, `unminimize()`, `show()`, `setFocus()` and `emitTo` it `formation-viewer:refresh` with `{ profile_index }`; otherwise create `new WebviewWindow("formation-viewer", { url: "/formation-viewer?profile=<n>", title: "Formation viewer", width: 420, height: 560, resizable: true })`. Errors go to `showErrorToast`.

- [ ] **Step 1:** In `TaskCard.svelte` add a button rendered only when `b.taskKey?.startsWith("Clash of Critters::") && b.option.args.includes("auto_battle")`, left of the eye button (same size 22px, same hover rule; `right: 38px` normally, `right: 68px` in the palette variant), `title`/`aria-label` `$t("Show formation")`, `onclick` calls `openFormationViewer(profiles.active)`.
- [ ] **Step 2:** Run `pnpm tauri dev` and check by hand: the button shows only on the "Tự Động Chiến Đấu" card in the cards, palette and accordion views (if `args` does not hold `auto_battle`, read the real value from the card and fix the condition); on the preparation and fight screens the window shows the right stage and tiers; on the camp it shows the "type a stage" message; typing 15-51, `-`/`+` and the prev/next buttons work; clicking the card button again refreshes and focuses the same window; closing and clicking again opens it anew; the window uses the same theme as the main window; clicking while the auto battle runs does not disturb it; fast `-`/`-` clicks end on the last stage clicked.
- [ ] **Step 3:** Add a "Formation Viewer" bullet to `games/clash_of_critters/CLAUDE.md` (command `get_formation_view`, module `formation_view.py`, route `/formation-viewer`, window label, statuses, the one-screenshot-no-input rule) and the note that the patch zip carries only the Python part: the button, window, CSP and capabilities need a full app build. Confirm `scripts/build_coc_patch.py` packages `formation_view.py` (it takes every `.py` of the folder; if it lists files, add it).
- [ ] **Step 4:** Run `pnpm prettier-write`, `pnpm check`, and from the repo root `uvx ruff check --fix` and `uvx ruff format`; run `uv run pytest src-python/tests/games/clash_of_critters/test_formation_view.py src-python/tests/games/clash_of_critters/test_formation_load.py -q` from `src-tauri/`; expect everything clean and all PASS, and show the pass count.
- [ ] **Step 5:** Commit `feat: open the formation viewer from the auto battle card`.
