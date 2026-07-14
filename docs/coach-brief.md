# AI Coach — Build Brief

**For handoff to Claude Code. Read this before writing any coach code.**

This document defines the AI coach: its character, the principles it must never violate, the user stories it serves, the order those stories get built, and the exact contracts for the first slice. It is the intent layer for the coach the same way the plan brief is the intent layer for the calendar. Where it says "the coach," it means the LLM-backed reasoning layer; where it says "the formula," it means the existing readiness computation in the daily-readiness bucket. These are different things and the difference is the whole point of this document.

---

## 1. What the coach is

The coach is an expert cycling performance training partner. It knows the KPIs (CTL, ATL, TSB, ramp rate, EF, decoupling, HRV and resting-HR trends against personal baselines), it reads the athlete's data accurately, and it knows what it takes to reach a target event. It is a training partner, not a dashboard and not a blunt physiologist: honest and direct, but it reads like someone who knows this athlete, their constraints, and their goal.

Two behaviors define it beyond voice:

- **It asks for what it needs.** If an input is missing (e.g. a skipped RPE) it asks rather than guessing.
- **It remembers.** Durable facts about the athlete — constraints, preferences, goal — live in the **plan brief**. "Coach memory" is not a separate store: to remember something is to update the brief; to recall something is to read the brief. There is no other memory.

The coach speaks with **one voice across every surface** — Telegram and the dashboard (both the Coach panel and the "Adjust with coach" brief interface). This is not just tone: there is **one coach brain** — the reasoning plus the brief read/write — and each surface is a thin I/O adapter onto it. The same request produces the same result regardless of where it entered. The system prompt in §6 is that voice, written once and reused verbatim everywhere.

---

## 2. The principles it must never violate

These are non-negotiable. They are what separate a good coach from one that quietly corrupts the architecture.

1. **The coach explains; it never re-derives.** The readiness verdict, its color, and its driver numbers come from the formula (daily-readiness bucket). The coach is handed these and writes the words around them. It must never compute its own parallel verdict, never contradict the score on screen, and never emit a color or a number as if it decided it.

2. **Sacred separation applies to prose too.** The coach reads the computed actual-history layer; it never writes to it. Forward-looking or planned content it produces is written only to the planned-workouts bucket. Actual and planned never mix — in data or in words.

3. **You build, the coach advises.** The plan is athlete-authored at the intent layer (the brief). The coach advises, and — where it writes workouts at all (story 12) — it compiles authored intent into concrete sessions rather than inventing training. See the open item in §8: whether "coach compiles, you approve" satisfies this principle, or whether the coach must stay suggest-only, is undecided and only bites at the plan-compilation slice.

4. **Propose, confirm, write — never silent.** Any coach action that writes to the calendar proposes first, waits for explicit confirmation, then writes. It never silently populates days or weeks.

5. **No invented numbers.** Every figure the coach states must come from data handed to it. It does not estimate, round into precision it wasn't given, or fabricate a metric to fill a sentence.

---

## 3. The user stories

Every story is tagged by what it needs to be built. The Telegram two-way loop is **already engineered**, so the tag is split to reflect that: **[Channel-ready]** means the transport exists and the only remaining work is the coach reasoning; **[Voice]** means one-directional commentary (no reply needed); **[Brief]** means the coach must read and/or write the plan brief; **[Reasoning]** means the hard part is the LLM interpreting free-text or data and deciding what it means.

**Readiness & the morning verdict**
1. Explain the readiness verdict in plain language — which driver is dragging and why — so the athlete understands the number, not just sees it. **[Voice]**
2. Ask how fresh the athlete feels and their work/life stress (1–5 each) each morning, and feed the answers into tomorrow's read. **[Channel-ready]**

**Rides**
3. Post-ride debrief interpreting the ride (EF, decoupling, late-ride fade) against what the session was *for*. **[Voice]**
4. Ask ride feel / RPE after a ride so objective and subjective sit together. **[Channel-ready]**

