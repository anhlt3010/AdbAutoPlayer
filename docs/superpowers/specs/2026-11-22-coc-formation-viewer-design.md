# Clash of Critters: Formation Viewer Window (Design)

Date: 2026-11-22. Status: waiting for the user's approval.

## Intent and why

While arranging the field by hand on the preparation screen, the user wants to see the prepared formation of that stage with the **exact tier** of every tatari. The game's own screen does not show it. The data already exists (`tatari_formations/<chapter>/<stage>.json`, `tatari_db/` sprites); nothing shows it to the user.

First idea was an overlay drawn on the emulator. ADB cannot draw on the device, and a window glued on top of MuMu is fragile, so the user chose a **separate small window** to place next to the emulator.

## What the user gets

- A new button on the "Tự động chiến đấu" card of Clash of Critters, **left of the show/hide (eye) button**.
- Click: the app takes one screenshot of the device, reads the stage ("15-50") from the stage label at the top centre, **on whatever screen the game is on** (no check that it is the preparation screen), and opens a small Windows window with the formations of that stage. The label exists on the preparation and the fight screens; see "Constraints" for the screens without it.
- The window shows a 5x5 field. Each occupied cell shows the sprite of the exact evolution (`evolution_id`), a tier badge (T3, T4, ...), a glitter mark when `glitter` is true, and the name. Header: stage, `Lv <level>` when the formation has one, and a position "2/3".
- Two buttons, previous and next, move between the formations of the stage (file order, the same order the auto battle tries them). They are disabled at both ends.
- Clicking the card button again while the window is open re-reads the screen, updates the window and brings it to the front (one window only).
- The window also has a refresh button that does the same re-read.
- **Manual stage:** a text box in the window header shows the current stage and can be edited (type "15-51", press Enter), with `-` and `+` buttons that step the stage number by one inside the same chapter (they do not cross to another chapter). A manual stage needs no device and no screenshot, so it works on camp, victory, defeat and stage map. Typing a stage that does not parse (not "chapter-number") shows an error and keeps the previous formations. Changing the stage starts again at formation 1. The refresh button and a click on the card button go back to reading the screen, replacing the manual stage.

```text
┌ [-][15-50][+] · Lv 1475 ─ 2/3 [◀][▶][⟳] ┐
│ ┌────┬────┬────┬────┬────┐           │
│ │ T4 │ T3 │T4✨│ T3 │ T3 │  sprite   │
│ ├────┼────┼────┼────┼────┤  + tier   │
│ │ T4 │ T3 │ T3 │ T3 │ T3 │  + name   │
│ └────┴────┴────┴────┴────┘  (5x5)    │
└──────────────────────────────────────┘
```

## Goals

- Show the exact tier of every unit, from the sprite of its `evolution_id`.
- Work while the auto battle is running or stopped; never disturb a running auto battle.
- Accept any screen: a stage number read from the top-centre label, or typed by the user when the screen has no label.
- When it cannot show a formation, say why in the window: no device, stage unreadable (the screen has no stage label, for example camp, victory, defeat, stage map), stage typed wrongly, no formation file for the stage.

## Non-goals and anti-goals

- No overlay on the emulator, no window that follows MuMu.
- No deploying from the viewer, no editing of formation files, no new formation data.
- No live following of the stage: one read per click or refresh.
- Anti-goal: the click must never tap, swipe or change anything on the device (screenshot only).
- Anti-goal: never show the formation of a wrongly read stage without saying so: a stage that does not parse is an error state, not a guess.

## Constraints from the code

