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
