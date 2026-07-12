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

- **Story 12 authorship (unresolved).** Does "the coach compiles the brief into workouts, the athlete approves" satisfy *you build, the coach advises* — or must the coach stay strictly suggest-only, with the athlete placing every workout? Decide before building the block scope of story 12. Does not affect slices 1–4.
- **Readiness formula.** The formula the coach explains is a separate, still-open design decision (not a coach task). The coach depends on its output shape (verdict + driver breakdown) — coordinate the field names so §5.1 and the formula agree.
- **Voice tuning.** The §6 prompt is a draft; expect to refine length and tone against real slice-1 output before it hardens into the reused-everywhere version.
