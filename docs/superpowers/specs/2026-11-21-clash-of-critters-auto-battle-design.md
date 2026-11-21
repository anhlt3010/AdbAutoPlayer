# Clash of Critters: Auto Battle Rewrite (Design)

Date: 2026-11-21. Status: waiting for the user's approval.

Screens used as evidence are in `assets/` next to this file (real 1080x1920 captures from MuMu, `127.0.0.1:16384`).

## Intent and why

The current "Tu Chien Dau" command (`keep_game_running`) is a simple loop: it restarts the game if needed, walks to the battle preparation screen, and presses Quick Deploy once when it sees at least N red Dislike icons. It never chooses a formation and its Quick Deploy handling is poor.

The new auto battle reads the stage the player is on, and:

- On a normal stage it presses the game's own **Trien Khai Nhanh** (quick deploy) and fights.
- If the stage was already lost once, or the stage is a **boss stage**, it loads the prepared formation from `tatari_formations/` and drags the player's tatari into the right cells before fighting.

The user wants this started from the main menu button "Tu Dong Chien Dau" and run as a fixed script.

## Goals

- One command, run from the main menu, that plays the whole loop: map, preparation, battle, defeat, retry.
- Read the stage number ("15-50") from the preparation screen.
- Recognize which tatari the player owns from the tray cards, mapped to `evolution_id` of `tatari_db`.
- Deploy a formation from `tatari_formations/<chapter>/<stage>.json` by drag and drop, substituting owned evolutions when the exact one is missing.
- Remove the old auto battle handling first.

## Non-goals and anti-goals