**Plan & disruption**
5. Nudge on a missed workout — without silently stacking it onto a later day. **[Voice]**
6. Adjust the plan when the athlete reports disruption ("I was sick this week") within the guardrails (event date and taper non-negotiable). **[Channel-ready + Brief + Reasoning]**
7. Co-design the high-level plan structure (blocks, zone focus) with the coach — through **both** the dashboard Plan/brief interface ("Adjust with coach") and Telegram. **[Channel-ready + Brief + Reasoning]** — one coach brain and one brief output behind both entry points; the surfaces are thin adapters, not separate features (see §1).

**Constraints & drift**
8. Flag when the athlete has drifted from their stated constraints (held in the brief) so the brief and reality don't diverge. **[Voice + Brief]**

> Note: "hold the athlete's constraints in the brief" is deliberately *not* a story. It has no trigger of its own — constraints are captured *during* other interactions (co-design, an adjustment, a check-in) and honored by other stories. It is the memory mechanism defined in §1 ("to remember is to update the brief"), and it is the same brief read/write that stories 6 and 7 already build. Story 8 above is the active behavior that stands on it.

**Progress toward the target event**
9. Weekly / end-of-block summary of how the block actually went. **[Voice]**
10. "Am I on track for the event?" — compare trajectory to what the target demands (leans on the forward projection). **[Voice]**

**The Coach panel**
11. Dashboard Coach panel: ask questions about the athlete's own data — the conversational chat interface. **[Channel-ready + Reasoning]** — the largest deferred piece; explicitly last.

> Note: "ask for a missing input rather than guess" is deliberately *not* a story. It never fires on its own — it's a behavior the coach exhibits while composing any other message. It lives in the character definition (§1) and principle 5, not here.

**Plan compilation**
12. Ask the coach to compile the brief into calendar workouts — a single workout, a block, or the full plan to the event — so authored intent becomes a concrete schedule. **[Channel-ready + Brief + Reasoning]**, with autonomy rising sharply across the three scopes:
    - *Single workout* ("push today to tomorrow") — mechanical shuffle, minimal judgment.
    - *Block* ("enter the base block") — bounded content generation.
    - *Full plan* ("everything to the event") — heaviest write in the app; closest to the coach-generated-plan model that was rejected; most guarded; last.
    - Writes only to the planned-workouts bucket. Propose → confirm → write (principle 4).

---

## 4. Build order

Telegram being engineered removes the *channel* blocker but not the *reasoning* or *brief* blockers. Sequence by remaining difficulty, not by tag count.

- **Slice 1 — the daily loop.** Stories 1 + 2. Full spec in §5. Ships first, proves the voice and the subjective-capture value.
- **Slice 2 — the reactive commentary.** Stories 3, 5, 8, 9 — the remaining **[Voice]** stories that push commentary off existing events. No reasoning-on-free-text, no brief-writing.
- **Slice 3 — light asks.** Story 4 — coach asks for a structured input (ride feel / RPE) and stores it. Channel-ready, low reasoning. (The "ask when an input is missing" behavior rides along here and in slice 1 — it is not its own slice.)
- **Slice 4 — brief-writing & interpretation.** Stories 6, 7 — coach reads free-text, decides meaning, updates the brief within guardrails. First genuinely hard reasoning.
- **Slice 5 — plan compilation.** Story 12, in scope order: single workout → block → full plan. Resolve the §8 authorship question before the block scope.
- **Slice 6 — the Coach panel.** Story 11, the conversational interface. Last, largest.

---

## 5. Slice 1 — the daily loop (build this first)

A complete organism on day one: the coach explains today's computed verdict **and** asks the two subjective questions, the reply lands as a check-in, and tomorrow's recompute is smarter for it. No brief-writing, no plan generation. This is the smallest thing that closes the subjective-data gap the whole app exists to close.

### 5.1 Input contract (what the model is handed each morning)

