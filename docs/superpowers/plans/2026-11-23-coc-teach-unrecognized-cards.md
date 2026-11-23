# Teach Unrecognized CoC Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user teach the bot, once, which tatari an unrecognized tray card is, from a new tab of the formation viewer window.

**Architecture:** The auto battle saves one crop per unrecognized card (deduplicated). A new pure module `card_teaching.py` lists those crops with a sprite picker per element, and turns a crop into a player template. Two PyTauri commands expose it to a new tab of `/formation-viewer`. `CardTemplateStore` reloads an element folder when its files change, so a running auto battle sees new templates.

**Tech Stack:** Python 3.12 (OpenCV, Pydantic, PyTauri), SvelteKit 5 (runes), Tauri 2.

**Spec:** `docs/superpowers/specs/2026-11-23-coc-teach-unrecognized-cards-design.md`

## Global Constraints

- Python rules from the root `CLAUDE.md`: no `time.time`, no `cv2.split`, constants instead of bare literals (PLR2004), modern type syntax. Docstrings are required outside `games/` and `tests/`, so `__main__.py` commands follow the existing pattern there.
- Run only the targeted test files, from `src-tauri/`: `uv run pytest src-python/tests/games/clash_of_critters/<file> -q`. Never the full suite.
- Lint from the repo root: `uvx ruff check --fix` then `uvx ruff format`.
- Template match threshold for crops is the same as for templates: `_TEMPLATE_MIN_SCORE = 0.8`.
- Folders live under `SettingsLoader.get_app_config_dir()`: `clash_of_critters_cards/<element>/<evolution_id>.png` (templates) and `clash_of_critters_unrecognized/<name>.png` (full card crops).
- Teaching refuses an evolution id that is not in `tatari_db` and one whose element differs from the crop's.
- The viewer never sends input to the device.
- User-facing log lines are in Vietnamese, like the other deploy logs. UI strings go through `$t`, with Vietnamese in `src/lib/i18n/vn.json`.
- Needs a full app build; the patch zip is not enough.

## Review Focus

- A `crop_id` that is not a file stem of the unrecognized folder (including `../x` or an absolute path) returns `unknown_crop` and touches no file. Test in Task 3.
- The unrecognized folder missing or empty gives an empty list, not an error. Test in Task 3.
- An unreadable PNG in the unrecognized folder is skipped in the list and in dedup. Tests in Tasks 2 and 3.
- Re-teaching the same evolution id replaces only that template file; other templates of the element stay. Test in Task 3.
- A template file replaced in place (same name, new content) is picked up by a running store. The folder's own modification time does not change on Windows in that case. Test in Task 1.

---

### Task 1: Template store reloads changed folders

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/card_recognition.py` (`CardTemplateStore`)
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_card_templates.py`

**Interfaces:**
- Produces: `CardTemplateStore.match(card_bgr, element)` keeps its signature. When no loaded template scores at least 0.8, it checks the element folder's signature, which is the sorted `(file name, st_mtime_ns)` of its `*.png` files. If the signature differs from the one at load time, it reloads that element and matches again. `save()` updates the stored signature, so the store's own write does not trigger a reload.

- [ ] **Step 1: Write the failing tests** in `test_card_templates.py`, using the existing `cleared` fixture and `_card` helper:
  - `test_store_sees_template_added_by_another_store`: store A and store B on the same `tmp_path`. A does `match(water card, "water")`, which returns None and loads the empty folder. B does `save("water-3-3", water card)`. Then `A.match(water card, "water") == "water-3-3"`.
  - `test_store_sees_template_replaced_in_place`: A saves `"water-3-3"` from `WATER_CARD` and B saves `"water-3-3"` from `OTHER_WATER_CARD`. Bump the file's mtime with `os.utime(path, ns=(t, t + 10**9))` so it surely differs. Then `A.match(other water card, "water") == "water-3-3"`.
- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest src-python/tests/games/clash_of_critters/test_card_templates.py -q`. Expected: the 2 new tests FAIL and the others pass.
- [ ] **Step 3: Implement it.** Add `self._signatures: dict[str, tuple[tuple[str, int], ...]]` and a helper `_signature(element) -> tuple[tuple[str, int], ...]` (an empty tuple when the folder is missing). Then add the reload-on-miss logic in `match` and the signature update in `save`.
- [ ] **Step 4: Run the tests again.** Same command; expected: all pass.
- [ ] **Step 5: Commit.** `git commit -m "feat: reload CoC card templates written by another process"`

### Task 2: One saved crop per unrecognized card, and the log line

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/card_recognition.py` (`CardRecognizer.recognize`, new constants)
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/deploy.py` (`_get_recognizer`, `_deploy_formation`)
- Create fixtures: `src-tauri/src-python/tests/games/clash_of_critters/data/unrecognized_fire_8_a.png`, `unrecognized_fire_8_b.png`, `unrecognized_water_10_a.png`, `unrecognized_water_10_b.png`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_card_recognition.py`

