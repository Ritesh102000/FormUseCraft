# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""PostgreSQL storage.

A shared database is what lets the local admin instance and the public
form instance run on different machines against the same data.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_usage (
    bucket TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS google_connection (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    provider_subject TEXT NOT NULL,
    email TEXT NOT NULL,
    encrypted_token TEXT NOT NULL,
    scopes JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS google_oauth_states (
    state_hash TEXT PRIMARY KEY,
    session_hash TEXT NOT NULL,
    encrypted_request TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_login_limits (
    bucket TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS forms (
    id            TEXT PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    display_mode  TEXT NOT NULL DEFAULT 'single',
    accent        TEXT NOT NULL DEFAULT '#6366f1',
    is_published  BOOLEAN NOT NULL DEFAULT FALSE,
    confirm_msg   TEXT NOT NULL DEFAULT 'Thanks — your response has been recorded.',
    meeting_url   TEXT NOT NULL DEFAULT '',
    meeting_label TEXT NOT NULL DEFAULT 'Book a meeting',
    booking_mode  TEXT NOT NULL DEFAULT 'external',
    booking_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    sheet_profile TEXT NOT NULL DEFAULT 'default',
    sheet_id      TEXT,
    sheet_url     TEXT,
    sheet_error   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE forms ADD COLUMN IF NOT EXISTS
    ai_voice_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS sections (
    id          TEXT PRIMARY KEY,
    form_id     TEXT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL
);

-- section_id is SET NULL, not CASCADE: rebuilding a form drops its sections,
-- and archived questions must survive that so response history stays readable.
CREATE TABLE IF NOT EXISTS questions (
    id          TEXT PRIMARY KEY,
    form_id     TEXT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    section_id  TEXT REFERENCES sections(id) ON DELETE SET NULL,
    type        TEXT NOT NULL,
    label       TEXT NOT NULL,
    help_text   TEXT NOT NULL DEFAULT '',
    placeholder TEXT NOT NULL DEFAULT '',
    required    BOOLEAN NOT NULL DEFAULT FALSE,
    options     JSONB NOT NULL DEFAULT '[]'::jsonb,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    position    INTEGER NOT NULL,
    archived    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS responses (
    id           TEXT PRIMARY KEY,
    form_id      TEXT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload      JSONB NOT NULL,
    booking_token_hash TEXT,
    sync_ready   BOOLEAN NOT NULL DEFAULT TRUE,
    booking_slot_window TIMESTAMPTZ,
    booking_slot_count INTEGER NOT NULL DEFAULT 0,
    synced       BOOLEAN NOT NULL DEFAULT FALSE,
    sync_error   TEXT
);

-- Native booking reservations. The unique slot prevents two Formcraft
-- visitors from confirming the same start time concurrently.
CREATE TABLE IF NOT EXISTS bookings (
    id                TEXT PRIMARY KEY,
    form_id           TEXT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    response_id       TEXT NOT NULL UNIQUE REFERENCES responses(id) ON DELETE CASCADE,
    calendar_profile  TEXT NOT NULL DEFAULT 'booking',
    calendar_id       TEXT NOT NULL DEFAULT 'primary',
    start_at          TIMESTAMPTZ NOT NULL,
    end_at            TIMESTAMPTZ NOT NULL,
    visitor_timezone  TEXT NOT NULL DEFAULT 'UTC',
    status            TEXT NOT NULL DEFAULT 'pending',
    calendar_event_id TEXT UNIQUE,
    calendar_event_url TEXT,
    meet_url          TEXT,
    invitation_sent   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_created_at  TIMESTAMPTZ,
    invitation_sent_at TIMESTAMPTZ,
    confirmed_at      TIMESTAMPTZ,
    UNIQUE (calendar_profile, calendar_id, start_at),
    CHECK (status IN ('pending', 'event_created', 'confirmed')),
    CHECK (end_at > start_at)
);

-- One row per response keeps retries free while limiting attackers who create
-- many responses to send Calendar invitations. Only keyed hashes are stored;
-- raw visitor IP addresses and email addresses are never written here.
CREATE TABLE IF NOT EXISTS booking_attempts (
    response_id  TEXT PRIMARY KEY REFERENCES responses(id) ON DELETE CASCADE,
    form_id      TEXT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    client_hash  TEXT NOT NULL,
    email_hash   TEXT NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stable question -> spreadsheet column mapping. Columns are never reused,
-- so deleting a question does not shift historical data.
CREATE TABLE IF NOT EXISTS sheet_columns (
    form_id     TEXT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL,
    col_index   INTEGER NOT NULL,
    PRIMARY KEY (form_id, question_id)
);

-- Added after the first release; ALTER ... IF NOT EXISTS keeps init_db()
-- safe to run against an existing database.
ALTER TABLE forms ADD COLUMN IF NOT EXISTS export_key TEXT;
ALTER TABLE forms ADD COLUMN IF NOT EXISTS meeting_url TEXT NOT NULL DEFAULT '';
ALTER TABLE forms
    ADD COLUMN IF NOT EXISTS meeting_label TEXT NOT NULL DEFAULT 'Book a meeting';
-- Existing rows keep the original Google account. New rows can explicitly
-- select another credential profile without moving or breaking old Sheets.
ALTER TABLE forms
    ADD COLUMN IF NOT EXISTS sheet_profile TEXT NOT NULL DEFAULT 'default';
ALTER TABLE forms
    ADD COLUMN IF NOT EXISTS booking_mode TEXT NOT NULL DEFAULT 'external';
ALTER TABLE forms
    ADD COLUMN IF NOT EXISTS booking_config JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE responses ADD COLUMN IF NOT EXISTS booking_token_hash TEXT;
ALTER TABLE responses
    ADD COLUMN IF NOT EXISTS sync_ready BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE responses ADD COLUMN IF NOT EXISTS booking_slot_window TIMESTAMPTZ;
ALTER TABLE responses
    ADD COLUMN IF NOT EXISTS booking_slot_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS invitation_sent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS calendar_profile TEXT NOT NULL DEFAULT 'booking';
ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS calendar_id TEXT NOT NULL DEFAULT 'primary';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS event_created_at TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS invitation_sent_at TIMESTAMPTZ;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_form_id_start_at_key;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
    CHECK (status IN ('pending', 'event_created', 'confirmed'));
CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_calendar_slot_unique
    ON bookings(calendar_profile, calendar_id, start_at);

-- The public URL segment. Unguessable, and generated once at creation so a
-- shared link keeps working even after the form is renamed.
ALTER TABLE forms ADD COLUMN IF NOT EXISTS public_ref TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_forms_public_ref ON forms(public_ref);
-- Form names are admin-facing identifiers as well as Google Sheet titles.
-- Treat case and surrounding whitespace as equivalent so "Survey" cannot be
-- recreated as " survey ", including during concurrent requests.
CREATE UNIQUE INDEX IF NOT EXISTS idx_forms_title_normalized
    ON forms ((lower(btrim(title))));

CREATE INDEX IF NOT EXISTS idx_sections_form ON sections(form_id, position);
CREATE INDEX IF NOT EXISTS idx_questions_form ON questions(form_id, position);
CREATE INDEX IF NOT EXISTS idx_responses_form
    ON responses(form_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_responses_unsynced
    ON responses(form_id) WHERE NOT synced;
CREATE INDEX IF NOT EXISTS idx_bookings_form_start
    ON bookings(form_id, start_at);
CREATE INDEX IF NOT EXISTS idx_booking_attempts_client
    ON booking_attempts(form_id, client_hash, attempted_at DESC);
CREATE INDEX IF NOT EXISTS idx_booking_attempts_email
    ON booking_attempts(form_id, email_hash, attempted_at DESC);
"""

_pool: ConnectionPool | None = None


class _PerRequestPool:
    """Stand-in for a pool on serverless hosts.

    A long-lived pool is wrong under FaaS: instances are frozen between
    invocations, so pooled sockets go stale and every cold start leaks another
    set. Opening one connection per request and closing it is correct there —
    point FORMCRAFT_DATABASE_URL at a pooled endpoint (Neon's `-pooler` host,
    Supabase's port 6543) so the churn lands on PgBouncer, not on Postgres.
    """

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(settings.database_url, row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()

    def close(self) -> None:
        return None


class DatabaseUnavailable(RuntimeError):
    """Raised when the database cannot be reached, with a readable hint."""


def pool() -> ConnectionPool | _PerRequestPool:
    global _pool
    if _pool is None:
        if not settings.database_url:
            raise DatabaseUnavailable(
                "FORMCRAFT_DATABASE_URL or DATABASE_URL is not set. "
                "Point it at your Postgres "
                "instance, e.g. postgresql://user:pass@host/dbname?sslmode=require"
            )
        if settings.serverless:
            _pool = _PerRequestPool()
            return _pool
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=settings.db_pool_size,
            kwargs={"row_factory": dict_row},
            # Neon can close an idle SSL socket while the local admin remains
            # open. Validate on checkout so the pool replaces that socket
            # before a dashboard or editor request receives it.
            check=ConnectionPool.check_connection,
            open=True,
        )
    return _pool


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """A connection inside a transaction. Commits on exit, rolls back on error."""
    with pool().connection() as conn, conn.transaction():
        yield conn


@contextmanager
def readonly() -> Iterator[psycopg.Connection]:
    with pool().connection() as conn:
        yield conn


def init_db() -> None:
    """Create tables if they do not exist. Safe to run on every start."""
    try:
        with pool().connection() as conn:
            # Serialize first-boot DDL across simultaneous serverless instances.
            conn.execute("SELECT pg_advisory_xact_lock(784246019)")
            conn.execute(SCHEMA)
            conn.commit()
        backfill_public_refs()
    except psycopg.OperationalError as exc:
        raise DatabaseUnavailable(
            f"Could not connect to Postgres: {exc}\n"
            "Check FORMCRAFT_DATABASE_URL and that the database is reachable."
        ) from exc


def backfill_public_refs() -> int:
    """Give any pre-existing form an unguessable public reference."""
    import secrets

    with pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, slug FROM forms WHERE public_ref IS NULL"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE forms SET public_ref = %s WHERE id = %s",
                (f"{row['slug']}-{secrets.token_urlsafe(9)}", row["id"]),
            )
        conn.commit()
    return len(rows)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def ping() -> dict[str, Any]:
    try:
        with readonly() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "detail": f"{type(exc).__name__}: {exc}"}
    return {"ready": True, "detail": "Connected."}