- Stage reading exists: `auto_battle._read_stage()` crops `STAGE_LABEL_BOX` and runs `RapidOCRBackend`, then `formation.parse_stage`. Formations: `formation.load_formations(root, stage)` (follows `shared_with`, skips malformed ones). Sprites: `tatari_db.TatariDb.get(evolution_id).image_path`.
- PyTauri commands live in Python (`__main__.py`, `@tauri_profile_aware_command`); `src/client/` is generated from the Python IPC models, never edited by hand.
- Where the stage number shows (checked on the real captures in `docs/superpowers/specs/assets/`): top centre of the preparation screen and of the fight screen (pill "15-50", about x 440-555, y 30-80). **Not shown** on camp, victory and defeat (the top bar is blurred or absent). On the stage map the numbers sit beside each node (15-47 ... 15-51), not in the top label, so the viewer cannot tell which one is current; it reports "unreadable" there. `STAGE_LABEL_BOX` ends at x 550 and may clip the fight-screen label; the viewer must verify this on the fight capture and, if needed, use its own wider box without changing the auto battle's constant.
- The auto battle runs in its own process; the viewer command runs in the main process, so it needs its own one-off screenshot (not the running task's `Game` object).
- `tauri.conf.json` CSP is `default-src 'self'`, which blocks `data:` images. `capabilities/default.json` only covers the window `main`.
- Frontend rules in `src/CLAUDE.md` (`#lib/` imports with extensions, i18n through `$t`). Python rules in the root `CLAUDE.md` (docstrings outside `games/`, no `time.time`, regression tests for the changed branches, run only the targeted test files).

## Approaches

**Window kind** (decided with the user): a real Tauri window next to the emulator, over an in-app floating panel (hides behind MuMu, covers the app) and over an overlay on the emulator (ADB cannot draw; a transparent window must track MuMu).

**How the window gets its data.**

- A. The main window calls the Python command and pushes the result to the viewer by event. Needs the viewer to be open before the data arrives; two places hold state.
- B. **Chosen.** The viewer window calls the Python command itself on open and on refresh. The card button only opens or focuses the window (and asks it to refresh). The viewer is self-contained, so the refresh button costs nothing extra.

**How sprites reach the page.**

- A. Serve the files from `tatari_db/images/` through Tauri's asset protocol. Needs scope and CSP changes and path handling for dev vs bundle.
- B. **Chosen.** The command returns each sprite as a small base64 PNG data URI inside the response (downscaled, deduplicated per `evolution_id`). One CSP change: `img-src 'self' data:`.

## Design

### Python

- New module `games/clash_of_critters/formation_view.py` (pure logic + one thin screenshot step), so it can be tested without a device:
  - a function that builds the response from a stage and the loaded formations: units with `row`, `col`, `tier`, `glitter`, `name`, `sprite` (data URI or `None` when the evolution is not in `tatari_db`; the window then shows text only), formations in file order, `level`;
  - a function that reads the stage from a screenshot (the top-centre label, `RapidOCRBackend`, `parse_stage`); it does not look at which screen it is.
- New command in `__main__.py` (`@tauri_profile_aware_command`, run in the thread pool like `get_profile_state`): takes `ProfileContext` plus an optional `stage` text (when given, no screenshot is taken and no device is needed; the text goes through `parse_stage`), returns a Pydantic model with a `status` (`ok`, `no_device`, `stage_unreadable`, `stage_invalid`, `no_formation`), the stage text, and the formations. Errors are statuses, not exceptions, so the window can word them.
- Screenshot only, through the existing controller; no input is sent.

### Tauri and frontend

- New route for the viewer (static SPA, so a normal SvelteKit route) holding the 5x5 grid, the prev/next buttons, the refresh button and the stage box with its `-` / `+` buttons (they send the new stage text to the command; the stage the command answers with is what the box then shows). The profile index comes in the window URL.
- The card button opens the window from the frontend with a fixed label (`formation-viewer`); if it exists it is refreshed and focused. Small default size (about 420x560), resizable.
- `capabilities/default.json`: add permissions to create and control the window, and give the new window the same `pytauri:default` access as `main`.
- `TaskCard.svelte` is shared by every task and has three variants (cards, palette, accordion). The new button renders only for the Clash of Critters auto battle task (matched by the task key), left of the eye button, in all three variants.
- All new texts go through `$t` with Vietnamese strings added to the i18n files.

## Tests and checks

- Python: tests for the response builder (formation order, `level`, glitter, unknown `evolution_id` gives no sprite, `shared_with`, stage with no file), and for the stage reading with the real captures in `tests/games/clash_of_critters/data/` (preparation screens give a stage; camp, defeat and victory give `stage_unreadable`). A manual stage is tested too: valid text skips the screenshot step, bad text gives `stage_invalid`, a stage with no file gives `no_formation`. The fight-screen capture (`battle_screen.png`, only in `docs/superpowers/specs/assets/`) is copied into the test data folder and must give "15-50". Run only these test files and show the pass count.
- Frontend: `pnpm check`, `pnpm prettier-write`.
- Manual: with MuMu on a preparation screen and on a fight screen, click the button, move through the formations, change stage, click refresh; also click while the auto battle runs and check it is not disturbed.

## Calls I made (not the user's)

- Screen detection: none, by the user's request ("any screen"). A readable stage is the only condition. Screens with no label (camp, victory, defeat, stage map) report `stage_unreadable`; no fallback to a "last seen" stage, because after a win the next stage differs and a stale stage would be silently wrong.
- Prev/next stop at the ends (no wrap-around).
- The manual `-` / `+` stay inside the chapter and never go below stage 1; there is no upper limit, a stage past the last file simply gives `no_formation`.
- The refresh button and the card button always return to reading the screen, even after a manual stage (the manual stage is a one-off lookup, not a mode).
- One viewer window only; a second click refreshes it.
- Sprites downscaled to roughly 96 px on the longer side; exact size left to the builder.
- Where to place the window on first open (default position) is left to the builder.

## Left to the builder

- The exact way to take the one-off screenshot in the main process (reuse of `AdbController` as `get_profile_state` does).
- Exact Tauri permission names, window size, and visual styling of the tier badge, using the app's existing theme variables.
