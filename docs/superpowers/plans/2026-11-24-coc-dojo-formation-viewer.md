# Võ Đường Formation Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A button on the "Võ Đường Huy Hiệu" card opens the existing formation viewer in dojo mode: stage and element are detected from one screenshot, the formation is shown on a 3x4 grid, and unrecognized dojo cards show in the cards tab with the right element.

**Architecture:** The viewer window, its tabs and the `get_formation_view` command stay; they get a `mode` (`battle` | `dojo`). Dojo mode reads the stage with the dojo label box, votes the element from the element icons of the tray cards, and loads `tatari_dojo/<element>/`. The recognizer writes the known element into the file name of an unrecognized crop, and the cards tab reads it back.

**Tech Stack:** Python 3.12 (OpenCV, pydantic, pytest), SvelteKit 3 + Svelte 5 runes, PyTauri generated client.

**Spec:** `docs/superpowers/specs/2026-11-24-coc-dojo-formation-viewer-design.md`

## Global Constraints

- Python (from `CLAUDE.md`): ruff `line-length = 88`, Google docstrings on public functions, no bare literals in comparisons (PLR2004: use module constants), `X | None` annotations, `time.time` and `cv2.split` banned. Run `uvx ruff check --fix` and `uvx ruff format` from the repo root.
- `Point` equality is always true in this repo: compare `(p.x, p.y)`.
- Tests: run only the touched test files, from `src-tauri/`: `uv run pytest src-python/tests/games/clash_of_critters/<file> -q`. Never the full suite. Report the pass count.
- Frontend: imports use `#lib/...` / `#pytauri/...` with the file extension. `src/client/` is generated, never edited by hand. Checks: `pnpm check`, `pnpm prettier-write`.
- The viewer never sends input to the device.
- Dojo captures for tests: `docs/superpowers/specs/assets/dojo_prep_cleared.png` (stage 4-2, grass tray) and `dojo_prep_scrolled.png`; load them like `test_badge_dojo_helpers.py` does (`Path(__file__).parents[5] / "docs" / "superpowers" / "specs" / "assets"`).
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- A patch zip carries only the Python part; the UI work needs a full app build (mention it in the final report).

## Review Focus

- A dojo screen where fewer than 2 tray cards read an element (empty/blurred tray): answer `element_unreadable` with the stage set, never a wrong element (Task 1).
- Two elements tied in the vote: `element_unreadable`, not the first one (Task 1).
- Dojo mode on a screen with no stage label (camp, Chế Độ screen): `stage_unreadable`, not a crash or a battle-box read (Task 1).
- A bad or unknown `element` string from the UI: treated as unreadable (Task 1).
- An old unprefixed crop and a prefixed crop of the same card: only one is saved, both still listed and taught (Task 2).
- The auto-open event from a dojo run (`openFormationViewer(profile, "cards")`, no mode) must not flip an open dojo viewer back to battle mode (Task 4).
- Stepping the dojo stage past 10 or below 1 is refused (Task 4).

---

### Task 1: Dojo view in `formation_view.py`

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/formation_view.py`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_formation_view.py`

**Interfaces:**
- Consumes: `battle_layout.DOJO_LAYOUT`, `BATTLE_LAYOUT`, `PrepLayout`, `find_card_lefts(screenshot, layout)`, `card_box(center: Point, layout)`, `ELEMENT_ICON_BOX`; `card_recognition.classify_element(icon_bgr) -> str | None`; `tatari_db.ELEMENTS`; `formation.load_dojo_formations(root, element, stage)`.
- Produces:
  - `ViewMode = Literal["battle", "dojo"]`
  - `FormationViewStatus` gains `"element_unreadable"`
  - `FormationViewResponse` gains `element: str | None = None` and `mode: ViewMode = "battle"`
  - `read_stage_from_screenshot(screenshot: np.ndarray, box: tuple[int, int, int, int] = VIEW_STAGE_BOX) -> StageId | None`
  - `read_tray_element(screenshot: np.ndarray, layout: PrepLayout = DOJO_LAYOUT) -> str | None`
  - `load_formation_view(stage_text, grab=grab_screenshot, data_root=None, mode: ViewMode = "battle", element: str | None = None) -> FormationViewResponse`
  - `build_response(stage, formations, db, element: str | None = None, mode: ViewMode = "battle")`