- **The computed verdict and its driver breakdown** — the output of the formula. This is what the coach *explains*; it is never re-derived.
- **Load picture:** CTL, ATL, TSB, and the recent ramp.
- **Recovery signals as deviations from personal baseline** — HRV, resting HR, sleep, wrist-temp deviation, respiratory rate. Deviations, not raw values: the coach cares about "elevated vs. your normal," not the absolute figure.
- **Recent rides:** the last few days — what, and how hard.
- **Last check-in:** yesterday's freshness / work-stress answers.
- **A thin slice of the brief:** goal, the standing constraint (e.g. 3 rides/week), today's planned session, and where the athlete is in the block.

**Deliberately excluded from slice 1:** full ride streams, long history, and the forward projection. Noise for a daily read, or belonging to later stories (10, 12).

### 5.2 Output contract (lightly structured)

The model returns named fields, not free prose. Rendered together they read like the coach talking; separated, the dashboard can reuse the pieces and the existing message length/pill controls can address each independently. Proposed fields:

- `headline` — one line, e.g. "Amber — load's the drag, not sleep."
- `why` — a short paragraph explaining the read in the coach's voice.
- `note` — optional single actionable line for today (e.g. "Keep it easy — your call whether to ride at all.").

The verdict color and all numbers are **passed into** the render, not generated by the model. The coach writes the words around them.

### 5.3 The reply

The same morning message asks freshness and work/life stress, 1–5 each. The engineered Telegram loop carries the reply back as a check-in. Tomorrow's recompute consumes it. That closing of the loop — coach speaks, athlete answers, next read knows — is the point of the slice.

---

## 6. The coach's voice (draft system prompt)

This is the prize: written once, reused verbatim on every surface. Draft — refine against real output during slice 1.

> You are an expert cycling performance coach and training partner for a single athlete. You know the athlete, their constraints, and their goal event, and you speak like someone who does — direct and honest, never generic, never padded. You read the data you are given accurately and you explain it in plain language.
>
> You will be given a computed readiness verdict, its driver breakdown, and supporting data. Your job is to **explain** that verdict — never to recompute it, contradict it, or invent your own. The color and the numbers are decided elsewhere and handed to you; you write the words around them. Never state a figure you were not given. If a figure would help but you don't have it, say so or ask for it rather than guessing.
>
> Focus on what matters today: which driver is dragging the read and why, what it means for the athlete's goal, and — only when useful — one honest note on how to approach the day. Respect the athlete's stated constraints at all times. Keep it short. You are a partner, not a report.

Refinement notes: tune length and directness against the athlete's taste on real mornings; the `headline`/`why`/`note` split maps onto the existing messaging length and pill controls.

---

## 7. Prerequisite

Slice 1 requires an LLM API. Default: the Anthropic API, which needs a new `ANTHROPIC_API_KEY` secret in Railway's secrets store (never in the repo), billed to the athlete's own Anthropic account. This is the athlete's call and cost; it gates the build but not the design.

---

## 8. Open items

- **Story 12 authorship (RESOLVED 2026-07-13).** The decision: *compile-and-approve, one week per approval*. "The coach compiles authored intent, the athlete approves" satisfies *you build, the coach advises* — because the athlete authored the block's intent (phase/focus/zones) and explicitly confirms each result. The guard against overreach into the rejected coach-generated-plan model is scope granularity: at block scope the coach may never write more than **one week per confirmation** (enforced in code — `coach_plan_compile._restrict_to_one_week`), and confirming a week auto-advances to *propose* the next, so the athlete rolls through a block one approval at a time. See §9.
- **Readiness formula.** The formula the coach explains is a separate, still-open design decision (not a coach task). The coach depends on its output shape (verdict + driver breakdown) — coordinate the field names so §5.1 and the formula agree.
- **Voice tuning.** The §6 prompt is a draft; expect to refine length and tone against real slice-1 output before it hardens into the reused-everywhere version.

---

## 9. Build status (updated 2026-07-13)

