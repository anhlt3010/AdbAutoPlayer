# Clash of Critters

Game module for Clash of Critters (`com.farlightgames.pgame.gp.vn`, base resolution 1080x1920). Code in `main.py` (commands) and the battle modules below, settings in `settings.py`, template images in `templates/`, tatari data in `tatari_db/` and `tatari_formations/`.

## Command Categories

| Category | Commands |
| --- | --- |
| Battle | `auto_battle` (Tự Động Chiến Đấu) |
| Events | `artifact_adventure` (Phiêu Lưu Cổ Vật), `artifact_adventure_limited` (Phiêu Lưu Cổ Vật Giới Hạn), `zobo_hunt` (Săn Bắn Zobo) |

## Auto Battle (Battle category)

`auto_battle` runs `AutoBattleMixin._run_auto_battle()` (`auto_battle.py`): a loop of `_auto_battle_step()` that reads the screen and acts. `ClashOfCritters` inherits `AutoBattleMixin` -> `DeployMixin` -> `Game`; the game supplies `_tap_common_button()`.

- Screens (templates in `auto_battle.py`): camp (`hub_battle_button`) -> stage map (`stage_map_marker`, then a fixed tap on the big yellow start button at (540, 1690): its label changes) -> preparation (`quick_deploy_button`) -> fight (`fight_button` "Chiến Đấu", or `auto_fight_button` "Tự Động Chiến Đấu" which the same button shows on later stages) -> defeat (`defeat_title`, then `retry_button` "Thử Lại", which goes back to the preparation screen) or victory (`victory_title`, then `continue_button` "Tiếp Tục", which goes back to the stage map and so on to the next stage).
- Preparation screen: the stage ("15-50") is read by OCR from `battle_layout.STAGE_LABEL_BOX`. Each stage gets a **plan** of steps (`_plan_for`): a normal stage is `[Quick Deploy, formation 1, formation 2, ...]`, a **boss stage** (number divisible by 10) is `[formation 1, formation 2, ...]`; no formation file -> `[Quick Deploy]`. Every preparation screen that starts a fight counts as one fight of the current step; after `auto_battle.max_formation_attempts` fights the next step starts, and when the last step is used up the auto battle stops. **A retry of the same step never deploys again** (only Chiến Đấu is pressed; a formation step is deployed again only if the "Đã triển khai" counter shows 0); a new step deploys (Quick Deploy button or the formation). A win clears the plan, so the next visit of that stage starts over. An unreadable stage -> Quick Deploy, outside the plan, and the auto battle stops after more than `max_formation_attempts` lost visits of it. The "Báo Cáo" icon (`prep_report_icon`) only feeds that unreadable-stage counter. Optional `auto_battle.keep_formation_after_win` (off by default): after a win with a formation (deployed or kept) the next normal stages keep the field as it is (these fights are not part of any plan), until a boss (its plan starts) or a loss (the plan of the stage starts at its first step); the field counts as kept only if the counter still shows units. Kept boss formations lost a normal stage in a live run, hence off.
- `auto_battle.max_formation_attempts` (default 3) caps the fights per step (Quick Deploy and each formation); `idle_limit_seconds` stops the loop after a long time without a known screen. The loop also stops when one known screen is seen poll after poll (`idle_limit_seconds / poll_interval_seconds` times).
- Pinball reward upgrade screen (can open after a boss stage): `_close_pinball_reward_screen()` in the auto battle loop, after the common buttons. It needs the gem icon of the reward cards (`pinball_reward_gem.png`) AND the X of the bottom bar (`pinball_reward_close.png`), then taps the X. The X alone is never tapped: the same bottom bar shows on the defeat and stage map screens. Not used by the Events commands.
- Formations: `tatari_formations/<chapter>/<chapter>-<stage>.json` holds `formations[]` (`source`, `level`, `units`), tried in file order; `formation.py` `load_formations` skips a malformed formation and follows `shared_with` only when `formations` is empty. Tatari data: `tatari_db/` (wiki sprites, `tatari_db.json`, `tatari_db.py`). Both folders are bundled (`tauri.bundle.templates.json`) and must be committed for CI builds.
- Deploying (`deploy.py`): clear the field (button at (1000, 880)), then for each element of the formation: filter the tray by element, scan it to its end, walk back to its start dragging the wanted cards (`deployment_plan.py` picks the owned evolution: exact, then same tatari with the nearest tier, higher first). Every drag is checked against the "Đã triển khai: n/15" counter and repeated once. `_deploy_formation` returns `DeployResult(count, needed)` (`needed` = cells with an owned tatari): while the counter is below `needed` it tries the units that failed again for up to `_FILL_ATTEMPTS` (5) rounds without clearing the field. `auto_battle._deploy_current_step` drops an incomplete formation for the next step of the plan (fresh fight count) and stops with an error log when none is left; a formation is never fought with a short field. The wait for the tray to stop gliding after a swipe polls every `auto_battle.tray_settle_poll_seconds` (default 0.5; a new setting field only appears after the profile settings are reset or edited).
- **Drags from the tray must be steep** (|dx| <= 0.5 |dy|): a sideways drag scrolls the tray instead. `battle_layout.plan_drag` goes through a free intermediate cell and then moves the unit inside the field (checked by the target cell changing). The tray keeps gliding after a swipe: wait with `_wait_tray_stable()` before reading it, and find cards by the gaps between them (`find_card_lefts`), not by fixed slots.
- Card recognition (`card_recognition.py`): the card's element from its icon colour; then a template from the player's own earlier cards (`CardTemplateStore`, PNGs in `<app config dir>/clash_of_critters_cards/<element>/<evolution_id>.png`; delete the folder to forget them); only for an unknown card the wiki sprites are matched (outline score + colour score, glitter twin by colour). Deployed cards (dimmed with a green check) are skipped.
- Geometry constants (field cells, tray slots, boxes) are measured on 1080x1920 captures kept in `docs/superpowers/specs/assets/` and `tests/games/clash_of_critters/data/`.
- **`Point` equality is always true in this repo** (a dataclass without fields): compare `(p.x, p.y)` in code and in tests.
- Formation card (`show_formation`, label "Xem Đội Hình", Battle category): `main.py` calls `formation_view.load_formation_view()` (stage typed in `formation_view.stage`, accepts en dashes, or read by OCR from one screenshot when empty: preparation and fight screens only) and `formation_page.render_formation_page()` builds a self-contained HTML page (5x5 grid per formation, sprites as data URIs, names escaped) that is written to `<temp dir>/coc_formation_<stage>.html` and opened with `webbrowser`. If the browser cannot be opened the path is logged. It only takes a screenshot and never sends input. The app runs one task per profile at a time (`start_task` answers "Task is already running!"), so the card cannot run while the auto battle of the same profile runs: stop it first or type the stage. It needs only a patch (no app build); the new setting field appears after the profile settings are reset or edited. The old formation viewer window was removed.