- [ ] **Step 1: Write the failing tests** in `test_formation_view.py`

```python
DOJO_BOX = DOJO_LAYOUT.stage_label_box


def test_dojo_prep_screen_reads_its_stage_with_the_dojo_box() -> None:
    assert read_stage_from_screenshot(_dojo("dojo_prep_cleared.png"), DOJO_BOX) == StageId(4, 2)


def test_dojo_prep_screen_votes_its_element() -> None:
    assert read_tray_element(_dojo("dojo_prep_cleared.png")) == "grass"
    assert read_tray_element(_dojo("dojo_prep_scrolled.png")) == "grass"


def test_screen_without_a_tray_has_no_element() -> None:
    assert read_tray_element(_capture("camp_screen.png")) is None


def test_one_vote_is_not_enough(monkeypatch) -> None:
    monkeypatch.setattr(formation_view, "classify_element", _votes(["grass", None, None]))
    assert read_tray_element(_dojo("dojo_prep_cleared.png")) is None


def test_tied_vote_is_unreadable(monkeypatch) -> None:
    monkeypatch.setattr(formation_view, "classify_element", _votes(["grass", "grass", "fire", "fire"]))
    assert read_tray_element(_dojo("dojo_prep_cleared.png")) is None


def test_dojo_screen_gives_formations_of_the_detected_element() -> None:
    response = load_formation_view(None, grab=_dojo_grab("dojo_prep_cleared.png"),
                                   data_root=REAL_ROOT, mode="dojo")
    assert (response.status, response.stage, response.element, response.mode) == ("ok", "4-2", "grass", "dojo")
    assert response.formations  # tatari_dojo/grass/4-2.json (shared_with 4-1 - 4-10)


def test_dojo_screen_without_element_keeps_the_stage(monkeypatch) -> None:
    monkeypatch.setattr(formation_view, "read_tray_element", lambda *_: None)
    response = load_formation_view(None, grab=_dojo_grab("dojo_prep_cleared.png"),
                                   data_root=REAL_ROOT, mode="dojo")
    assert (response.status, response.stage, response.element) == ("element_unreadable", "4-2", None)


def test_dojo_typed_stage_with_element_skips_the_screenshot() -> None:
    response = load_formation_view("4-3", grab=_no_grab, data_root=REAL_ROOT, mode="dojo", element="grass")
    assert (response.status, response.stage, response.element) == ("ok", "4-3", "grass")


def test_dojo_typed_stage_without_element_is_unreadable_and_skips_the_screenshot() -> None:
    response = load_formation_view("4-3", grab=_no_grab, data_root=REAL_ROOT, mode="dojo")
    assert (response.status, response.stage) == ("element_unreadable", "4-3")


def test_dojo_unknown_element_is_unreadable() -> None:
    response = load_formation_view("4-3", grab=_no_grab, data_root=REAL_ROOT, mode="dojo", element="wind")
    assert response.status == "element_unreadable"


def test_dojo_screen_without_label_is_stage_unreadable() -> None:
    response = load_formation_view(None, grab=_grab_of("camp_screen.png"), data_root=REAL_ROOT, mode="dojo")
    assert response.status == "stage_unreadable"


def test_dojo_typed_stage_without_file_names_the_element() -> None:
    response = load_formation_view("4-99", grab=_no_grab, data_root=REAL_ROOT, mode="dojo", element="grass")
    assert (response.status, response.element, response.mode) == ("no_formation", "grass", "dojo")
```

`_dojo(name)` loads an asset from the specs assets folder (as in `test_badge_dojo_helpers.py`), `_dojo_grab(name)` wraps it in a lambda, `_votes(list)` returns a `classify_element` replacement that yields the list items in call order. Existing battle tests must stay green unchanged.

- [ ] **Step 2: Run the tests to see them fail**

