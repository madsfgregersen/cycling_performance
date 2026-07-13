from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    BigInteger,
    JSON,
    String,
    Text,
    func,
)

from .database import Base


class RideSummary(Base):
    """Bucket 1: one row per ride."""

    __tablename__ = "rides_summary"

    id = Column(Integer, primary_key=True)
    strava_activity_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(String, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    distance_m = Column(Float, nullable=True)
    moving_time_s = Column(Integer, nullable=True)
    elapsed_time_s = Column(Integer, nullable=True)
    elevation_gain_m = Column(Float, nullable=True)
    average_watts = Column(Float, nullable=True)
    weighted_avg_watts = Column(Float, nullable=True)
    average_heartrate = Column(Float, nullable=True)
    max_heartrate = Column(Float, nullable=True)
    ride_tss = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RideStream(Base):
    """Bucket 2: one row per second of a ride."""

    __tablename__ = "ride_streams"

    ride_id = Column(Integer, ForeignKey("rides_summary.id"), primary_key=True)
    second_offset = Column(Integer, primary_key=True)
    watts = Column(Float, nullable=True)
    heartrate = Column(Float, nullable=True)
    cadence = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    velocity_smooth = Column(Float, nullable=True)
    distance = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)


class HealthSample(Base):
    """Bucket 3: raw Apple Health samples. Dedup rules land with the
    health-data-pipeline slice, not here."""

    __tablename__ = "health_samples"

    id = Column(Integer, primary_key=True)
    metric_name = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    value = Column(Float, nullable=True)
    source = Column(String, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TelegramCheckin(Base):
    """Bucket 4: subjective daily inputs. Structured fields (mood,
    soreness, etc.) land with the Telegram slice, not here."""

    __tablename__ = "telegram_checkins"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    raw_message = Column(Text, nullable=True)
    # Set when this reply is answering a specific ride's feel/RPE ask,
    # rather than a generic day-bucketed check-in (see coach-brief story 4).
    ride_id = Column(
        Integer, ForeignKey("rides_summary.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DailyReadiness(Base):
    """Bucket 5: computed, sacred, actual history only. Sole source for
    the dashboard. Never written to speculatively."""

    __tablename__ = "daily_readiness"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True)
    ctl = Column(Float, nullable=True)
    atl = Column(Float, nullable=True)
    tsb = Column(Float, nullable=True)
    verdict = Column(String, nullable=True)
    computed_at = Column(DateTime(timezone=True), nullable=True)


class StravaToken(Base):
    """Single-row table holding the current Strava OAuth tokens.

    Auth plumbing, not one of the six data buckets.
    """

    __tablename__ = "strava_tokens"

    id = Column(Integer, primary_key=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    expires_at = Column(BigInteger, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IntegrationLog(Base):
    """Audit trail of inbound communication from external data sources
    (Strava webhook/backfill, Health Auto Export, later Telegram) --
    including no-op events, so a receipt can be confirmed even when it
    produced no new data."""

    __tablename__ = "integration_log"

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)
    event = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MessagingSetting(Base):
    """On/off toggle per proactive message type (see messaging_settings.py
    for the catalog). A missing row means enabled -- default-on."""

    __tablename__ = "messaging_settings"

    key = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlannedWorkout(Base):
    """Bucket 6: future date + target TSS; editable/provisional."""

    __tablename__ = "planned_workouts"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    target_tss = Column(Float, nullable=True)
    zone = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlanConstraint(Base):
    """The athlete-authored 'brief' (docs/coach-brief.md section 1): durable
    standing facts the coach reads before advising or proposing a change.
    To remember is to add one of these; to recall is to read them. Freeform
    text by design -- interpretation happens where it's read, not at write
    time (no invented structure the athlete didn't state)."""

    __tablename__ = "plan_constraints"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PlanAdjustmentProposal(Base):
    """A pending propose-confirm-write action (coach-brief principle 4).
    Holds what the coach proposed to change on the calendar; `changes` is
    only ever applied to planned_workouts once status becomes 'confirmed'."""

    __tablename__ = "plan_adjustment_proposals"

    id = Column(Integer, primary_key=True)
    trigger_message = Column(Text, nullable=False)
    proposal_summary = Column(Text, nullable=False)
    changes = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
