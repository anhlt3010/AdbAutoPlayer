# Clash of Critters: Teach the Bot Unrecognized Cards (Design)

Date: 2026-11-23. Status: waiting for the user's approval.

## Intent and why

When the player evolves a tatari, the art of its tray card changes. On the preparation screen the bot then does not recognize the card and the formation is short ("thiếu ..."). The user asked earlier for re-detection; it exists and runs, but it cannot recognize these cards.

How recognition works today (`card_recognition.py`, `CardRecognizer.recognize`):

- Step 1: the player's own templates (`<app config dir>/clash_of_critters_cards/<element>/<evolution_id>.png`, `CardTemplateStore`). An evolved card no longer matches its old template (measured 0.23 against a 0.8 threshold), so step 1 does not hold on to the old tier.
- Step 2: outline + colour matching against the wiki sprites. This is the part that fails. The two cards seen on 2026-11-23 (a `fire-8` burger pig and a `water-10` butterfly, both "Cấp 351") score about 0.31 against a 0.4 threshold, with a margin of about 0.01 over other tatari. The card shows a zoomed, cropped part of the art with the level text on top. Larger sprite sizes (up to 380 px) were tried and did not fix it.
- A failed card is saved to `<app config dir>/clash_of_critters_unrecognized/<sha1 of pixels>.png`. Two cards produced 11 files because the pixels differ slightly between scans.

The user chose to **teach the bot once** per unrecognized card, over full automation, which could guess wrong. The user also chose to do this **in the formation viewer window** (picking from a list with images), over renaming files by hand.

## What the user gets

- During the auto battle, every unrecognized card is saved **once**. A card that matches an already saved unrecognized card is not saved again. The log says how many cards are waiting, in Vietnamese, for example: "Có 2 thẻ chưa nhận ra, mở cửa sổ đội hình để chỉ cho bot."
- The formation viewer window gets two tabs: **"Đội hình"** (the current viewer, unchanged) and **"Thẻ chưa nhận ra (N)"**.
- The second tab shows the saved cards. Clicking a card shows a picker with only that card's element: one row per tatari, with the wiki sprites of its normal tiers and its glitter tiers. The user picks one and presses **Lưu**.
- Saving turns the card into a player template for that evolution id and removes it from the list. All other waiting crops that match the new template are removed too.
- A running auto battle sees the new template at its next tray scan, without being restarted.

```text
┌ [Đội hình] [Thẻ chưa nhận ra (2)] ─────────────┐
│  ┌──────┐  ┌──────┐                            │
│  │fire  │  │water │   ← card crops from game   │
│  └──────┘  └──────┘                            │
│ Selected card: pick the tatari (its element):  │
│  fire-1 [T1][T2][T3][T4]  ✨[T1][T2][T3][T4]   │
│  fire-8 [T1][T2][T3][T4]  ✨[T1][T2][T3][T4]   │
│  ...   (wiki sprite of each evolution)         │
│                                  [Lưu]         │
└────────────────────────────────────────────────┘
```

## Goals

- An evolved (or any unrecognized) card can be taught in a few clicks, once, and is recognized from then on.
- One saved crop per card, not one per scan.
- Works while the auto battle runs; never sends input to the device.

## Non-goals

- No editing or deleting of a template taught by mistake. The user deletes the file in `clash_of_critters_cards/<element>/` (decided with the user).
- No automatic guess or suggestion in the picker.
- No change to the wiki matching (step 2) itself.
- No change to how the auto battle reacts to a short formation (next step of the plan, as today).

## Anti-goals

- A taught card must never be saved under an id that is not in `tatari_db` (`recognize` already ignores such files, but the save command must refuse them).
- Teaching must never delete or overwrite a template of another evolution than the one picked. Saving the same id again replaces that one file only, which is the existing `CardTemplateStore.save` behaviour.
- The viewer must not touch the device.

## Constraints

- **Needs a full app build** (`coc-setup` skill). The new tab, commands and any capability change are not carried by the patch zip.
- The viewer runs in the main process. The auto battle runs in its own process with its own `CardTemplateStore` cache (`_templates`, loaded once per element). A template written by the viewer is invisible to a running auto battle until that cache is refreshed.
- `CardTemplateStore.save` cuts the template from a **full card crop** (`_template_of`, the `CARD_ART_BOX` inset by `_TEMPLATE_MARGIN`). The saved unrecognized files are full card crops (`card_box` size), so they can be passed to it unchanged.
- The element of a saved crop comes from `classify_element` on its `ELEMENT_ICON_BOX`, the same way `recognize` gets it. An unrecognized card always has a known element, because `recognize` returns before saving when the element is unknown.
- Both folders live under `SettingsLoader.get_app_config_dir()`, which is per profile. The viewer commands must use the same profile-aware setup as `get_formation_view` (`@tauri_profile_aware_command`, run in `_executor`).
- Sprites to the page: reuse `formation_view.sprite_data_uri` (96 px PNG data URIs; the CSP already allows `data:`). One element has about 14 tatari x 8 evolutions, about 112 small images.
- `src/client/` is generated from the Python IPC models. Frontend rules are in `src/CLAUDE.md` (i18n through `$t`). Python rules are in the root `CLAUDE.md`: docstrings outside `games/`, regression tests, and run only the targeted test files.