## Events Category Rules

- **Every command in the `Events` category must make sure the pinball screen is open first.** Camp screen shows the "Pinball" tab (`pinball_tab.png`); pinball screen shows the "Camp" tab (`camp_tab.png`; the crop excludes the optional pinball-ball bubble so it matches with or without it). Already on pinball: stay; on camp: tap "Pinball".
- Use the shared helper `_open_pinball_screen()` as the first step after `open_eyes()`. Do not re-implement it per command.
- A new Events command must call `_open_pinball_screen()` first.

Example:

```python
@register_command(gui=GUIMetadata(label="...", category="Events"))
def my_event(self) -> None:
    self.open_eyes(device_streaming=False)
    self._open_pinball_screen()
    ...
```

## Templates

- `templates/pinball_tab.png` is the crop of the "Pinball" tab (bottom-right of the main screen, icon + label, x 880-1060, y 1745-1900 of 1080x1920). Also required: `camp_tab.png` (crop of the "Camp" tab, x 900-1050, y 1790-1900, on the pinball screen).
- The whole `templates/` folder is bundled via `src-tauri/tauri.bundle.templates.json`; no per-file registration is needed.
- `templates/artifact_adventure_icon.png` is the black-cat card on the pinball screen (right side). It is cropped to the ear/eye area (x 930-990, y 725-772) on purpose: the torch count bubble, the number in the middle and the "ends in N days" label are dynamic and must stay out of the crop.
- `templates/zobo_hunt_icon.png` is the golden-trophy card of the Zobo Hunt event (Săn Bắn Zobo) on the pinball screen, cropped to the Zobo face on the trophy (x 948-1000, y 508-555 of a real 1080x1920 screenshot; a downscaled crop does not match); the coin bubble, the number and the "ends in N days" label are dynamic and excluded. `zobo_hunt_start_button.png` is the "Bắt Đầu Ngay" text (x 430-810, y 1795-1865). `zobo_hunt` opens the event (skipped if the start button is already shown), waits 20s so the user can adjust settings, then presses "Bắt Đầu Ngay". In the arena (`zobo_hunt_arena_close.png`, the bottom "X", x 495-585, y 1805-1890) it loops: press each buff whose label is visible (`zobo_hunt_rage_button.png` "Cuồng Nộ" x 900-1050 y 1460-1502, `zobo_hunt_target_lock_button.png` "Khóa Mục Tiêu" x 898-1050 y 1672-1710; while a buff runs (~20s) its label becomes a countdown, so a visible label means ready), then `hold()` the arena centre for 3s to shoot. Stops when the arena is not seen for 60s. A red speech bubble can cover the Cuồng Nộ label briefly; the next loop retries.
- Artifact Adventure templates: `artifact_adventure_start_button.png` (text of "Bắt Đầu Phiêu Lưu!"; the "1x" badge above is dynamic), `artifact_adventure_advance_button.png` ("Tiến Lên" text only; the torch icon changes with the torch type and the torch count below is dynamic, so both are excluded), `artifact_adventure_tap_to_continue.png` ("Chạm điểm bất kì để tiếp tục"). `artifact_adventure` loops over these three screens (plus the fight/retreat, reward and claim screens below); if none is seen for 60s it stops.
- Claim popup (`artifact_adventure_claim_button.png`, "Nhận Ngay" text only, x 385-700, y 1735-1810): the "Bàn Tay Vàng" popup can appear mid-adventure; the loop taps the button to continue.
- Common buttons (any screen, any command): `open_all_button.png` ("Mở Tất Cả" text only, x 648-945, y 1672-1752; the "5/30" badge of the neighbouring "Mở thêm nhóm" button is dynamic) and `ok_button.png` ("OK" text only, x 488-598, y 1738-1802, on the "Phần Thưởng!" screen). `more_group_button.png` ("Mở thêm nhóm" text only, x 330-755, y 1672-1752, when it is the only button on screen; the "5/6" badge above is dynamic). Whenever one is seen it is tapped: the battle loop via `_tap_common_button()` before its normal checks, and the Artifact Adventure loop via `_COMMON_BUTTONS`. Add new always-tap buttons to `_COMMON_BUTTONS` / `_COMMON_BUTTON_LOG`.
- Fight-or-retreat choice (`artifact_adventure_retreat_button.png` / `_fight_button.png`, icon + title only): the win rate is read by RapidOCR from the line under the Fight card and all `N%` values are summed (base + bonus). Fight if the sum is >= `artifact_adventure.min_win_rate_percent` (default 80), otherwise retreat; an unreadable rate also retreats. After a retreat the reward screen is closed with `artifact_adventure_accept_button.png` ("Chấp Nhận").
- `artifact_adventure_limited` shares all logic with `artifact_adventure` via `_artifact_adventure(max_advances)`; it counts "Tiến Lên" presses and stops at the next stage / new-adventure screen once `artifact_adventure.limited_advance_count` is reached (pending tap-to-continue, fight/retreat and reward screens are still handled first).

