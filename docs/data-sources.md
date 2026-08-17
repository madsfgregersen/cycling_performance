# Data sources

## Strava (ride data)
OAuth2, webhooks, 1 Hz streams. Client ID `264132`. Rate limits: 100
requests / 15 min, 1,000 / day (read). The starter token has only `read`
scope — an OAuth2 authorization flow requesting `activity:read_all` and
`profile:read_all` is required before ride streams can be pulled.
(Secret and tokens: Railway secrets store only — see `CLAUDE.md`.)

**Laps** (`ride_laps` table, `ride_laps.py`): the athlete's Garmin lap-button
presses (and auto-laps), pulled from `/activities/{id}/laps`. Each lap's
`start_index`/`end_index` map onto the stored 1 Hz streams; per-lap training
values (avg/normalized power, IF, lap TSS, avg/max HR, cadence) are computed
from that stream slice + the athlete's FTP (`readiness.FTP_WATTS`, default
315 W), and each lap gets an objective Coggan zone (z1–z5 by NP vs FTP). This
partitions a ride so warm-up/cool-down don't dilute the interval work — the
coach can evaluate the work laps on their own. Captured on ride-landed
(webhook) and backfill; `GET /backfill/laps` populates existing rides.

## Health Auto Export (HAE)
iOS app, Apple Health → backend pipeline. Push-based and foreground-only:
the payload arrives when the phone is first opened in the morning, NOT
autonomously overnight. Architecture treats "morning health data arrival"
as the trigger, not a fixed clock time. Export range must be set to a
rolling "today" window (a frozen date range was a bug).

## Hardware
Apple Watch Ultra (Gen 1), worn overnight for sleep, HRV, respiratory
rate, wrist temperature, resting HR.
