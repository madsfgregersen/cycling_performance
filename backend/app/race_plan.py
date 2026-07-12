# Static reference data mirroring docs/geo-park-training-plan.md.
# A placeholder until the AI coach can generate this -- not database-backed
# or user-editable yet.

GOAL = {
    "name": "Geo Park Gran Fondo",
    "date": "2026-08-30",
    "distance_km": 150,
    "elevation_m": 2000,
    "hills": 12,
}

WEEKS = [
    {
        "week": 1,
        "start": "2026-07-13",
        "end": "2026-07-19",
        "phase": "build",
        "label": "Build",
        "focus": "Wake up the top end",
        "detail": (
            "Reintroduce structured intensity. Threshold: 3x10 min @ "
            "95-100%. VO2 opener: 5x3 min @ ~115%. Long endurance: 3-4 hrs "
            "Z2 over rolling terrain. ~8-10 hrs."
        ),
    },
    {
        "week": 2,
        "start": "2026-07-20",
        "end": "2026-07-26",
        "phase": "build",
        "label": "Build",
        "focus": "Threshold volume",
        "detail": (
            "Push threshold duration; introduce race-specific over-unders. "
            "Threshold: 2x20 min @ 95-100%. Over-unders: 3x[2 min @ 105% / "
            "3 min @ 88-90%]. Long ride: 4 hrs hitting 4-6 short climbs at "
            "tempo/threshold. ~9-11 hrs."
        ),
    },
    {
        "week": 3,
        "start": "2026-07-27",
        "end": "2026-08-02",
        "phase": "build",
        "label": "Build Peak",
        "focus": "Biggest load",
        "detail": (
            "Your hardest week; expect real fatigue by the end. "
            "Threshold: 3x12 min. VO2: 5x4 min @ 115%. Longest ride: "
            "4.5-5 hrs simulating rolling terrain. Second easy endurance "
            "ride. ~10-12 hrs."
        ),
    },
    {
        "week": 4,
        "start": "2026-08-03",
        "end": "2026-08-09",
        "phase": "recovery",
        "label": "Recovery",
        "focus": "Absorption",
        "detail": (
            "Cut volume 40-50%, mostly easy. This is where the last three "
            "weeks turn into fitness. One light opener: 3x5 min tempo. "
            "Optional FTP re-test at week's end. ~5-6 hrs."
        ),
    },
    {
        "week": 5,
        "start": "2026-08-10",
        "end": "2026-08-16",
        "phase": "specificity",
        "label": "Specificity",
        "focus": "Race simulation begins",
        "detail": (
            "Everything now points at the event. Longer over-unders: "
            "4x[3 min over / 3 min under]. Hill repeats at event gradient: "
            "6-8x4-6 min @ threshold, recover on descent. 4-4.5 hr ride: "
            "go hard on every hill, practice recovering between them. "
            "~9-11 hrs."
        ),
    },
    {
        "week": 6,
        "start": "2026-08-17",
        "end": "2026-08-23",
        "phase": "specificity",
        "label": "Specificity Peak",
        "focus": "Last big ride",
        "detail": (
            "Highest-quality week, front-loaded. Big race-simulation ride "
            "early/mid-week: ~4-5 hrs, hills at goal effort, fueling and "
            "pacing exactly as race day. One shorter sharp session. Start "
            "easing by the weekend. ~8-10 hrs, tapering into Sunday."
        ),
    },
    {
        "week": 7,
        "start": "2026-08-24",
        "end": "2026-08-30",
        "phase": "taper",
        "label": "Taper + Race",
        "focus": "Race day",
        "detail": (
            "Volume down ~50-60% from peak; keep riding most days but "
            "short. Openers 2-3 days out: short spin with a few 1-2 min "
            "efforts at race intensity. Easy spin or full rest the day "
            "before. Race: Sunday, Aug 30. Priority is freshness, sleep, "
            "and logistics -- not fitness."
        ),
    },
]


def get_overview() -> dict:
    return {"goal": GOAL, "weeks": WEEKS}