**Interfaces:**
- Produces in `card_recognition.py`:
  - `TEMPLATE_DIR_NAME = "clash_of_critters_cards"` and `UNRECOGNIZED_DIR_NAME = "clash_of_critters_unrecognized"`. `deploy.py` imports these instead of its own `_TEMPLATE_DIR_NAME` and literal.
  - `art_match_score(card_bgr: np.ndarray, other_card_bgr: np.ndarray) -> float`: the template of `other_card_bgr` (`CardTemplateStore._template_of`) searched with `TM_CCOEFF_NORMED` in the `CARD_ART_BOX` of `card_bgr`, with NaN treated as -1.
  - `CardRecognizer.waiting_count() -> int`: the number of `*.png` files in `debug_dir` (0 when it is unset or missing).
- `recognize` saves an unrecognized crop only if no readable PNG already in `debug_dir` has `art_match_score(card, existing) >= _TEMPLATE_MIN_SCORE`. The file name scheme is unchanged.

- [ ] **Step 1: Copy the fixtures.** Source folder: `%APPDATA%/com.anhlt3010.CocAutoPlayer/0/clash_of_critters_unrecognized/`.
  - `d0faeb6166cd.png` becomes `unrecognized_fire_8_a.png`, and `26b1a8603831.png` becomes `unrecognized_fire_8_b.png`.
  - `2a4bb1f46b37.png` becomes `unrecognized_water_10_a.png`, and `8d932cebbbb0.png` becomes `unrecognized_water_10_b.png`.
  - Before committing, check that all 11 files in that folder collapse into 2 groups at 0.8 (7 fire and 4 water; the list is in the spec). If they do not, pick the threshold from those crops and note it in the commit.
- [ ] **Step 2: Write the failing tests:**
  - `test_art_match_score_same_card_scans`: `art_match_score(fire_a, fire_b) >= 0.8` and `art_match_score(water_a, water_b) >= 0.8`.
  - `test_art_match_score_different_cards`: `art_match_score(fire_a, water_a) < 0.8`.
  - `test_unrecognized_card_saved_once`: build a `CardRecognizer` whose `_match` is monkeypatched to return None, with `debug_dir=tmp_path`. Call `recognize(fire_a)`, then `recognize(fire_b)`, then `recognize(water_a)`. Then `waiting_count() == 2`.
  - `test_unreadable_crop_ignored_by_dedup`: write `b"junk"` to `tmp_path / "bad.png"`, then `recognize(fire_a)` saves a file, so `waiting_count() == 2`.
- [ ] **Step 3: Run them and see them fail.** Run `uv run pytest src-python/tests/games/clash_of_critters/test_card_recognition.py -q`.
- [ ] **Step 4: Implement it** as described in Interfaces. Read crops with `cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)`, the same way the store reads templates, so non-ASCII paths work. Skip a crop whose shape differs from the card.
- [ ] **Step 5: Add the log line.** At the end of `_deploy_formation`, after `Đã xếp ...`, if `self._get_recognizer().waiting_count() > 0`, log at info level: `f"Có {n} thẻ chưa nhận ra, mở cửa sổ đội hình để chỉ cho bot."`
- [ ] **Step 6: Run the tests again.** Run `uv run pytest src-python/tests/games/clash_of_critters/test_card_recognition.py src-python/tests/games/clash_of_critters/test_deploy.py -q`; expected: all pass.
- [ ] **Step 7: Commit.** `git commit -m "feat: save one crop per unrecognized CoC card and log how many wait"`

### Task 3: Teaching module

**Files:**
- Create: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/card_teaching.py`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_card_teaching.py`

**Interfaces:**
- Consumes: `TEMPLATE_DIR_NAME`, `UNRECOGNIZED_DIR_NAME`, `art_match_score`, `CardTemplateStore`, `classify_element` (Task 2 / existing); `ELEMENT_ICON_BOX`; `TatariDb.sprites_for_element`, `TatariDb.get`; `formation_view.sprite_data_uri`.
- Produces (Pydantic models, because they go over IPC):

