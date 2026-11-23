# CoC Võ Đường Huy Hiệu: design

Date: 2026-11-24. Status: waiting for approval. Game: Clash of Critters (1080x1920).

## Intent

A command `badge_dojo` (label "Võ Đường Huy Hiệu", category "Chế Độ") that plays the five Võ Đường of the "Võ Đường Huy Hiệu" mode by itself, with the prepared formations in `tatari_dojo/`, so the player gets the badges without tapping.

## Goals

- Open Chế Độ, then the banner (done: `modes_button.png`, `badge_dojo_banner.png`, command `badge_dojo` navigates there).
- Visit the five element tabs (Thủy, Hỏa, Thảo, Thạch, Lôi). Play a Võ Đường only if its "Thử Thách" button is yellow; skip it if grey.
- In a Võ Đường: "Thử Thách", "Bắt đầu" on the current stage, deploy the formation of that stage from `tatari_dojo/<element>/<dojo>-<stage>.json`, press "Chiến Đấu".
- After a win, go on with the next stage of the same Võ Đường. A stage is given up (go to the next element) when every formation of it lost `max_formation_attempts` (default 3) times.
- When everything is done, log a summary of every fight (element, stage, formation, result).

## Non-goals and anti-goals

- No change to how `auto_battle` plays: it must behave exactly as before the refactor (its tests stay green).
- Never press "Chiến Đấu" with a short field (same rule as auto battle: an incomplete formation is dropped for the next one).
- Not building the other "Chế Độ" cards (Khiêu Chiến Trùm, Album Thẻ).

## Measured on the live MuMu (assets in `docs/superpowers/specs/assets/dojo_*.png`)

Chế Độ banner screen: the Võ Đường banner is the second card. Võ Đường screen ("Võ Đường Hệ Thảo Màn 4"):

- Element tabs along the bottom, centres y ~1720, x = 125 (water), 330 (fire), 540 (grass), 745 (rock), 955 (lightning). Close X at (540, 1845).
- "Thử Thách" button x 325-755, y 1430-1560. Colour of the patch x 345-420, y 1445-1475: yellow = mean HSV (24, 244, 253), grey = (0, 0, ~130). Seen today: only grass was yellow (current stage 4-2); water 2/3, fire 1/3, rock 2/3, lightning 1/3 of "Tiến hóa 3 Tatari lên bậc Đỏ", all grey.
- Stage list (after "Thử Thách"): stages stacked bottom to top (4-1 "K.O." at the bottom, 4-2 current, 4-3, 4-4 above). The yellow "Bắt đầu" button sits right under the current stage card, so its position changes: find it by template.

Preparation screen (differs from the auto battle one):

| | auto battle (`battle_layout.py`) | Võ Đường |
| --- | --- | --- |
| Player field | 5x5, columns x 300-780, rows y 490-970, max 15 | 3 columns x 429 / 541 / 654 (edges 373, 485, 598, 710), 4 rows y ~634 / 747 / 860 / 974 (edges 577, 691, 803, 918, 1030), max 5. The row above (464-577) is a neutral row: a drop there does not register (tested) |
| Tray cards | 6 columns, pitch ~178, card 160x190, rows y 1285 / 1480 | 5 columns, pitch ~217.5, card ~194x232 (scale 1.21 of the battle card), card lefts ~35 / 240 / 457 / 674 / 892, centres x ~132 / 337 / 554 / 771 / 989, rows y ~1354 / 1598 |
| Element filter row | y 1665 | none; the tray is already filtered to the Võ Đường element |
| Clear field button | (1000, 880) | (1000, 1040), works (counter back to 0/5) |
| Counter "Đã triển khai: n/5" | box (300,1110,500,1170) | text "n/5" at x ~505-595, y ~1145-1195; use a wider box, about (100, 1130, 630, 1210) |
| Stage label | box (380,25,550,95), "15-50" | "4-2" at x ~530-610, y ~55-100; box about (500, 45, 640, 110); "Cấp.500" below it |
| Tray scroll | horizontal, swipe along the row gap | horizontal, a swipe at y ~1468 moves it |

The game keeps the field of the previous attempt (the screen opened with 5/5), so the formation step always clears first. The measurements above are from pixels of the captures and a drag test (card to y 1000 raised the counter to 1/5, card to y 520 did not); the tray `find_card_lefts` thresholds (gap brightness, card width 154-166) still have to be re-measured for the larger cards.

## Approaches

- **A. Layout object (chosen).** `battle_layout.py` keeps the battle values as the default layout, a second layout holds the Võ Đường values, and `DeployMixin` reads its geometry (field cells, tray slots, card size, boxes, clear point, max units, whether an element filter exists) from the layout in use. Reuses the tested deploy logic, recognizer and card teaching. Costs a careful refactor of `deploy.py` and `card_recognition.py` call sites.
- **B. Copy `deploy.py` as `dojo_deploy.py`.** Safe for auto battle, but duplicates ~500 lines and every future fix.
- **C. New small deployer for the dojo.** Smaller (5 units, no filter), but drops the counter checks, retries and card teaching.

The user picked A.

## Design of A

