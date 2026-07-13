# CLAUDE.md

## What this project is
A private, personal cycling training application, built for one user's own
use. It is unrelated to any employer or company and must never be named
after, associated with, or framed as a work project.

## Who I am as your collaborator
I am non-technical. I do not write code. I direct you (Claude Code) via
plain-language instructions. Work with me accordingly:

- Present decisions one at a time, and wait for my explicit confirmation
  before proceeding to the next.
- Before running commands or writing code, explain in plain language what
  it does and why — build my mental model, don't just execute.
- Build in vertical slices: each slice independently deployable and
  testable, rather than large sweeping changes.
- When you're about to change files, show me the plan first and wait for
  my OK.

## Hard security rule — never violate
The Strava Client Secret, Access Token, and Refresh Token must NEVER be
written into this repository — not in code, not in docs, not in config,
not in comments. They live ONLY in the hosting platform's (Railway) secrets
store. The Strava Client ID (264132) is not secret and may appear in the
repo.

## Where the full plan lives
See the `docs/` folder:

- `docs/architecture.md` — the four locked architecture decisions
- `docs/build-plan.md` — build sequence and reasoning (Backend → Dashboard →
  Telegram; this three-phase build is complete and live)
- `docs/data-sources.md` — Strava and Apple Health integration details
- `docs/health-data-notes.md` — key learnings on handling health data
- `docs/backfill.md` — historical data backfill plan
- `docs/race-context.md` — target race and rider background
- `docs/geo-park-training-plan.md` — the original training plan text (now
  seeded into the DB-backed `plan_blocks` table, not read from this file
  directly by the app)
- `docs/coach-brief.md` — **read this before touching any AI coach code.**
  The full spec (character, principles, user stories, build order) plus a
  "Build status" section (§9) documenting what's actually shipped, what
  isn't, and real architecture decisions made during the build that extend
  beyond the original spec — most importantly, the unified conversation
  model behind both Telegram and the dashboard's "Talk to your coach"