```python
TeachStatus = Literal["ok", "unknown_crop", "unknown_evolution", "wrong_element"]


class WaitingCard(BaseModel):
    id: str  # file stem in the unrecognized folder
    element: str
    image: str  # PNG data URI of the full card crop


class CardChoice(BaseModel):
    evolution_id: str
    tatari_id: str
    tier: int
    glitter: bool
    sprite: str | None


class WaitingCardsResponse(BaseModel):
    cards: list[WaitingCard]
    # Picker data, only for the elements of the waiting cards; sorted by
    # tatari number, then glitter, then tier.
    choices: dict[str, list[CardChoice]]


def load_waiting_cards(config_dir: Path, db: TatariDb) -> WaitingCardsResponse: ...
def teach_card(
    config_dir: Path, db: TatariDb, crop_id: str, evolution_id: str
) -> TeachStatus: ...
```

- `teach_card` finds the crop only by comparing `crop_id` with the stems listed in the folder. It never joins `crop_id` into a path. It saves with `CardTemplateStore(config_dir / TEMPLATE_DIR_NAME).save(evolution_id, crop)`. Then it deletes the crop and every other readable crop whose `art_match_score(other, crop) >= 0.8`.
- Crops whose element is unknown, or which cannot be read, are left out of `cards`.

- [ ] **Step 1: Write the failing tests.** The fixtures from Task 2 are copied into `tmp_path / UNRECOGNIZED_DIR_NAME`. `db` is `TatariDb.load` of the real `tatari_db` folder, as in `test_tatari_db.py`.
  - `test_load_lists_cards_and_choices`: with fire_a and water_a, the result has 2 cards with elements `{"fire", "water"}`. `choices` has the keys `{"fire", "water"}`. `"fire-8-2"` is in the fire choices with a sprite starting `data:image/png;base64,`.
  - `test_load_missing_folder`: returns `cards == []` and `choices == {}`.
  - `test_load_skips_unreadable`: a `bad.png` with junk bytes is not listed.
  - `test_teach_ok_removes_duplicates`: with fire_a, fire_b and water_a, `teach_card(..., "<fire_a stem>", "fire-8-2") == "ok"`. Then `cards/fire/fire-8-2.png` exists, only the water crop is left, and a new `CardTemplateStore` on `cards/` matches fire_b as `"fire-8-2"`.
  - `test_teach_unknown_evolution`: `"fire-99-1"` returns `"unknown_evolution"` and no file changes.
  - `test_teach_wrong_element`: the fire crop with `"water-10-2"` returns `"wrong_element"`.
  - `test_teach_unknown_crop`: `"nope"` and `"../" + stem` return `"unknown_crop"` and no file changes.
  - `test_reteach_replaces_only_that_template`: an existing `cards/fire/fire-1-2.png` is unchanged after teaching `fire-8-2`.
- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest src-python/tests/games/clash_of_critters/test_card_teaching.py -q`.
- [ ] **Step 3: Implement the module.** Encode the crop to a data URI with `cv2.imencode(".png", crop)` and base64.
- [ ] **Step 4: Run the tests again.** Same command; expected: all pass.
- [ ] **Step 5: Commit.** `git commit -m "feat: list and teach unrecognized CoC cards"`

### Task 4: PyTauri commands

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/__main__.py` (next to `get_formation_view`)
- Regenerated: `src/client/*` (by running the app with the generator on, never by hand)

**Interfaces:**
- Consumes: `load_waiting_cards`, `teach_card`, `WaitingCardsResponse`, `TeachStatus` (Task 3).
- Produces two commands for the frontend. Their names in the generated client are `getUnrecognizedCards` and `teachCard`:

```python
class TeachCardBody(ProfileContext):
    crop_id: str
    evolution_id: str


class TeachCardResponse(BaseModel):
    status: TeachStatus


@tauri_profile_aware_command
async def get_unrecognized_cards(
    app_handle: AppHandle, body: ProfileContext
) -> WaitingCardsResponse: ...


@tauri_profile_aware_command
async def teach_card(
    app_handle: AppHandle, body: TeachCardBody
) -> TeachCardResponse: ...
```

- Both run in `_executor` with `copy_context()`, like `get_formation_view`. `config_dir` is `SettingsLoader.get_app_config_dir()`, and `db` is `formation_view._load_db(SettingsLoader.games_dir() / "clash_of_critters" / "tatari_db")`. Make `_load_db` public as `load_db` and update its one caller. Rename the imported `teach_card` (`import ... as teach_card_impl`) so it does not clash with the command name.