- `battle_layout.py`: a frozen dataclass `PrepLayout` (field columns x, rows y, max units, tray columns x, tray rows y, card size, element icon and art boxes scaled, tray box, card band rows and card width range for `find_card_lefts`, scroll y and from/to x, clear point, counter box, stage label box, `has_element_filter`). `BATTLE_LAYOUT` equals today's constants (module-level names stay as aliases so existing imports and tests keep working). `DOJO_LAYOUT` has the values above.
- `DeployMixin` gets `_layout` (default `BATTLE_LAYOUT`); the command sets `DOJO_LAYOUT` for its run. `_select_element` does nothing when the layout has no filter. Card recognition crops a dojo card and resizes it to the battle card size (160x190) before `recognize`, so templates and wiki sprites keep working.
- Formations: a loader for `tatari_dojo/<element>/<dojo>-<stage>.json` (`element`, `dojo`, `stage`, `formations[]`, `shared_with` like "1-1 – 1-10", same unit schema as `tatari_formations`). `tatari_dojo/` must be committed and bundled (`tauri.bundle.templates.json`), as `tatari_formations/` is.
- Command flow in `main.py` (or a `dojo.py` mixin): open banner (exists) -> for each tab: tap, read the "Thử Thách" colour, skip if grey -> "Thử Thách" -> loop {find "Bắt đầu" template, tap, read the stage label by OCR, plan = formations of that stage, play the plan with the auto battle fight/attempt counting, on a win go back to the stage list, on every formation lost 3 times leave the Võ Đường and go to the next tab} -> summary log.
- Settings: reuse `auto_battle.max_formation_attempts`; no new setting is needed for the first version.
- Tests: layout values, the yellow/grey button read on the saved captures, the stage label read, the dojo loader (incl. `shared_with`), the command flow with a mocked device, and the auto battle tests unchanged.

## Left to the builder

- Exact pixel re-measurement of card lefts and boxes on the dojo prep screen.
- Template crops: "Thử Thách" is read by colour (no template needed), "Bắt đầu" button, and the preparation-screen check.
- Order of the five tabs: water, fire, grass, rock, lightning (the on-screen order).

## Defeat screen (captured 2026-11-24 after a fight the user started)

- The title "Thất Bại" matches the existing `defeat_title.png` at 0.995, so it is reused as is.
- Buttons at the bottom: a ranking icon (left), a white "Thử Lại" at x ~180-600, y ~1590-1730 (centre ~(390, 1660)), and a green "Trở Về" at x ~640-1060 (centre ~(845, 1660)). The auto battle `retry_button.png` matches only 0.42 here, so the dojo needs its own "Thử Lại" template (cropped to the text).
- "Thử Lại" goes back to the preparation screen of the same stage and keeps the field (counter 5/5 right after), exactly like auto battle. So a retry never needs a new deploy, and the "counter shows 0 -> deploy again" rule of auto battle applies. "Trở Về" was not pressed; it is expected to leave to the stage list (to be confirmed when the flow is built).
## Victory screen (captured 2026-11-24, fight of 4-2 grass won, about 20 s after "Chiến Đấu")

- Before the result a full-screen popup "Đặc Điểm Mới!" (a new trait, here "Người Nhặt Đồ") can show (`assets/dojo_new_trait_popup.png`). A tap on the empty area (540, 1600) closes it and the result screen follows. The loop must tap such popups away (treat "no known screen" as: tap (540, 1600), the same way auto battle taps unknown popups) and not count them as idle forever.
- Result screen (`assets/dojo_victory.png`): "CHIẾN THẮNG!" matches the existing `victory_title.png` at 0.975, so it is reused. Buttons: white "Trở Về" (centre ~(390, 1785)) and green "Tiếp tục" (centre ~(845, 1785)); the auto battle `continue_button.png` matches only 0.64, so the dojo needs its own "Tiếp tục" template (text only). On defeat the same two slots are "Thử Lại" / "Trở Về" at y ~1660, on victory they are at y ~1785: the buttons are found by template, never by a fixed point.
- "Tiếp tục" goes **straight to the preparation screen of the next stage** (4-3, opponent Goz), not to the stage list, and the field of the won fight is kept (counter 5/5 with the old units, `assets/dojo_next_prep.png`). So after a win the loop reads the new stage label, then must **clear and deploy the formation of the new stage** (never trust the kept field: it is the previous stage's formation). The stage list and "Bắt đầu" are only needed once per Võ Đường (the first stage) and after "Trở Về".

## Open (only the user can answer)

1. What the player wants logged in the summary beyond element, stage, formation and result (for example the badge or reward gained)?

## Live run (2026-11-24, MuMu, Võ Đường Thảo, stages 4-3 to 4-10 and the badge)

Verified: navigation from the camp screen, tab colours, stage read, loader, deploy on the dojo layout (5/5), fights, win/loss handling, keeping the field after a win (the loss of a kept fight deploys the stage formation), "Mở Thêm Nhóm" reveal, stage 9 (only "Trở Về") and stage 10 ("Nhận Huy Hiệu") flows, badge screens, return to the Võ Đường screen and the summary. Found and fixed during the run: one tray card read as the wrong element (the Võ Đường element is now passed in), the reveal screen, the single-button win screens, the badge screens. After finishing Võ Đường 4 the grass tab was grey (tier 5 not open), so entering the next tier was not exercised.
Not seen live: "Trở Về" of a defeat screen, a stage given up after all attempts, and Võ Đường of other elements (their buttons were grey).
