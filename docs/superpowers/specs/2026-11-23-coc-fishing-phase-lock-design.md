# CoC fishing: phase-locked taps (replaces the timed-tap design)

Date: 2026-11-23. Replaces `2026-11-23-coc-fishing-tap-timing-design.md` (merged in `c0690e83`/`0d28e881`), which a live run on MuMu showed to be wrong.

## What the live run showed

A recording of 7 tension bars (read-only, no input sent) gave:

- The bobber moves on a triangle wave between **x 308 and x 806** (498 px) at about **352 px/s** (half period about 1.41 s). The old constants were 380 / 800 and 300 px/s.
- The H264 stream delivers frames in bursts: stalls of 0.4 to 0.5 s followed by catch-up, 80% of frames within a 0.2 s staleness spread. Speed measured from frame arrival times therefore swings from 0 to 1800 px/s, which broke the timed tap (log: `speed -1785 px/s`, taps 70 px outside the zone).
- Each missed tap costs the player time in the game, so live tests are kept to a minimum.

## Intent

Hit the yellow zone, also small zones, despite the stream timing noise.

## Design

- Model the bobber as the known triangle wave: `L = 308`, `R = 806`, `V = 352` px/s. Only its phase in wall-clock time is unknown.
- `BobberClock` learns the phase from frames. A frame shows the bobber at game time `wall - delay` with `delay >= freshest delay`, so the phase estimate is a lower envelope: it moves earlier when a fresher frame arrives, creeps later by 0.02 s per second (V is not exact), and ignores a frame more than 0.5 s off. A frame counts only when the heading is known (steady move of at least 6 px over the last 4 distinct x values, not within 25 px of an end).
- `plan_tap` finds the next wall time the model puts the bobber on the zone centre, minus `tap_lead_seconds`, and returns the wait when it is within the loop interval (or slightly late while the landing is still inside the zone). Stalled frames no longer matter once the phase is known.
- After a tap the zone is forgotten and not read again for `lead + 0.3 s` (the shrunk zone shows only after the tap landed and a possibly stale frame came in), so a held frame cannot tap twice.
- `fishing_contest.tap_lead_seconds` stays; its meaning is the total delay between a bobber position in the freshest frame and the game receiving the tap (frame delay + tap delay). Default 0.2 s is a guess; it can only be measured by real taps, so the log of every tap shows the numbers needed to tune it.

## Non-goals

- No capture of the emulator window on the PC (decided against).
- No automatic latency calibration.
- `read_tension_bar()` and the cast/reel/popup flow are unchanged.

## Verification

- Unit tests of `BobberClock` and `plan_tap` on synthetic frames with stale and bursty arrival.
- Offline replay of the recorded traces (not committed) comparing predicted and observed bobber x on the freshest frames.
- Live check by the player with at most 2 to 3 casts.
