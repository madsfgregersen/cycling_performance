# Data sources

## Strava (ride data)
OAuth2, webhooks, 1 Hz streams. Client ID `264132`. Rate limits: 100
requests / 15 min, 1,000 / day (read). The starter token has only `read`
scope — an OAuth2 authorization flow requesting `activity:read_all` and
`profile:read_all` is required before ride streams can be pulled.
(Secret and tokens: Railway secrets store only — see `CLAUDE.md`.)

## Health Auto Export (HAE)
iOS app, Apple Health → backend pipeline. Push-based and foreground-only:
the payload arrives when the phone is first opened in the morning, NOT
autonomously overnight. Architecture treats "morning health data arrival"
as the trigger, not a fixed clock time. Export range must be set to a
rolling "today" window (a frozen date range was a bug).

## Hardware
Apple Watch Ultra (Gen 1), worn overnight for sleep, HRV, respiratory
rate, wrist temperature, resting HR.
