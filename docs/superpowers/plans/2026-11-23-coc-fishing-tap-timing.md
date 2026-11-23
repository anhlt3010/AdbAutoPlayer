# CoC Fishing Timed Taps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Fishing Contest tension bar hit small yellow zones by tapping at a predicted time aimed at the zone centre, with a tunable tap latency.

**Architecture:** Pure helpers in `clash_of_critters/main.py` predict when the bobber reaches the zone centre (with bounces at both bar ends) and decide the delay before the tap. `_play_tension_bar` uses them instead of the "inside the zone now and ahead" test. The latency comes from a new `fishing_contest.tap_lead_seconds` setting.

**Tech Stack:** Python 3.12, numpy, pydantic settings, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-23-coc-fishing-tap-timing-design.md`

## Global Constraints

- Run from `src-tauri/`: `uv run pytest src-python/tests/games/clash_of_critters/test_fishing_contest.py -q`. Run only the targeted test files, never the full suite.
- Lint from the repo root: `uvx ruff check --fix` and `uvx ruff format`.
- Banned: `time.time` (use `time.monotonic`); no magic literals in comparisons (module constants); modern type syntax (`X | None`).
- Do not change `read_tension_bar()`, `fishing_button_state()`, or the cast/reel/popup flow.
- Setting `tap_lead_seconds`: default 0.15, range 0.0 to 0.5. Bar bounce limits: bobber centre between x 380 and x 800.
- `Point` equality is always true in this repo: compare `(p.x, p.y)` if needed.
- Never declare done without showing the pass count of the targeted test file(s).

## Review Focus

- Speed is about 0 (bobber not moving between samples): no tap is scheduled and no division by zero.
- Zone narrower than the bobber or only a few pixels wide: still one tap aimed at the centre.
- Bobber about to bounce at an end before reaching the centre: the prediction accounts for the bounce.
- Bobber exactly on the centre or just past it when the zone is read: no tap for this pass, the next crossing is used.
- A wide zone: still tapped once per crossing, not repeatedly.

---

### Task 1: Prediction helpers

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/main.py` (constants near line 129, functions after `read_tension_bar`)
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_fishing_contest.py`

**Interfaces:**
- Produces:
  - `seconds_to_reach(x: float, velocity: float, target: float, low: float, high: float) -> float | None`: time in seconds until a point at `x` moving at signed `velocity` px/s first reaches `target`, bouncing between `low` and `high`; `None` if `abs(velocity) < _MIN_SPEED`.
  - `plan_tap(bobber: float, speed: float, zone: tuple[int, int], lead: float) -> float | None`: seconds to wait before tapping now, or `None` if the moment is not close yet or already passed. Uses `_BOBBER_MIN_X = 380`, `_BOBBER_MAX_X = 800`, `_TAP_WINDOW_SECONDS = 0.03`.
  - `smoothed_speed(samples: Sequence[tuple[int, float]]) -> float`: signed px/s from `(x, time)` samples (last minus first over elapsed time); 0.0 when fewer than 2 samples or no elapsed time. `_SPEED_SAMPLES = 5` is the length the loop keeps.
  - Constants: `_MIN_SPEED = 50.0` (px/s).

- [ ] **Step 1: Write failing tests** (names and assertions, `pytest.approx` with `abs=1e-6`):
  - `test_seconds_to_reach_moving_toward_target`: `seconds_to_reach(400, 300, 700, 380, 800) == 1.0`.
  - `test_seconds_to_reach_moving_away_bounces_once`: `seconds_to_reach(500, 300, 400, 380, 800)` is `(800-500 + 800-400)/300 = 700/300`.
  - `test_seconds_to_reach_bounces_twice`: `seconds_to_reach(500, -300, 600, 380, 800)` is `(120 + 420 + 200)/300 = 740/300` (left end, then right end, then back to 600).
  - `test_seconds_to_reach_negative_velocity_toward_target`: `seconds_to_reach(700, -300, 400, 380, 800) == 1.0`.
  - `test_seconds_to_reach_slow_speed_is_none`: velocity 10 returns `None`.
  - `test_plan_tap_small_zone_aims_at_centre`: bobber 500, speed 300, zone (596, 604), lead 0.15: centre 600 reached in 1/3 s, tap delay is `1/3 - 0.15`; assert approx.
  - `test_plan_tap_not_close_yet_is_none`: same but bobber 400 (centre 0.67 s away, lead 0.15): `None`.
  - `test_plan_tap_passed_the_centre_is_none`: bobber 610 moving right at 300, zone (596, 604): the next crossing needs a bounce and is far away: `None`.
  - `test_plan_tap_wide_zone_taps_once_per_crossing`: zone (450, 750) centre 600, bobber 560 speed 300, lead 0.15: delay is `max(0, 40/300 - 0.15)` = 0.0; assert `0.0`.
  - `test_smoothed_speed`: samples `[(100, 0.0), (130, 0.1)]` gives 300.0; fewer than 2 samples gives 0.0; equal times gives 0.0.

- [ ] **Step 2: Run to verify they fail** (`ImportError`).

- [ ] **Step 3: Implement the three functions and constants.** `seconds_to_reach` unfolds the bounces: map the position onto a line of period `2 * (high - low)`, move it by `velocity * t`, and solve for the first `t >= 0` where the folded position equals `target` (two candidate unfolded targets: `target` and `2 * high - target`, in the direction of travel). `plan_tap` computes `t = seconds_to_reach(...)`, returns `None` if `t` is `None`, `None` if `t - lead` is above `_TAP_WINDOW_SECONDS` or below `-_TAP_WINDOW_SECONDS`, else `max(0.0, t - lead)`. Zone centre is `(zone[0] + zone[1]) / 2`.

- [ ] **Step 4: Run to verify they pass.** Expected: new tests PASS, existing tests still pass.

- [ ] **Step 5: Commit** `feat: predict the bobber crossing of the CoC fishing zone`.

### Task 2: `tap_lead_seconds` setting

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/settings.py`
- Modify: `src-tauri/settings/ClashOfCritters.toml`
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_fishing_contest.py` (or the existing settings test file if one covers `Settings`)

**Interfaces:**
- Produces: `FishingContestSettings(BaseModel)` with `tap_lead_seconds: TapLeadSeconds` (`Annotated[float, Field(ge=0.0, le=0.5)]`, default 0.15, title "Tap Lead (seconds)", description "Seconds between the tap command and the game seeing the tap. Raise it if taps land late, lower it if they land early."); `Settings.fishing_contest: FishingContestSettings` with title "Cuộc Thi Câu Cá". TOML section `[fishing_contest]` with `tap_lead_seconds = 0.15`.

- [ ] **Step 1: Write failing tests**: `test_fishing_contest_settings_default` (`Settings().fishing_contest.tap_lead_seconds == 0.15`) and `test_fishing_contest_tap_lead_range` (0.51 and -0.01 raise `ValidationError`; 0.0 and 0.5 are accepted). Use `FishingContestSettings` directly if `Settings()` needs a file.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** the model, wire it into `Settings`, add the toml section.
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** `feat: add the CoC fishing tap lead setting`.

### Task 3: Use timed taps in `_play_tension_bar`

**Files:**
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/main.py` (`_play_tension_bar`, remove `_TAP_LEAD_SECONDS` and `_ZONE_MARGIN` if unused afterwards)
- Modify: `src-tauri/src-python/adb_auto_player/games/clash_of_critters/CLAUDE.md` (tension bar paragraph)
- Test: `src-tauri/src-python/tests/games/clash_of_critters/test_fishing_contest.py`

