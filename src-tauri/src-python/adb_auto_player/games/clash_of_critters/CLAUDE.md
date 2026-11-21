# Clash of Critters

Game module for Clash of Critters (`com.farlightgames.pgame.gp.vn`, base resolution 1080x1920). Code in `main.py`, settings in `settings.py`, template images in `templates/`.

## Command Categories

| Category | Commands |
| --- | --- |
| Battle | (being rewritten: `auto_battle`, Tự Động Chiến Đấu) |
| Events | `artifact_adventure` (Phiêu Lưu Cổ Vật), `artifact_adventure_limited` (Phiêu Lưu Cổ Vật Giới Hạn), `zobo_hunt` (Săn Bắn Zobo) |

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

- Python code goes to `Lib/site-packages/adb_auto_player/games/clash_of_critters/`: `__init__.py`, `main.py`, `settings.py`.
- Template images go to `games/clash_of_critters/templates/` (the install root, where Tauri bundles resources, per `src-tauri/tauri.bundle.templates.json`). This is the folder the app reads templates from.
- Never include `__pycache__/`, `README.md`, `CLAUDE.md` or tests.
- Default settings (`src-tauri/settings/ClashOfCritters.toml`) are compiled into the app and are not in the install folder; mention to the user that a new setting field only appears after the profile settings are reset or edited, and do not add the toml to the zip unless asked.
- Output: `clash_of_critters_patch.zip` in `N:/00_PersonalProject/AdbAuto-CoC/` by default (or wherever the user names). Print the zip path and its file list when done.

```powershell
$src = "N:\00_PersonalProject\AdbAuto-CoC\GIT\AdbAutoPlayer\src-tauri\src-python\adb_auto_player\games\clash_of_critters"
$stage = Join-Path $env:TEMP "coc_patch"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
$code = "$stage\Lib\site-packages\adb_auto_player\games\clash_of_critters"
New-Item -ItemType Directory -Force $code, "$stage\games\clash_of_critters\templates" | Out-Null
Copy-Item "$src\__init__.py", "$src\main.py", "$src\settings.py" $code
Copy-Item "$src\templates\*" "$stage\games\clash_of_critters\templates"
Compress-Archive -Path "$stage\*" -DestinationPath "N:\00_PersonalProject\AdbAuto-CoC\clash_of_critters_patch.zip" -Force
```

The user extracts the zip into `%LOCALAPPDATA%\AdbAutoPlayer` and overwrites existing files, then restarts the app.