- **Win screen handling is out of scope for now** (the user will supply it later). Until then the bot must not do anything destructive on an unknown screen; it logs it and stops after the idle limit (see Flow).
- Do not touch Artifact Adventure, Zobo Hunt, the pinball logic, or `_COMMON_BUTTONS`; they share code with the old command and must keep working.
- Do not edit or delete `tatari_db/` or `tatari_formations/` (the user's data).
- Anti-goal: starting a battle with an empty field, or looping forever on a stage that keeps losing (see "My calls").

## Facts observed on the real screens

- Main (camp) screen: bottom-left "Chien Dau" button, about (110, 1820).
- Stage map: big yellow button at the bottom (about (540, 1690)) opens the preparation screen. Its label changes (it showed "Trum!"), so the old `stage_start_button.png` may not match every stage.
- Preparation screen:
  - Stage label top centre, "15-50" (about x 400-540, y 30-85). Easy to OCR with `\d+-\d+`.
  - Player field is **5x5**. Cell centres approximately x = 300/420/540/660/780, y = 490/610/730/850/970. Calibrate against `assets/prep_screen_*.png`.
  - Counter "Da trien khai: n/15" at about y 1140 (max 15 tatari).
  - Tray: 2 rows x 6 visible columns of cards, **scrolls horizontally**. Card centres about x = 110/288/466/644/822/1000, y = 1285 and 1480. Each card shows full art on an orange background, an element icon (top-left), the level ("Cap 299") and stars. Stars are not the evolution tier; the evolution is only recognizable from the creature's shape.
  - Element filter row at y about 1665; **Tat ca** is selected by default.
  - Buttons: "Trien Khai Nhanh" about (390, 1800), "Chien Dau" about (845, 1800).
  - **Clear field button**: the right-edge button with a download-style icon at about (1000, 880). One tap clears the field (counter goes 15/15 to 0/15), no confirm dialog. The padlock-like button below it (about (1000, 1015)) is **not** the clear button; do not use it.
  - A **"Bao cao" (Report) icon** appears on the left, just above the tray, only after the stage was lost at least once. Use it as the "lost before" signal.
- Battle: runs automatically (x4 speed in the capture), the stage label stays on top.
- Defeat screen: large "That Bai" title, buttons **"Thu Lai"** (about (390, 1665)) and "Nang Cap". "Thu Lai" returns to the preparation screen (told by the user, not tested).

## Flow (script of the command)

State machine over a screenshot loop. Templates/OCR decide the screen, the first match decides the action:

- Game not running: start it and wait (keeps the existing restart behavior, see "My calls").
- Common buttons ("Mo Tat Ca", "OK", "Mo them nhom"): tap them, as in other commands.
- Camp screen: tap "Chien Dau".
- Stage map: tap the yellow start button.
- Preparation screen:
  - Read the stage.
  - Mode = formation if the stage is a boss (`stage_number % 10 == 0`, e.g. 15-10, 15-50) **or** the "Bao cao" icon is visible. Otherwise mode = quick deploy.
  - Quick deploy: tap "Trien Khai Nhanh" once, then "Chien Dau".
  - Formation: run the deploy procedure below, then "Chien Dau".
- Battle in progress: wait (poll).
- Defeat ("That Bai"): tap "Thu Lai" (back to the preparation screen, where "Bao cao" now shows and formation mode is chosen).
- Victory: **not handled yet.** Any unrecognized screen is logged; if nothing recognizable is seen for a configurable idle limit the command stops with a warning.

## Tatari recognition (approach 2, chosen)

1. For each visible tray card, classify the **element** from the icon at the top-left (fire, water, grass, rock, lightning).
2. Restrict candidates to the `tatari_db` entries of that element (about 100 of 500).
3. Match the card's creature art against the candidates' wiki sprites (transparent PNGs, same art as the game) and pick the best score above a threshold. Wiki and in-game art match visually; the card only crops and overlays it.
4. Store the result as a per-profile JSON cache (card art hash to `evolution_id`) so the same card is not matched again.
5. Cards below the threshold are logged and their crop saved for the user to inspect; they are treated as unknown (unusable) rather than guessed.

The builder chooses the exact matching method (multi-scale alpha-masked template matching vs feature matching); this must be validated against the real tray in `assets/prep_screen_cleared.png` (12 cards visible) before being relied upon. Evolutions of one family look alike, so the validation must check them specifically.

## Formation planning (pure logic)

- Load `tatari_formations/<chapter>/<stage>.json`; follow `shared_with` when it points to another stage.
- Each unit has `row`, `col` (1-5), `tatari_id`, `evolution_id`, `tier`, `glitter`.
- Pick an owned card for each unit, each card used once, in this order:
  1. exact `evolution_id` and same glitter;
  2. same `evolution_id` ignoring glitter;
  3. same `tatari_id` with another evolution: nearest tier first, a **higher** tier preferred over a lower one at equal distance;
  4. none owned: leave the cell empty and log it.
- Units are placed in the order of the file.

## Deploy procedure (formation mode)

- Tap the clear button, verify the counter reads 0/15.
- For each planned unit: if its card is not visible in the tray, scroll the tray horizontally until it is; drag the card to the cell `(row, col)`.
- After all drags read the counter and log expected vs actual deployed count.
- If nothing could be deployed, do not press "Chien Dau"; stop with a warning.

## Constraints

- Python only (`games/clash_of_critters/`), following the repo rules in `CLAUDE.md` (ruff, Google docstrings outside `games/`, no `time.time`, PLR2004 constants, modern type hints).
- Resolution fixed at 1080x1920 (`base_resolution`).
- Data bundling: `tatari_db/` is about 70 MB on disk (some wiki sprites are about 1000 px wide) and `tatari_formations/` has about 5,500 small files. Neither is covered by `src-tauri/tauri.bundle.templates.json` (it only bundles `templates/`). The builder must add them to the bundle and should consider shipping downscaled sprites.
- Per `CLAUDE.md`: targeted tests only, a regression test per bug fix, and the final report must show the pass count of the targeted test files.

## Approaches considered (for tatari recognition)

1. Match directly against all 500 wiki sprites: no extra data, but slow and prone to confusing evolutions of one family.
2. **Chosen:** element pre-filter, then match, with a per-profile cache. Faster and fewer false matches.
3. Learn from the user labelling cards by hand: most accurate but needs manual work, against the goal of full automation.

## Removal of the old handling (first step, before new code)

Delete from `main.py`: `keep_game_running`, `_keep_alive_tick`, `_quick_deploy_if_needed`, `_quick_deploy_done`, `_NAVIGATION_LOG`, `_FORMATION_FIELD_CROP`, and the battle-only template constants. Delete from `settings.py`: `KeepAliveSettings`, its constants and the `keep_alive` field. Remove the Battle row from `CLAUDE.md`/`README.md` and the `keep_alive` section of `src-tauri/settings/ClashOfCritters.toml` if present. Keep `_tap_common_button`, `_COMMON_BUTTONS`, the Artifact Adventure and Zobo Hunt code, `_open_pinball_screen`, and the event templates. Templates `auto_battling.png`, `auto_battle_button.png`, `dislike_icon.png` are used only by the old flow: remove them. `hub_battle_button.png`, `stage_start_button.png`, `quick_deploy_button.png` may be reused; re-capture any that do not match the current UI.

## My calls (not agreed with the user; to confirm)

- The command is renamed `auto_battle` with label "Tu Dong Chien Dau", category Battle, with a new settings group (`auto_battle`) holding poll interval, startup wait, idle limit and the max formation attempts below.
- Keep "start the game if it is not running" from the old command.
- After a formation attempt is lost, retry the formation up to a configurable `max_formation_attempts` (default 3) and then stop with a warning, instead of looping forever.
- Boss rule is `stage_number % 10 == 0` on the number after the dash.
- Tatari recognition cache is stored in the profile's app config directory.
- On a missing evolution, a higher tier is preferred over a lower one at equal distance.
- Tests: unit tests for stage parsing, boss rule, formation resolver, substitution picker and cache; a card-recognition test on crops taken from `assets/prep_screen_cleared.png`.

## Left to the builder

Exact pixel coordinates and template crops (capture them from the real UI), the matching algorithm and thresholds, the drag duration and scroll step, how to read the counter reliably, file layout inside `games/clash_of_critters/`, and the bundle configuration for the data folders.