**Interfaces:**
- Consumes: `plan_tap`, `smoothed_speed`, `_SPEED_SAMPLES` (Task 1); `self.settings.fishing_contest.tap_lead_seconds` (Task 2).

- [ ] **Step 1: Write failing tests** driving `ClashOfCritters._play_tension_bar` unbound with a `SimpleNamespace` fake (`get_screenshot`, `tap`, `settings`) and `monkeypatch` of `main.monotonic` and `main.sleep` onto a fake clock that advances on every `sleep`. `read_tension_bar` is monkeypatched to return a scripted bobber path (bobber moving 300 px/s, constant zone), then `None` so the bar ends:
  - `test_tension_bar_small_zone_taps_once_near_the_centre`: zone (596, 604): exactly one tap, issued at a clock time within 0.03 s of `crossing_time - lead`.
  - `test_tension_bar_wide_zone_is_tapped`: zone (450, 750): at least one tap, and no two taps closer than the time of one full bounce.
  - `test_tension_bar_uses_the_setting`: lead 0.3 taps earlier than lead 0.1 by about 0.2 s.
  - `test_tension_bar_no_tap_without_zone`: zone `None` always: no tap.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Rewrite the decision part of `_play_tension_bar`.** Keep the existing zone reading (`seen_zone` accepted only while the bobber is more than `_BOBBER_HALF_WIDTH` outside it; zone forgotten after each tap). Keep the last `_SPEED_SAMPLES` `(bobber, now)` samples (append only when `bobber` changes) and use `smoothed_speed`. When `zone` is known, call `plan_tap(bobber, speed, zone, lead)`; if it returns a delay, `sleep(delay)`, `self.tap(_FISHING_BUTTON, log=False)`, then `zone = None`. Log per tap: `Tap N: bobber x, speed v px/s, zone (l, r), lead s.`
- [ ] **Step 4: Run to verify they pass**, then run `uvx ruff check --fix` and `uvx ruff format` from the repo root.
- [ ] **Step 5: Update the tension bar paragraph of `clash_of_critters/CLAUDE.md`** (timed tap at the zone centre, `fishing_contest.tap_lead_seconds`, new setting appears only after a profile settings reset or edit; a patch zip carries only the Python part).
- [ ] **Step 6: Commit** `fix: aim the CoC fishing taps at the centre of the yellow zone`.

---

**Self-review notes:** spec coverage: helper (Task 1), setting (Task 2), loop change and logging (Task 3), docs (Task 3), tests per spec list (Tasks 1 to 3). Names match across tasks: `seconds_to_reach`, `plan_tap`, `smoothed_speed`, `tap_lead_seconds`, `FishingContestSettings`.
