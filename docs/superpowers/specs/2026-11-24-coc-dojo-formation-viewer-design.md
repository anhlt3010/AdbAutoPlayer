# Clash of Critters: formation viewer for Võ Đường Huy Hiệu

Size: a small change (reuses the existing viewer window, no new subsystem). Short design.

## Intent

The "Tự Động Chiến Đấu" card has a button that opens the formation viewer (formation of the current stage, exact tiers; a tab to teach the bot unrecognized tray cards). The user wants the same button on the "Võ Đường Huy Hiệu" card so they can check the formation of a dojo stage and teach the dojo's unrecognized cards. Mostly used to look at the formation of a stage. The user does not want to pick the element by hand.

## Goals

- A button on the `badge_dojo` card opens the existing viewer window in dojo mode.
- Formation tab in dojo mode: stage and element are detected from one screenshot of the preparation screen; the formations come from `tatari_dojo/<element>/`.
- The field grid is 3 columns x 4 rows; cells outside the dojo map are not drawn.
- Unrecognized cards of the dojo show in the cards tab with the right element.

## Non-goals / anti-goals

- No second window, route or copy of the viewer code.
- The viewer still never sends input to the device.
- No change to how the bot deploys or fights.
- Not a failure to show the element picker, but it must not be needed in the normal case.

## Approaches

- Window: reuse the one viewer window with a `mode` (`battle` | `dojo`). A separate dojo window would copy most of the code, so it was dropped. Chosen.
- Element detection: (A) vote of the element icons of the tray cards (`classify_element`), or (B) the same plus a small element picker shown only when the vote fails. The user chose **B**: A alone can fail when the tray holds only 1-2 cards, and B costs almost nothing.

## Design

- Entry: `TaskCard.svelte` maps task keys to a viewer mode: `Clash of Critters::clash_of_critters.auto_battle` -> `battle`, `...badge_dojo` -> `dojo`. `openFormationViewer(profile, tab, mode)` passes `mode` in the URL and in the refresh event; an open viewer in the other mode switches mode and reloads.
- Command `get_formation_view` (`__main__.py`, `formation_view.py`) gets `mode` and an optional `element`. Dojo mode:
  - Stage: OCR of `DOJO_LAYOUT.stage_label_box` ("4-2" = Võ Đường 4, stage 2), `parse_stage`.
  - Element: typed/picked element if given, otherwise the vote over the tray cards of the screenshot (cards cut with the dojo layout, resized to the battle card size like the bot does).
  - Formations: `load_dojo_formations(root / "tatari_dojo", element, stage)`.
  - The response gets `element` and `mode`; new status `element_unreadable` (stage read, element not). A typed stage in dojo mode with no element also answers `element_unreadable`.
- Frontend: formation tab shows an element picker (5 elements) only on `element_unreadable` or when the user changes it; picking reloads. `FormationGrid.svelte` takes `columns` and `rows` (5x5 for battle, 3x4 for dojo) and draws only those cells. Strings in `src/lib/i18n/vn.json`. `src/client/_apiTypes.d.ts` is generated, never edited by hand.
- Cards tab: `CardRecognizer._save_unrecognized` writes `<element>_<hash>.png` when the caller passed the element (dojo does, `_tray_element`); `card_teaching._crops` uses the file-name prefix when it is a known element, else `classify_element` as today. Old crops without a prefix keep working. `teach_card` removes crops by stem, so it needs no change.

## Constraints

- A patch zip carries only the Python part; the button, the mode, the grid and the picker need a full app build.
- Python rules of `CLAUDE.md` (no magic values, docstrings, `Point` compared by `(x, y)`); regression tests only for the changed code (`test_formation_view.py`, `test_card_teaching.py`, recognizer save test), never the full suite.

## Left to the builder

- Exact vote rule. My call: at least 2 cards vote and the top element has strictly more votes than the second; otherwise `element_unreadable`.
- How to cut the tray cards in the viewer (no `Game` object): reuse the helpers of `deploy.py` / `battle_layout.py` for the dojo layout.
- Layout and wording of the picker.