The entire planned coach scope is shipped and live except two stories the athlete **deliberately parked on 2026-07-13**: story 10 and the full-plan scope of story 12 (12c). Neither is a gap to fill by default — do not pick them up without the athlete explicitly un-parking them. Read this section before touching coach code — it documents real design decisions made during the build, some of which extend beyond what this brief originally specified.

**Shipped:**

| Slice | Stories | What it is |
|---|---|---|
| 1 | 1, 2 | Morning verdict explanation + subjective check-in (freshness/stress) |
| 2 | 3, 5, 9 | Post-ride debrief (EF + decoupling from ride streams), missed-workout nudge, weekly/block summary |
| 3 | 4 | Ride feel / RPE ask, tied to the specific ride that prompted it |
| 4 | 6, 8 | Disruption adjustment (propose-confirm-write) + constraint drift alert |
| — | 7 | Plan structure co-design (the 7-week block plan is now DB-backed and editable, not hardcoded) |
| — | 11 | Q&A about the athlete's own data |
| 5 (12a) | 12 | Single-workout compilation — compile one day's session from block intent |
| 5 (12b) | 12 | Block compilation — compile a block one week per approval, auto-advancing to the next week on confirm (§8 authorship resolved: compile-and-approve, one week at a time) |

**Parked (deferred by the athlete's decision, 2026-07-13 — not a backlog to clear):**
- **Story 10** ("am I on track for the event"). Would need the forward projection (CTL/ATL/TSB to race day) + a sense of what the event demands wired into the Q&A coach context (`coach_context.py`), which today only carries goal facts + planned workouts, not the projection. Read-only [Voice] story; no writes.
- **Story 12c** (full-plan compilation — "everything to the event," the heaviest, most-guarded scope; the §8 decision keeps block fills bounded to one block, so a whole-plan sweep was always going to be its own deliberate scope).

### Story 12 compilation — the compile branch

A **4th reasoning branch** (`coach_plan_compile.py`), classified as intent `compile`, alongside disruption/plan_structure/question behind the same classifier and voice.

- It turns the athlete-authored block intent (phase/focus/zones in `plan_blocks`) into concrete `planned_workouts` rows. Scope — single day (12a) or one week (12b) — is read from the message but **capped to one plan-block week in code** (`_restrict_to_one_week`): the coach can never write two weeks in one approval, even if the model tries. This is the structural enforcement of the §8 "one week per approval" decision, not a prompt request.
- Compilation reuses the disruption flow's write path: proposals are tagged `kind="compile"` (a one-off day/week) or `kind="compile_block"` (an auto-advancing block fill) and applied by `coach_plan_adjust.apply_changes`. No new table or migration — `kind` was already a free-text column.
- **Auto-advance:** confirming a `compile_block` week triggers `propose_next_in_block`, which proposes the next un-filled week of the *same* phase as its own pending proposal. Rejecting a week stops the chain. The chain is bounded to the block (when the phase is complete it stops); sweeping the whole plan to the event is 12c's separate, still-deferred scope.
- The taper/event hard boundary is enforced at both propose and apply time, same as disruption.
- **Title/notes split.** `planned_workouts` has a `title` column (short calendar label, e.g. "Z2 long ride", "Hill reps") separate from `notes` (the full session detail). The coach sets both when it creates a workout; the calendar card shows the title (falling back to the zone label), and clicking a workout opens the full notes in a textarea. Disruption updates leave `title` null on a pure move so a shuffle doesn't wipe the label. A one-off `POST /planned-workouts/backfill-titles` (`coach_plan_compile.backfill_titles`, idempotent) gave titles to workouts created before the split.

### The conversation model — an important extension beyond the original brief

Story 11 was originally scoped as a separate dashboard "Coach panel." During the build, this was reconsidered: rather than a fourth UI surface, Q&A became a **third reasoning branch** alongside disruption and plan_structure, behind the *same* intent classifier. There is one shared orchestrator, `coach_conversation.py`, that is the literal "one coach brain" this brief calls for in §1 — every surface really is a thin adapter onto it:

- **Telegram** and the **dashboard** ("Talk to your coach," reachable both as a full page — the Plan brief sub-page — and as a compact panel docked on the Plan tab itself) are two windows onto the *same* conversation, not separate feeds. A message sent from either surface is visible from both.
- Proactive pushes (morning verdict, ride debrief, missed-workout nudge, weekly summary, constraint drift) are *also* folded into this same unified thread now, interleaved chronologically with the reactive conversation — matching what Telegram already looks like natively.
- Athlete-authored messages log under one event name (`checkin_received`, tagged by source) regardless of which surface or intent triggered them. Coach replies that are part of the conversation (as opposed to internal bookkeeping) log under `plan_thread_coach`. A generic `key=value | text` marker prefix lets a logged message carry metadata (which ride, which date, which proposal) without polluting the displayed text; a `proposal_id` marker gets its live status looked up and rendered as inline Confirm/Reject buttons directly on that message when still pending.
- Telegram's Bot API cannot make a message appear as if the athlete sent it, so when the athlete writes from the dashboard, the bot echoes what they said into the Telegram chat before its own reply (`coach_conversation.echo_athlete_action`) — otherwise the Telegram side would show replies with no visible question.
- The three reasoning tasks (`coach_plan_adjust.py` for disruption, `coach_plan_structure.py` for plan_structure, `coach_qa.py` for question) are independent context-builders sharing only the voice (`coach_voice.py`) and the classifier. Q&A is read-only — it never proposes or writes anything, unlike the other two. It's grounded in `coach_context.py`'s broader aggregator plus recent thread history (so follow-up questions work like a real conversation).
- Both propose-confirm-write flows (disruption → `planned_workouts`, plan_structure → `plan_blocks`) share one `plan_adjustment_proposals` table, distinguished by a `kind` column. The taper/event-date guardrail is enforced in code twice — once when a change is proposed, again when it's confirmed — never left to the prompt alone.
- The race goal itself (name/date/distance/elevation/hills) moved from hardcoded Python into a DB-backed `race_goal` table, editable from the brief page. Editing it does *not* reshape the block calendar — that stays a separate, deliberate co-design action.
- `ai_coach.py`'s two Claude-calling functions fail safe (return `""`/`{}`) on any exception now, rather than raising — an earlier version could 500 the Telegram webhook on a transient API hiccup and go completely silent with no diagnostic trace.
- **Model selection is DB-backed and switchable at runtime.** `ai_coach` no longer hardcodes `ANTHROPIC_MODEL`; it reads the active model per call via `llm_usage.get_active_model` (an `app_config` key/value row, falling back to the `ANTHROPIC_MODEL` env then the catalog default). The dashboard Logs page has a dropdown (Opus 4.8 / Sonnet 5 / Haiku 4.5) that switches it instantly — no redeploy. The switchable catalog + pricing lives in `llm_pricing.py`.
- **API cost monitoring.** Every Claude call records model, workload category, tokens, and computed cost to the `llm_usage` table (`llm_usage.record_usage`, fail-safe — never breaks a reply). The Logs page shows cost-per-day and cost-by-category from `GET /llm/cost`. Categories are the coach's jobs (morning_verdict, ride_debrief, compile, qa, disruption, plan_structure, intent_classify, workout_title, etc.). Tracking starts at ship time; earlier calls weren't recorded.

### Where to look

- `coach_conversation.py` — the orchestrator; start here.
- `coach_context.py` — the broad data aggregator Q&A reads from.
- `coach_plan_adjust.py` — disruption reasoning + both intent classifiers (message intent, proposal-reply decision).
- `coach_plan_structure.py`, `coach_qa.py` — the other two reasoning branches.
- `plan_constraints.py`, `plan_blocks.py`, `race_goal.py` — the athlete-editable "brief" data (constraints list, block structure, goal facts).
- `telegram.py` — transport only now; the proactive `send_*` functions plus the webhook handler, no reasoning of its own.
- `backend/app/static/dashboard.html` — `view-brief` (full conversation + constraints + goal editor) and the compact panel embedded in `view-plan`.
