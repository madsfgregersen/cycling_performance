# Build plan

Build in this order:

1. **Backend / API** — data model (six buckets, see `architecture.md`) and
   the readiness engine (CTL/ATL/TSB rolling, green/amber/red). Shared
   foundation for both surfaces.
2. **Dashboard** — the validation surface. Plotting the CTL/ATL/TSB curves
   makes it possible to eyeball the readiness computation and catch bad
   logic before it gets compressed into a single indicator.
3. **Telegram** — the daily check-in capture and morning verdict delivery.
   Built once the underlying computation has been visually validated on
   the dashboard.

## Time-sensitive, independent of surface order
The one-time historical backfill (see `backfill.md`) needs 42+ days of
ride history to build CTL. Start it early, regardless of which surface is
being built — it takes real calendar time to become meaningful, and the
target race is approaching.
