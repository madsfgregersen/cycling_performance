# Data sources

## Strava (ride data)
OAuth2, webhooks, 1 Hz streams. Client ID `264132`. Rate limits: 100
requests / 15 min, 1,000 / day (read). The starter token has only `read`
scope — an OAuth2 authorization flow requesting `activity:read_all` and
`profile:read_all` is required before ride streams can be pulled.
(Secret and tokens: Railway secrets store only — see `CLAUDE.md`.)

**64-bit IDs (Strava change, effective June 1, 2027):** activity and athlete
`id`s may exceed JavaScript's exact-integer range (2^53). Backend is safe:
`rides_summary.strava_activity_id` is `BigInteger`, and Python ints/`json`
are exact at any size (so we keep reading `id`, not `id_str`). The only risk
was the browser: the dashboard-facing ride lists (`/rides`, `/rides/recent`)
therefore send `strava_activity_id` as a **string**, which the dashboard only
concatenates into URLs (`/rides/{id}`, `/rides/{id}/laps`; FastAPI parses the
path back to int). Keep any new browser-facing ID fields as strings too. We
don't store athlete IDs.

**Which activities count as a ride:** `backfill.BIKE_RIDE_TYPES = {"Ride",
"VirtualRide"}` (checked via `_is_bike_ride`, used by both the webhook path and
backfill). `"VirtualRide"` is Zwift/Swift and other indoor-trainer rides —
Strava labels them with a distinct `type`, so they were silently skipped until
Nov 2026. `"EBikeRide"` is intentionally excluded (motor assist distorts
training load); add it to the set if that ever changes. Road/gravel/MTB all
arrive as legacy `type="Ride"`, so they're already covered.

**Virtual vs outdoor tagging:** `rides_summary.sport_type` stores Strava's
activity type (`"Ride"` / `"VirtualRide"`), set on ingest from
`sport_type` (falling back to `type`). `is_virtual = sport_type ==
"VirtualRide"` surfaces on the `/rides` list and ride detail, drives a
"Virtual" badge + a Type row on the dashboard, and tells the coach (ride
debrief + weekly summary) when a session was indoor (no wind/terrain/GPS,
simulated elevation, trainer power) so it doesn't read anything into route or
hills. `GET /backfill/ride-types` is a one-off that fills `sport_type` on older
rides (NULL only) by re-fetching each activity's type from Strava.

**Laps** (`ride_laps` table, `ride_laps.py`): the athlete's Garmin lap-button
presses (and auto-laps), pulled from `/activities/{id}/laps`. Per-lap averages
(power, HR, cadence, speed, distance, elevation, times) are taken **straight
from Strava's lap object** so they match exactly what the athlete sees in
Strava; only NP, IF, lap TSS, peak power and the Coggan zone (z1–z5 by NP vs
FTP, `readiness.FTP_WATTS`, default 315 W) are computed here. This partitions a
ride so warm-up/cool-down don't dilute the interval work — the coach can
evaluate the work laps on their own. Captured on ride-landed (webhook) and
backfill; `GET /backfill/laps` populates existing rides.

> **Gotcha — map laps by time, not by array index.** A lap's Strava
> `start_index`/`end_index` index into *Strava's* stream arrays, whose length
> can differ from the rows we store on smart-recorded rides (recording gaps),
> so slicing our streams positionally drifts progressively and smears per-lap
> power. Instead we map each lap to our streams by **time**: `start_date` +
> `elapsed_time` give an elapsed-seconds window that lines up with our
> `second_offset`. (Fixed Aug 2026 after per-lap power read wrong vs Strava.)

## Health Auto Export (HAE)
iOS app, Apple Health → backend pipeline. Push-based and foreground-only:
the payload arrives when the phone is first opened in the morning, NOT
autonomously overnight. Architecture treats "morning health data arrival"
as the trigger, not a fixed clock time. Export range must be set to a
rolling "today" window (a frozen date range was a bug).

## Hardware
Apple Watch Ultra (Gen 1), worn overnight for sleep, HRV, respiratory
rate, wrist temperature, resting HR.
