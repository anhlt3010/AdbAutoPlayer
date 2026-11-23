# CoC fishing: timed taps on the tension bar

Date: 2026-11-23. Size: small change (one function plus one setting).

## Intent and why

In `fishing_contest`, the tension bar needs several hits on a yellow zone that shrinks after each hit. Live runs miss a lot, and the smaller the zone the worse it gets. Two misses were seen:

- the bot does not tap at all while the bobber runs through a small zone;
- the bot taps while the bobber is inside the zone on the captured frame, but the bobber is already outside when the game receives the tap.

Cause (from reading `_play_tension_bar`, to be confirmed by the new log): the bot taps only if the bobber and its position 0.15 s ahead are both inside `[left + 20, right - 20]`. A zone of about 40 px or less has no such window. The 0.15 s lead is a guess and is hard-coded.

## Goals

- Hit small zones: aim at the zone centre instead of requiring a margin on both sides.
- Make the tap latency a visible, tunable number instead of a hidden constant.
- Log enough to tune it: bobber x, speed, zone, predicted time to centre, lead used.

## Non-goals and anti-goals

- No automatic latency calibration (option C of the discussion); it can come later if one number per machine is not enough.
- No change to `read_tension_bar()`, to the button state reading, or to the cast/reel/popup flow.
- Must not make wide zones worse: a wide zone must still be hit as reliably as today.

## Constraints

- Needs device streaming for fresh frames (already required).
- 1080x1920 coordinates; bobber centre runs between about x 380 and x 800 and bounces at both ends (measured earlier, to be kept as constants).
- Ruff rules of the repo (no magic values in comparisons, Google docstrings outside `games/` are not required here).

## Approaches considered

- A. Tune constants (margin shrinking with the zone, longer lead). Smallest, but keeps "tap when inside the zone", so tiny zones still have no window and the latency stays a guess.
- B. Timed tap at the zone centre (chosen). Predict when the bobber reaches the centre and tap at that time minus the latency; the latency is a setting.
- C. B plus automatic latency calibration from hit/miss. Adaptive, but more code, risk of oscillation with few samples.

Chosen: B, because it fixes both misses with no new moving parts. Revisit C only if one latency per machine proves not enough.

## Design

1. New pure helper `seconds_to_reach(x, velocity, target, low, high)` in `main.py`: time until a point moving at a signed `velocity` (px/s) reaches `target`, bouncing between `low` and `high`. Unfolds the bounces; returns `None` when the velocity is about zero. Pure, so it is unit tested without a device.
2. `_play_tension_bar` keeps reading the bar and the zone as today (zone is read only while the bobber is more than `_BOBBER_HALF_WIDTH` outside it, forgotten after each tap). Changes:
   - keep a signed, lightly smoothed speed (average of the last few samples) instead of the last raw one;
   - once the zone is known, compute `t = seconds_to_reach(bobber, speed, zone_centre, low, high)`;
   - when `t - lead` is within one poll step, sleep for the remainder and tap; then forget the zone;
   - the old "inside the zone now and ahead" test is removed.
3. New setting `fishing_contest.tap_lead_seconds` (new `FishingContestSettings` in `settings.py`, wired into `Settings` and `settings/ClashOfCritters.toml`): seconds between the tap command and the game seeing it. Default 0.15 (today's value, my call; the right value is machine specific), range 0.0 to 0.5. A new field appears in an existing profile only after its settings are reset or edited.
4. Log per tap: `Tap N: bobber x, speed v px/s, zone (l, r), centre c, lead s.` so a miss can be read from the log and the lead adjusted.

## Tests (regression)

- `seconds_to_reach`: moving toward the target, away from it (needs one bounce), two bounces, speed about 0, target at an end.
- Tap decision with a fake bar sequence: a 30 px zone gets exactly one tap near the centre crossing; a wide zone is still tapped; a hit forgets the zone.
- Setting default and range.

Run `uv run pytest src-python/tests/games/clash_of_critters/test_fishing_contest.py -q` from `src-tauri/`.

## Left to the builder

- Smoothing window size, the poll step, and the exact bounce constants (taken from the existing measurements).
- Whether to share the lead setting wording with the CLAUDE.md of the game; update `clash_of_critters/CLAUDE.md` tension-bar paragraph to describe the timed tap.
- A patch zip carries the Python part; the new setting field appears only after a settings reset or edit.