- [ ] **Step 1: Add the models and commands.** Each command has a one-line docstring, like `get_formation_view`.
- [ ] **Step 2: Regenerate the TS client.** Run `pnpm tauri dev` from the repo root inside the `AdbAutoPlayer` venv, which sets `PYTAURI_GEN_TS`. Expected: `src/client/apiClient.ts` contains `getUnrecognizedCards` and `teachCard`. Stop the app after that.
- [ ] **Step 3: Check the types and lint.** Run `pnpm check`, then `uvx ruff check --fix` and `uvx ruff format`; expected: no errors.
- [ ] **Step 4: Commit.** `git commit -m "feat: add the CoC card teaching commands"`

### Task 5: "Thẻ chưa nhận ra" tab in the formation viewer

**Files:**
- Modify: `src/routes/formation-viewer/+page.svelte`
- Create: `src/lib/components/formation/UnrecognizedCards.svelte`
- Modify: `src/lib/formation/types.ts` (types derived from the generated client, as the file already does)
- Modify: `src/lib/i18n/vn.json`

**Interfaces:**
- Consumes: `getUnrecognizedCards({ profile_index })` and `teachCard({ profile_index, crop_id, evolution_id })` (Task 4).
- `UnrecognizedCards.svelte` props: `profileIndex: number`, `onCountChange: (n: number) => void`. It loads on mount and when `reloadToken: number` changes (the page bumps it on ⟳ and on the refresh event).

- [ ] **Step 1: Add the tabs to the page.** The page gets two tab buttons: `$t("Formation")` and `$t("Unrecognized cards ({{n}})")`. The existing header, counter, messages and grid make up the first tab, unchanged. The ⟳ button stays in the bar for both tabs.
- [ ] **Step 2: Build the component.**
  - It shows a grid of card images. Clicking one selects it.
  - For the selected card it shows `choices[card.element]` as one row per `tatari_id`: the normal tiers first, then the glitter ones with a ✨ mark, each as a sprite button with a `T<tier>` badge. When `sprite` is null, the badge is shown alone.
  - `$t("Save")` is enabled once a choice is picked. It calls `teachCard` and then reloads. A status other than `ok` shows `$t("Could not save: {{status}}")`. An empty list shows `$t("No unrecognized cards.")`.
- [ ] **Step 3: Add the translations** to `vn.json`: "Formation" → "Đội hình", "Unrecognized cards ({{n}})" → "Thẻ chưa nhận ra ({{n}})", "Save" → "Lưu" (if not present), "Could not save: {{status}}" → "Không lưu được: {{status}}", "No unrecognized cards." → "Không có thẻ chưa nhận ra.", "Pick the tatari of this card" → "Chọn tatari của thẻ này".
- [ ] **Step 4: Check and format.** Run `pnpm check` and `pnpm prettier-write`; expected: no errors.
- [ ] **Step 5: Test by hand.** Copy the 4 fixtures into `%APPDATA%/com.anhlt3010.CocAutoPlayer/0/clash_of_critters_unrecognized/` (back up the folder first), run `pnpm tauri dev`, and open the viewer from the "Tự Động Chiến Đấu" card. Expected:
  - The tab shows 2 cards.
  - Picking `fire-8-2` and pressing Lưu leaves 1 card, and `clash_of_critters_cards/fire/fire-8-2.png` exists.
  - Restore the folder afterwards.
- [ ] **Step 6: Commit.** `git commit -m "feat: teach unrecognized CoC cards from the formation viewer"`

### Task 6: Docs

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md` (the "Card recognition" and "Formation viewer" bullets, and the patch zip file list gains `card_teaching.py`)
- No change to `scripts/build_coc_patch.py`: it already packs every `.py` file of the folder.

- [ ] **Step 1: Update the CLAUDE.md bullets.**
  - Card recognition: one crop per unrecognized card, the reload on miss, and teaching from the viewer.
  - Formation viewer: the new tab and the two commands; this needs a full build.
- [ ] **Step 2: Run the targeted tests one last time.** Run `uv run pytest src-python/tests/games/clash_of_critters/test_card_templates.py src-python/tests/games/clash_of_critters/test_card_recognition.py src-python/tests/games/clash_of_critters/test_card_teaching.py src-python/tests/games/clash_of_critters/test_deploy.py src-python/tests/games/clash_of_critters/test_formation_view.py -q`; expected: all pass, and report the count.
- [ ] **Step 3: Commit.** `git commit -m "docs: describe teaching unrecognized CoC cards"`
