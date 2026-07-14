# Historical backfill

A one-time bulk import of historical rides is needed to seed CTL history
(42+ days minimum). Time-sensitive given race proximity; run early. Feeds
Buckets 1 and 2 (see `architecture.md`).

## Mechanism (as built)

Not `.fit` files — the backfill pulls from the **Strava API** (`backfill.py`,
`run_backfill`). For each *Ride* activity in the window it stores the headline
summary (Bucket 1) and the second-by-second streams (Bucket 2). It skips
activities already in the DB, so it's **idempotent** — safe to re-run — and it
sleeps 0.5s between rides to stay under Strava's rate limit.

Import alone does **not** compute training load. `run_backfill` writes rides
but not `ride_tss`; `readiness.recompute` fills `ride_tss` for every ride and
rolls CTL/ATL/TSB. So a useful backfill is two steps.

## Running it

Two GET endpoints, in order:

1. `GET /backfill/rides?days=N` — import the last N days (default 60). Use
   `days=180` for ~6 months. Returns `{found, imported, skipped_existing,
   stream_rows_saved}`.
2. `GET /readiness/recompute` — compute `ride_tss` + CTL/ATL/TSB across all
   rides. Returns `{rides_updated, days_computed}`.

A large import can run for minutes; if the HTTP call times out at the edge,
rides still commit ride-by-ride server-side — just re-run the import (skips
existing) and then recompute.

Last full run: 2026-07-13, `days=180` → 43 rides, ~171 days of readiness.
