# Architecture — four locked decisions

## Decision 1 — Hosting
Managed application platform: Railway, with an attached managed Postgres
database. Backend is Python / FastAPI. The subdomain `api.<domain>` points
at the platform.

## Decision 2 — Data storage
Postgres, "keep everything." Six buckets:

1. **Rides summary** — one row per ride (headline stats, ride TSS).
2. **Ride detail** — second-by-second (1 Hz) streams.
3. **Health samples** — raw Apple Health samples. Dedup on timestamp;
   sleep dedup on sleepStart/date.
4. **Telegram check-ins** — subjective daily inputs.
5. **Daily readiness** — computed, sacred, actual history only. Sole
   source for the dashboard. Never written to speculatively.
6. **Planned workouts** — future date + target TSS; editable/provisional.

Forward projection (CTL/ATL/TSB from planned workouts) is computed on
demand from Bucket 6 and never written back to Bucket 5.

## Decision 3 — Compute triggers
Three jobs:

1. **Ride-landed** (event-driven, off a Strava webhook): pull the stream
   into Bucket 2, headline into Bucket 1, compute ride TSS.
2. **Health-data-arrived** (fires when HAE POSTs on phone foreground):
   dedup into Bucket 3, collapse the overnight samples into a single daily
   recovery row, then roll CTL/ATL/TSB and write the green/amber/red
   verdict to Bucket 5.
3. **Forward projection** (compute-on-demand only, when the planner is
   edited): never a background job.

## Decision 4 — Interfaces
Two surfaces on top of the shared backend:

- **Dashboard (web)** — the thinking surface: trends, history, and the
  planner with a live projection curve.
- **Telegram** — input + nudge: subjective check-ins in, morning verdict
  out.