Run (from `src-tauri/`): `uv run pytest src-python/tests/games/clash_of_critters/test_formation_view.py -q`
Expected: the new tests FAIL (missing names / arguments); the old ones pass.

- [ ] **Step 3: Implement in `formation_view.py`**
  - Models and status as in Interfaces. `_empty(status, stage, element=None, mode="battle")` carries `element` and `mode` too.
  - `read_stage_from_screenshot` gets the `box` parameter (default keeps today's behaviour).
  - `read_tray_element`: scale the screenshot to 1080x1920 like `read_stage_from_screenshot`, cut every card the way `DeployMixin._visible_cards` does (`find_card_lefts`, rows from `layout.tray_rows_y`, `card_box`), resize to `BATTLE_LAYOUT.card_size` when the layout's card size differs, `classify_element` on `ELEMENT_ICON_BOX`. Vote rule (my call, constants `_MIN_ELEMENT_VOTES = 2`): return the top element only if it has at least `_MIN_ELEMENT_VOTES` votes and strictly more than the second; else None. Do not skip dimmed (deployed) cards.
  - `load_formation_view` dojo branch: element that is not in `ELEMENTS` counts as None. Typed stage: parse as today; no screenshot; `element` None -> `element_unreadable` with the stage. No stage text: grab (failure -> `no_device`), stage with the dojo box (None -> `stage_unreadable`), element = given or `read_tray_element`; None -> `element_unreadable` with the stage. Then `load_dojo_formations(root / "tatari_dojo", element, stage)` and `build_response(..., element=element, mode="dojo")`. The battle branch is unchanged apart from carrying `mode="battle"`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_formation_view.py -q`
Expected: all pass. If `read_tray_element` does not return `"grass"` on the two real captures, investigate the vote on those captures first; do not weaken the assertion.

- [ ] **Step 5: Lint and commit**

```bash
uvx ruff check --fix && uvx ruff format
git add src-tauri/src-python/adb_auto_player/games/clash_of_critters/formation_view.py src-tauri/src-python/tests/games/clash_of_critters/test_formation_view.py
git commit -m "feat: add the Võ Đường mode to the CoC formation view"
```

---

### Task 2: The element in the name of an unrecognized crop

**Files:**
- Modify: `.../clash_of_critters/card_recognition.py` (`recognize`, `_save_unrecognized`), `.../clash_of_critters/card_teaching.py` (`_crops`)
- Test: `tests/games/clash_of_critters/test_card_recognition.py`, `tests/games/clash_of_critters/test_card_teaching.py`

**Interfaces:**
- Consumes: `ELEMENTS` (from `tatari_db`), `classify_element`.
- Produces: `CardRecognizer._save_unrecognized(self, card_bgr: np.ndarray, element: str | None = None) -> None` writes `<element>_<12 hex>.png` when `element` is given, `<12 hex>.png` otherwise. `recognize` passes the element only when the caller supplied it. `card_teaching._crops` takes the element from a file-name prefix that is in `ELEMENTS`, else from `classify_element` as today. `load_waiting_cards` and `teach_card` keep their signatures.

- [ ] **Step 1: Write the failing tests**
  - `test_card_recognition.py::test_unrecognized_card_with_a_known_element_is_saved_with_its_prefix`: a recognizer with `debug_dir=tmp_path`, an unrecognizable card, `recognize(card, element="grass")` leaves exactly one file matching `grass_[0-9a-f]{12}\.png`.
  - `test_unrecognized_card_without_a_known_element_keeps_the_plain_name`: `recognize(card)` of a card whose icon reads as an element leaves `[0-9a-f]{12}\.png`.
  - `test_a_prefixed_and_a_plain_crop_of_the_same_card_are_saved_once`: after a plain crop exists, `recognize(same_card, element="grass")` adds no file.
  - `test_card_teaching.py::test_prefixed_crop_is_listed_with_its_element_even_when_the_icon_reads_none`: a flat grey image saved as `grass_abc123abc123.png`; `load_waiting_cards(...).cards[0].element == "grass"` and `"grass" in choices`.
  - `test_teach_a_prefixed_crop`: `teach_card(..., "grass_abc123abc123", "grass-4-4") == "ok"`, the crop is deleted, the template exists; with an evolution of another element it returns `"wrong_element"` and the crop stays.
  - `test_plain_crop_is_still_classified_by_colour`: an existing-style fixture still lists as before.

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest src-python/tests/games/clash_of_critters/test_card_recognition.py src-python/tests/games/clash_of_critters/test_card_teaching.py -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement** `_save_unrecognized`'s `element` parameter and name rule, the one-line change in `recognize` (remember whether the caller passed `element` before it is reassigned from the icon colour), and the prefix rule in `_crops` (split the stem on the first `_`). Keep the dedup loop of `_save_unrecognized` untouched (it globs `*.png`).

- [ ] **Step 4: Run to see them pass**, same command; all pass.

- [ ] **Step 5: Lint and commit**

```bash
uvx ruff check --fix && uvx ruff format
git add -A src-tauri/src-python/adb_auto_player/games/clash_of_critters src-tauri/src-python/tests/games/clash_of_critters
git commit -m "feat: keep the dojo element in the name of an unrecognized crop"
```

---

### Task 3: IPC command and generated client

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/__main__.py` (`FormationViewBody`, `get_formation_view`)
- Regenerate: `src/client/` (never by hand)

**Interfaces:**
- Consumes: Task 1's `load_formation_view(stage_text, mode=..., element=...)`, `ViewMode`.
- Produces: `FormationViewBody` with `mode: ViewMode = "battle"` and `element: str | None = None`; `getFormationView({profile_index, stage, mode, element})` in the TS client; `FormationView` gains `element` and `mode`, status gains `"element_unreadable"`.

- [ ] **Step 1: Implement** the two body fields and pass them: `ctx.run(load_formation_view, body.stage, mode=body.mode, element=body.element)` (use a lambda if the executor call does not take keyword arguments).
- [ ] **Step 2: Regenerate the client** with the repo's bootstrap (`pnpm pytauri`, from the repo root). Expected: `src/client/_apiTypes.d.ts` shows `mode` and `element` on the body and the new status/fields on the response. If the script does not regenerate it, find how the repo regenerates it (see `scripts/pytauri-bootstrap.cjs`) and use that; do not hand-edit.
- [ ] **Step 3: Check types** with `pnpm check` (the viewer page may still type-check; fix only what this task breaks).
- [ ] **Step 4: Commit**

```bash
uvx ruff check --fix && uvx ruff format
git add src-tauri/src-python/adb_auto_player/__main__.py src/client
git commit -m "feat: pass the viewer mode and element to get_formation_view"
```

---

### Task 4: Open the viewer from the dojo card

**Files:**
- Modify: `src/lib/formation/viewer.ts`, `src/lib/components/modern/TaskCard.svelte`, `src/lib/formation/stage.ts`
- Check: `src/routes/(app)/+layout.svelte:107` keeps calling `openFormationViewer(profile, "cards")` unchanged.

**Interfaces:**
- Produces:
  - `export type ViewerMode = "battle" | "dojo"`
  - `openFormationViewer(profileIndex: number, tab?: "cards", mode?: ViewerMode): Promise<void>`. A new window gets `&mode=<mode>` (default `battle`) in its URL. For an open window, the refresh event payload is `{ profile_index, mode? }` with `mode` only when the caller passed one, so the auto-open event of a dojo run never flips an open dojo viewer back to battle.
  - `stepStage(stage: string, delta: -1 | 1, maxStage = MAX_STAGE_NUMBER): string | null` (the page passes 10 in dojo mode; below 1 or above `maxStage` returns null).
  - `TaskCard.svelte`: task-key -> mode map `{ "Clash of Critters::clash_of_critters.auto_battle": "battle", "Clash of Critters::clash_of_critters.badge_dojo": "dojo" }`; the button shows for both keys and calls `openFormationViewer(profiles.active, undefined, mode)`. Same icon and style as today.

- [ ] **Step 1:** Implement the three edits above (keep the `opening` single-flight guard of `viewer.ts`).
- [ ] **Step 2:** `pnpm check` and `pnpm prettier-write`; expected: no new errors.
- [ ] **Step 3: Commit**

```bash
git add src/lib/formation src/lib/components/modern/TaskCard.svelte
git commit -m "feat: open the formation viewer from the Võ Đường card"
```

---

### Task 5: Viewer page in dojo mode

**Files:**
- Modify: `src/routes/formation-viewer/+page.svelte`, `src/lib/components/formation/FormationGrid.svelte`, `src/lib/i18n/vn.json`

**Interfaces:**
- Consumes: Task 3's `getFormationView({profile_index, stage, mode, element})` and `FormationView.element` / `.mode`; Task 4's `ViewerMode`, `stepStage(..., maxStage)`, the `mode` URL param and the refresh event payload `{ profile_index, mode? }`.
- Produces: `FormationGrid.svelte` props gain `rows?: number` and `columns?: number` (defaults 5 and 5); it draws exactly `rows x columns` cells (dojo: 4 rows, 3 columns), so cells outside the map are not drawn, and cells keep about the size of the 5x5 grid (cap the grid width in proportion to `columns / 5`).

- [ ] **Step 1: Page state.** `mode` (from the `mode` URL param, default `battle`), `element: string | null`. Every `load` sends `mode` and `element`; an answer with `element` sets `element`. A refresh event with a `mode` that differs from the current one switches mode, clears the view, the stage box and `element`, and reloads from the screen; a refresh event without `mode` keeps the mode. In dojo mode the stage `-`/`+` buttons use `maxStage = 10`, and a load triggered by a typed or stepped stage sends the known `element`.
- [ ] **Step 2: Element row (dojo mode only).** Next to the stage box show the detected element as a small badge; clicking it opens a row of 5 chips (water, fire, grass, rock, lightning). The row also opens by itself on `element_unreadable`. Picking a chip sets `element` and reloads with the current stage text (or from the screen when the box is empty).
- [ ] **Step 3: Problem text** for `element_unreadable`, e.g. "Could not tell the element from the tray. Pick it below." and the five element labels; add the English keys with Vietnamese values to `src/lib/i18n/vn.json` (follow the existing keys, e.g. `"Show formation": "Xem đội hình mẫu"`). The stage placeholder in dojo mode is `4-2`. The `no_formation` text keeps naming the stage.
- [ ] **Step 4: Grid.** In dojo mode render `<FormationGrid rows={4} columns={3} ...>`; battle mode keeps the defaults.
- [ ] **Step 5: Verify.** `pnpm check` and `pnpm prettier-write` pass. Then run the app (`pnpm tauri dev`) with the emulator on a Võ Đường preparation screen: the button on the Võ Đường card opens the viewer, shows "4-x", the element badge and a 3x4 grid; on the camp screen it answers the stage-unreadable text; the Tự Động Chiến Đấu button still shows the 5x5 battle view. Report what was seen, or say plainly if the app could not be run.
- [ ] **Step 6: Commit**

```bash
git add src/routes/formation-viewer src/lib/components/formation src/lib/i18n/vn.json
git commit -m "feat: show the Võ Đường formation in the viewer"
```

---

### Task 6: Docs

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md` (the "Formation viewer" bullet of Auto Battle and the Võ Đường section: the button on the Võ Đường card, `mode`, the element vote and its rule, `element_unreadable`, the 3x4 grid, the `<element>_<hash>.png` crop names; the UI needs a full app build).

- [ ] **Step 1:** Edit the file (CLAUDE.md markdown rules: language on code fences, blank lines around headings and lists).
- [ ] **Step 2: Final check.** Run the touched tests once more: `uv run pytest src-python/tests/games/clash_of_critters/test_formation_view.py src-python/tests/games/clash_of_critters/test_card_recognition.py src-python/tests/games/clash_of_critters/test_card_teaching.py -q`; show the pass count.
- [ ] **Step 3: Commit**

```bash
git add src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md
git commit -m "docs: describe the Võ Đường formation viewer"
```