## Approaches

**How the user teaches.**

- A. Rename the saved crop to the evolution id (for example `fire-8-2.png`) and the bot imports it. Python only, so a patch zip is enough, but the user must know the ids.
- B. **Chosen by the user.** A tab in the formation viewer with the card crops and a picker of wiki sprites. Easier to use, but needs a full build.
- Full automation (a better wiki matcher, or using the missing unit of the formation as a hint) was rejected: these cards score too close to other tatari, and a wrong guess deploys the wrong unit.

**How a running auto battle sees a new template** (my call): on a template miss, `CardTemplateStore` re-reads the element folder if the set of file names or any file's modification time changed since it was loaded, before falling back to the wiki matching. On Windows a folder's own modification time does not change when a file in it is overwritten, so the folder time alone is not enough. The cost is a few `stat` calls per miss. A timer, or a message between the processes, would be more moving parts. A file half-written by the other process reads as unreadable and is skipped (existing behaviour), then picked up at the next miss.

## Design

### Python

- `card_recognition.py`
  - Unrecognized crops: before writing, compare the card with the crops already in the debug folder (the same `TM_CCOEFF_NORMED` on the art box that the templates use, with the same 0.8 threshold) and skip it if one matches. Keep the file name scheme.
  - `CardTemplateStore`: reload an element folder when its modification time changed (see Approaches).
- A new pure module, for example `games/clash_of_critters/card_teaching.py`, testable without a device:
  - list the waiting crops: id (file stem), element, the crop as a data URI;
  - list the evolutions of an element for the picker, grouped by tatari, each with id, tier, glitter and sprite data URI (the row is labelled by `tatari_id`; `Sprite` has no name field) (from `TatariDb.sprites_for_element` and `sprite_data_uri`);
  - teach: given a crop id and an evolution id, check that the evolution exists in `tatari_db` and has the crop's element, call `CardTemplateStore.save`, then delete that crop and every other waiting crop that the new template matches. Return a status (`ok`, `unknown_crop`, `unknown_evolution`, `wrong_element`), not an exception.
- `__main__.py`: two new profile-aware commands next to `get_formation_view`: one returns the waiting crops plus the picker data for their elements, and one teaches. Both run in `_executor`.
- Log: after a tray scan in `deploy.py` that left cards unrecognized, one info line with the number of waiting crops (Vietnamese, like the other deploy logs).

### Frontend

- `src/routes/formation-viewer/+page.svelte`: two tabs. The existing content becomes the "Đội hình" tab unchanged. The new tab shows the crops, the picker for the selected crop, and **Lưu**. After saving, it reloads the list. The tab label shows the count. The list is loaded when the window opens, on the refresh button and when the tab is opened.
- New strings go through `$t` with their Vietnamese translations.

### Tests

- Duplicate crop not saved twice; a different card still saved.
- Template store picks up a file added after its first load.
- Teach: ok path (template written, crop and matching duplicates removed), unknown evolution, wrong element, unknown crop.
- Real crops from 2026-11-23 go into `tests/games/clash_of_critters/data/` as fixtures. They are in `%APPDATA%/com.anhlt3010.CocAutoPlayer/0/clash_of_critters_unrecognized/` (profile 0). The `fire-8` card: `26b1a8603831`, `2f741e75f012`, `554c1127ddde`, `90428a0e855c`, `a8205347ff64`, `c407c9cd6b9b`, `d0faeb6166cd`. The `water-10` card: `2a4bb1f46b37`, `8d932cebbbb0`, `eff30e84ab31`, `f8e9b8c1dc1c`. Copy two of each (to test the duplicate skip) and check that the dedup collapses all 11 into 2 and that the two cards do not match each other; if 0.8 does not do it, the builder picks the threshold from these crops.
- Template stays valid after a level-up (my check on the crops): the level text "Cấp 351" is at the top of the card (about y 10-45) and the stars at the bottom (about y 165-190), both outside `CARD_ART_BOX` (y 52-162). The element icon and the skill icon are left of x 50, also outside.

## Left to the builder

- The exact layout and styling of the tab and the picker, within the sketch above.
- The names of the module, commands and IPC models.
- Whether the picker data is sent in the same command as the crops or loaded per element.