## Packaging a Patch Zip for the Installed App

When the user asks for a zip of this game to copy into their installed AdbAutoPlayer (`%LOCALAPPDATA%\AdbAutoPlayer`), build it with the layout below so the user can extract it straight over the install root.

- Python code goes to `Lib/site-packages/adb_auto_player/games/clash_of_critters/`: every `.py` file of the folder (`__init__.py`, `main.py`, `settings.py`, `auto_battle.py`, `deploy.py`, `battle_layout.py`, `card_recognition.py`, `deployment_plan.py`, `formation.py`, `tatari_db.py`).
- The data folders `tatari_db/` and `tatari_formations/` go to `games/clash_of_critters/` next to `templates/`.
- Template images go to `games/clash_of_critters/templates/` (the install root, where Tauri bundles resources, per `src-tauri/tauri.bundle.templates.json`). This is the folder the app reads templates from.
- Never include `__pycache__/`, `README.md`, `CLAUDE.md` or tests.
- Default settings (`src-tauri/settings/ClashOfCritters.toml`) are compiled into the app and are not in the install folder; mention to the user that a new setting field only appears after the profile settings are reset or edited, and do not add the toml to the zip unless asked.
- Output: `clash_of_critters_patch_v<version>.zip` two levels above the repo (`N:/00_PersonalProject/AdbAuto-CoC/`) by default, or wherever the user names. Print the zip path and its file count when done.
- Ask the user for the version (`X.Y.Z`) before building; never guess it.

Build it with the script (packages files from git `HEAD`, so commit first) or the `coc-patch` skill, which also drafts the release note:

```bash
python scripts/build_coc_patch.py <version> [--ref <git-ref>] [--out <dir>]
```

The user extracts the zip into `%LOCALAPPDATA%\AdbAutoPlayer` and overwrites existing files, then restarts the app.
