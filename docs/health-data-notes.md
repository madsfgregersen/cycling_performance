# Health data handling — key learnings

- **Two data shapes in HAE payloads.** Branch by metric name — do NOT
  assume a `qty` field exists:
  - Scalar number-streams (`resting_heart_rate`,
    `heart_rate_variability`, `respiratory_rate`,
    `apple_sleeping_wrist_temperature`) have a `{qty, date, source}`
    structure.
  - `sleep_analysis` is a session record with no `qty` — it has
    start/end times and stage breakdowns.
  - Field order is inconsistent — always read by key name, never
    position.
- **Sleep window is the recovery filter.** The `sleepStart` → `sleepEnd`
  window separates overnight recovery signal from daytime noise.
  Overnight HRV and respiratory rate = averages of samples falling
  inside that window. Without this filter, HRV is useless daytime
  scatter.
- **Wrist temperature** arrives as absolute °C (~35.16), not a deviation.
  The app computes its own rolling baseline and deviation — no
  dependence on Apple's native feature.
- **Resting HR lags ~1 day.** Apple computes it late morning; the
  collapse job must tolerate this metric arriving behind the others.
- **HAE sends many `sleep_analysis` records per night, not one — and often
  more than one tracker.** A night arrives as ~10 overlapping cumulative
  snapshots (same `date`/`sleepEnd`, progressively later `sleepStart`, growing
  `totalSleep`) **plus** a second source (AutoSleep) that may cover a
  *different part* of the night — e.g. AutoSleep 22:37–00:47 (pre-midnight)
  while Apple Watch covers 00:16–05:51 (post-midnight). **Downstream must
  collapse to one merged record per night** (`recovery_signals.canonical_nights`,
  reused by the dashboard tile and the coach):
  - Group by the payload's wake-date, `date[:10]` — stable across midnight and
    across the historic +09:00 → CET timezone change (avoids double-counting
    the same night recorded under two offsets).
  - `total` = **interval-union of every window in the night** (time in bed),
    minus the awake time of the fullest record. This matches Apple's "asleep"
    within a few minutes and is never below the largest single session.
  - **Do NOT just take the record with the largest `totalSleep`** (the earlier
    fix): that drops whatever a second tracker covered — it read 5:25 for a
    7:03 night split across Apple Watch + AutoSleep.
  - Stage fields (deep/core/rem) come from the fullest record — indicative; on
    split-tracker nights they can sum below `total`.
- **The morning verdict must not fire mid-night.** It rides the first
  health-sync of the day; a sync at ~01:16 (only a pre-midnight nap recorded)
  would send an incomplete read. `telegram.send_morning_verdict` gates on
  `MORNING_EARLIEST_HOUR` (default 05:00 local, env-configurable); the manual
  test endpoint passes `force=True` to bypass it.
