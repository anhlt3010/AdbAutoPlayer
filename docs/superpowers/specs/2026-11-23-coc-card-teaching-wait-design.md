# CoC: wait for the user to teach unrecognized cards (short design)

## Intent

A tray card the bot cannot recognize is treated as "not owned", so a formation looks complete (`needed` is too small) and the bot presses Chiến Đấu with a short field. The user wants the bot to open the formation window for them, wait until every card is taught, then drag the missing tatari and only then fight.

## Goals

- Unrecognized cards found while deploying open the formation window on the "Thẻ chưa nhận ra" tab (event path A below) and the bot waits.
- After the waiting crops are gone, rescan the tray, recompute the plan and place only the missing tatari (no field clear).
- Wait at most `auto_battle.card_teaching_wait_seconds` (default 180, new setting); on timeout the formation counts as incomplete and the plan moves to the next formation (existing `_deploy_current_step` logic).

## Non-goals / anti-goals

- Card picture (level/stars) and Save button layout: already handled by the user, out of scope.
- No change to recognition scoring, templates or the deploy drag logic.
- The bot never fights a formation it knows is short because of waiting cards.
- No Rust changes.

## Constraints

- The task runs in its own process; only logs cross to the main process. A patch zip cannot carry this (frontend + `__main__.py` handler need a full app build).
- The bot cannot tell which waiting crop belongs to which formation cell, so it waits for all crops.

## Approaches

- **A (chosen by the user):** the task logs a record flagged `open_card_teaching`; `TauriQueueHandler` emits the event `formation-viewer:open-cards`; the main window opens/focuses the viewer on the cards tab. Least code, reuses the log path.
- B: Rust opens the window. Works while the main window is hidden, but duplicates the TypeScript open logic.

## Left to the builder

- Where in `_deploy_formation` the wait sits (after each element scan vs. after all scans); `waiting_count()` is the signal, the viewer deleting crops is the release.
- Event payload shape, setting field placement and tests (regression test for the changed branches; targeted pytest only).
