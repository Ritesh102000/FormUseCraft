# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Form persistence: read, create, replace, delete."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .db import pool, readonly, transaction
from .models import FormIn

# A reservation normally finishes in seconds. After this lease, it stops
# hiding the slot from availability, but another response may only replace it
# after the app has also verified that its deterministic Calendar event does
# not exist. That second check lives in app.py because it needs Google access.
BOOKING_RESERVATION_LEASE = timedelta(minutes=20)
BOOKING_CLIENT_HOURLY_LIMIT = 30
BOOKING_EMAIL_DAILY_LIMIT = 5
BOOKING_SLOT_CHECK_LIMIT = 12


class DuplicateFormTitleError(ValueError):
    """A form already uses the same human-facing title."""


class InvalidFormReferenceError(ValueError):
    """An edit tried to reuse structure owned by a different form."""


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return base or "form"


def unique_slug(conn: psycopg.Connection, title: str, exclude_id: str = "") -> str:
    base = slugify(title)
    candidate = base
    suffix = 2
    while True:
        row = conn.execute(
            "SELECT id FROM forms WHERE slug = %s AND id <> %s", (candidate, exclude_id)
        ).fetchone()
        if row is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def list_forms() -> list[dict[str, Any]]:
    with readonly() as conn:
        return conn.execute(
            """
            SELECT f.*,
                   (SELECT COUNT(*) FROM questions q
                     WHERE q.form_id = f.id AND NOT q.archived
                       AND COALESCE(q.config->>'hidden', 'false') <> 'true'
                   ) AS question_count,
                   (SELECT COUNT(*) FROM responses r
                     WHERE r.form_id = f.id) AS response_count
              FROM forms f
             ORDER BY f.updated_at DESC
            """
        ).fetchall()


def get_form(
    form_id: str = "", public_ref: str = ""
) -> dict[str, Any] | None:
    """Look up by internal id (admin) or public reference (visitor link).

    There is deliberately no lookup by slug: slugs are readable and therefore
    guessable, and a visitor holding one form's link must not be able to
    discover any other form.
    """
    if not form_id and not public_ref:
        return None

    with readonly() as conn:
        if form_id:
            form = conn.execute(
                "SELECT * FROM forms WHERE id = %s", (form_id,)
            ).fetchone()
        else:
            form = conn.execute(
                "SELECT * FROM forms WHERE public_ref = %s", (public_ref,)
            ).fetchone()
        if form is None:
            return None

        sections = conn.execute(
            "SELECT * FROM sections WHERE form_id = %s ORDER BY position",
            (form["id"],),
        ).fetchall()
        questions = conn.execute(
            """SELECT * FROM questions
                WHERE form_id = %s AND NOT archived
                ORDER BY position""",
            (form["id"],),
        ).fetchall()

    by_section: dict[str | None, list[dict[str, Any]]] = {}
    for question in questions:
        by_section.setdefault(question["section_id"], []).append(question)

    for section in sections:
        section["questions"] = by_section.get(section["id"], [])

    form["sections"] = sections
    form["questions"] = questions
    form["question_count"] = sum(
        1 for question in questions if not question["config"].get("hidden")
    )
    return form


def all_questions(form_id: str) -> list[dict[str, Any]]:
    """Every question ever on this form, archived ones last.

    Exports use this rather than get_form(): a deleted question still has
    answers in past responses, and dropping those columns would lose data.
    """
    with readonly() as conn:
        return conn.execute(
            """SELECT * FROM questions WHERE form_id = %s
                ORDER BY archived, position""",
            (form_id,),
        ).fetchall()


def rotate_export_key(form_id: str) -> str:
    key = secrets.token_urlsafe(24)
    with transaction() as conn:
        conn.execute(
            "UPDATE forms SET export_key = %s WHERE id = %s", (key, form_id)
        )
    return key


def clear_export_key(form_id: str) -> None:
    with transaction() as conn:
        conn.execute("UPDATE forms SET export_key = NULL WHERE id = %s", (form_id,))


def form_by_export_key(form_id: str, key: str) -> dict[str, Any] | None:
    """Constant-time key check, so the feed URL cannot be probed by timing."""
    if not key:
        return None
    with readonly() as conn:
        row = conn.execute(
            "SELECT export_key FROM forms WHERE id = %s", (form_id,)
        ).fetchone()
    if row is None or not row["export_key"]:
        return None
    if not secrets.compare_digest(row["export_key"], key):
        return None
    return get_form(form_id=form_id)


def create_form(
    payload: FormIn,
    *,
    sheet_profile: str = "default",
    booking_mode: str = "external",
    booking_config: dict[str, Any] | None = None,
) -> str:
    if sheet_profile not in {"default", "booking"}:
        raise ValueError(f"Unknown Google Sheet profile: {sheet_profile}")
    if booking_mode not in {"external", "google_api"}:
        raise ValueError(f"Unknown booking mode: {booking_mode}")
    if any(section.id for section in payload.sections) or any(
        question.id for section in payload.sections for question in section.questions
    ):
        raise InvalidFormReferenceError("A new form cannot reuse saved structure.")
    form_id = _new_id()
    now = _now()
    try:
        with transaction() as conn:
            _ensure_unique_title(conn, payload.title)
            slug = unique_slug(conn, payload.title)
            # Readable prefix for humans, random suffix so it cannot be guessed.
            # Never regenerated — renaming a form must not break shared links.
            public_ref = f"{slug}-{secrets.token_urlsafe(9)}"
            conn.execute(
                """INSERT INTO forms
                   (id, slug, public_ref, title, description, display_mode, accent,
                    is_published, confirm_msg, meeting_url, meeting_label,
                    booking_mode, booking_config, sheet_profile, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    form_id,
                    slug,
                    public_ref,
                    payload.title,
                    payload.description,
                    payload.display_mode,
                    payload.accent,
                    payload.is_published,
                    payload.confirm_msg,
                    payload.meeting_url,
                    payload.meeting_label,
                    booking_mode,
                    Jsonb(booking_config or {}),
                    sheet_profile,
                    now,
                    now,
                ),
            )
            _write_structure(conn, form_id, payload)
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "idx_forms_title_normalized":
            raise DuplicateFormTitleError(payload.title) from exc
        raise InvalidFormReferenceError(
            "The form contains a conflicting reference."
        ) from exc
    return form_id


def update_form(form_id: str, payload: FormIn) -> None:
    """Replace the form's structure.

    Questions keep their IDs when the client sends them back, so existing
    responses and spreadsheet columns stay attached. Questions that disappear
    are archived rather than deleted.
    """
    try:
        with transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM forms WHERE id = %s", (form_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(form_id)

            _ensure_unique_title(conn, payload.title, exclude_id=form_id)
            kept = {
                q.id for section in payload.sections for q in section.questions if q.id
            }
            section_ids = {section.id for section in payload.sections if section.id}
            _ensure_owned_structure(conn, form_id, kept, section_ids)

            slug = unique_slug(conn, payload.title, exclude_id=form_id)
            conn.execute(
                """UPDATE forms
                      SET slug = %s, title = %s, description = %s,
                          display_mode = %s, accent = %s, is_published = %s,
                          confirm_msg = %s, meeting_url = %s,
                          meeting_label = %s, updated_at = %s
                    WHERE id = %s""",
                (
                    slug,
                    payload.title,
                    payload.description,
                    payload.display_mode,
                    payload.accent,
                    payload.is_published,
                    payload.confirm_msg,
                    payload.meeting_url,
                    payload.meeting_label,
                    _now(),
                    form_id,
                ),
            )

            conn.execute(
                "UPDATE questions SET archived = TRUE WHERE form_id = %s", (form_id,)
            )
            conn.execute("DELETE FROM sections WHERE form_id = %s", (form_id,))
            _write_structure(conn, form_id, payload, reuse_ids=kept)
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "idx_forms_title_normalized":
            raise DuplicateFormTitleError(payload.title) from exc
        raise InvalidFormReferenceError(
            "The form contains a conflicting reference."
        ) from exc


def _ensure_unique_title(
    conn: psycopg.Connection, title: str, exclude_id: str = ""
) -> None:
    row = conn.execute(
        """SELECT id FROM forms
            WHERE lower(btrim(title)) = lower(btrim(%s)) AND id <> %s""",
        (title, exclude_id),
    ).fetchone()
    if row is not None:
        raise DuplicateFormTitleError(title)


def _ensure_owned_structure(
    conn: psycopg.Connection,
    form_id: str,
    question_ids: set[str],
    section_ids: set[str],
) -> None:
    if question_ids:
        owned = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM questions WHERE form_id = %s AND id = ANY(%s)",
                (form_id, list(question_ids)),
            ).fetchall()
        }
        if owned != question_ids:
            raise InvalidFormReferenceError("A question does not belong to this form.")
    if section_ids:
        owned = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM sections WHERE form_id = %s AND id = ANY(%s)",
                (form_id, list(section_ids)),
            ).fetchall()
        }
        if owned != section_ids:
            raise InvalidFormReferenceError("A section does not belong to this form.")


def _write_structure(
    conn: psycopg.Connection,
    form_id: str,
    payload: FormIn,
    reuse_ids: set[str] | None = None,
) -> None:
    reuse_ids = reuse_ids or set()
    position = 0

    for index, section in enumerate(payload.sections or []):
        section_id = section.id or _new_id()
        conn.execute(
            """INSERT INTO sections (id, form_id, title, description, position)
               VALUES (%s,%s,%s,%s,%s)""",
            (section_id, form_id, section.title, section.description, index),
        )
        for question in section.questions:
            values = (
                question.type,
                question.label,
                question.help_text,
                question.placeholder,
                question.required,
                Jsonb(question.options),
                Jsonb(question.config),
                position,
                section_id,
            )
            if question.id in reuse_ids:
                conn.execute(
                    """UPDATE questions
                          SET type = %s, label = %s, help_text = %s, placeholder = %s,
                              required = %s, options = %s, config = %s, position = %s,
                              section_id = %s, archived = FALSE
                        WHERE id = %s AND form_id = %s""",
                    (*values, question.id, form_id),
                )
            else:
                conn.execute(
                    """INSERT INTO questions
                       (id, form_id, type, label, help_text, placeholder,
                        required, options, config, position, section_id, archived)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)""",
                    (_new_id(), form_id, *values),
                )
            position += 1


def delete_form(form_id: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM forms WHERE id = %s", (form_id,))


def set_sheet(form_id: str, sheet_id: str, sheet_url: str, error: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            """UPDATE forms SET sheet_id = %s, sheet_url = %s, sheet_error = %s
                WHERE id = %s""",
            (sheet_id or None, sheet_url or None, error or None, form_id),
        )
        if sheet_id:
            # A newly linked (or deliberately replaced) spreadsheet needs a
            # complete backfill. Responses may have been collected while
            # Google was disconnected, so never trust their previous sync bit.
            conn.execute(
                """UPDATE responses SET synced = FALSE, sync_error = NULL
                    WHERE form_id = %s""",
                (form_id,),
            )


def set_sheet_profile(form_id: str, profile: str) -> None:
    """Select credentials before linking a Sheet; never retarget a linked file."""
    if profile not in {"default", "booking"}:
        raise ValueError(f"Unknown Google Sheet profile: {profile}")
    with transaction() as conn:
        form = conn.execute(
            "SELECT sheet_id, sheet_profile FROM forms WHERE id = %s", (form_id,)
        ).fetchone()
        if form is None:
            raise KeyError(form_id)
        if form["sheet_id"] and form["sheet_profile"] != profile:
            raise ValueError("A linked Google Sheet cannot change account profiles.")
        conn.execute(
            "UPDATE forms SET sheet_profile = %s WHERE id = %s", (profile, form_id)
        )


def set_booking_config(form_id: str, mode: str, config: dict[str, Any]) -> None:
    if mode not in {"external", "google_api"}:
        raise ValueError(f"Unknown booking mode: {mode}")
    with transaction() as conn:
        updated = conn.execute(
            """UPDATE forms
                  SET booking_mode = %s, booking_config = %s, updated_at = %s
                WHERE id = %s
            RETURNING id""",
            (mode, Jsonb(config), _now(), form_id),
        ).fetchone()
        if updated is None:
            raise KeyError(form_id)


def set_sheet_error(form_id: str, error: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE forms SET sheet_error = %s WHERE id = %s",
            (error or None, form_id),
        )


def save_response(
    form_id: str, answers: dict[str, Any], *, sync_ready: bool = True
) -> str:
    response_id = _new_id()
    with transaction() as conn:
        conn.execute(
            """INSERT INTO responses
                   (id, form_id, submitted_at, payload, sync_ready, synced)
               VALUES (%s,%s,%s,%s,%s,FALSE)""",
            (response_id, form_id, _now(), Jsonb(answers), sync_ready),
        )
    return response_id


def issue_booking_token(form_id: str, response_id: str) -> str:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with transaction() as conn:
        updated = conn.execute(
            """UPDATE responses SET booking_token_hash = %s
                WHERE id = %s AND form_id = %s
            RETURNING id""",
            (digest, response_id, form_id),
        ).fetchone()
    if updated is None:
        raise KeyError(response_id)
    return token


def booking_token_valid(form_id: str, response_id: str, token: str) -> bool:
    if not token:
        return False
    with readonly() as conn:
        row = conn.execute(
            """SELECT booking_token_hash FROM responses
                WHERE id = %s AND form_id = %s""",
            (response_id, form_id),
        ).fetchone()
    if row is None or not row["booking_token_hash"]:
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    return secrets.compare_digest(row["booking_token_hash"], digest)


def consume_booking_slot_check(
    form_id: str, response_id: str, *, now: datetime | None = None
) -> bool:
    """Allow a small burst of availability refreshes per saved response."""
    checked_at = now or _now()
    with transaction() as conn:
        row = conn.execute(
            """UPDATE responses
                  SET booking_slot_count = CASE
                          WHEN booking_slot_window IS NULL
                            OR booking_slot_window <= %s - INTERVAL '10 minutes'
                          THEN 1 ELSE booking_slot_count + 1 END,
                      booking_slot_window = CASE
                          WHEN booking_slot_window IS NULL
                            OR booking_slot_window <= %s - INTERVAL '10 minutes'
                          THEN %s ELSE booking_slot_window END
                WHERE id = %s AND form_id = %s
            RETURNING booking_slot_count""",
            (checked_at, checked_at, checked_at, response_id, form_id),
        ).fetchone()
    return bool(row and int(row["booking_slot_count"]) <= BOOKING_SLOT_CHECK_LIMIT)


def get_response(form_id: str, response_id: str) -> dict[str, Any] | None:
    with readonly() as conn:
        return conn.execute(
            "SELECT * FROM responses WHERE id = %s AND form_id = %s",
            (response_id, form_id),
        ).fetchone()


def get_booking(response_id: str) -> dict[str, Any] | None:
    with readonly() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE response_id = %s", (response_id,)
        ).fetchone()


def get_booking_for_slot(
    calendar_profile: str, calendar_id: str, start_at: datetime
) -> dict[str, Any] | None:
    with readonly() as conn:
        return conn.execute(
            """SELECT * FROM bookings
                WHERE calendar_profile = %s AND calendar_id = %s AND start_at = %s""",
            (calendar_profile, calendar_id, start_at),
        ).fetchone()


def pending_booking_expired(
    booking: dict[str, Any] | None, *, now: datetime | None = None
) -> bool:
    if booking is None or booking.get("status") not in {"pending", "event_created"}:
        return False
    if booking.get("invitation_sent"):
        return False
    lease_cutoff = (now or _now()) - BOOKING_RESERVATION_LEASE
    return booking["created_at"] <= lease_cutoff


@contextmanager
def booking_claim(booking_id: str) -> Iterator[bool]:
    """Try to own one booking workflow across app instances.

    The session advisory lock is released explicitly and also disappears if
    the process or database connection dies. Keeping this separate from the
    booking row means an interrupted request never leaves a permanent claim.
    """
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired",
            (booking_id,),
        ).fetchone()
        conn.commit()
        acquired = bool(row and row["acquired"])
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    (booking_id,),
                )
                conn.commit()


@contextmanager
def response_sync_claim(response_id: str) -> Iterator[None]:
    """Serialize one response's external Sheet upsert across app instances."""
    lock_name = f"response-sheet-sync:{response_id}"
    with pool().connection() as conn:
        conn.execute(
            "SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_name,)
        )
        conn.commit()
        try:
            yield
        finally:
            conn.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (lock_name,)
            )
            conn.commit()


def register_booking_attempt(
    form_id: str,
    response_id: str,
    client_hash: str,
    email_hash: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Record one response's attempt when its email and network are in bounds.

    Repeated confirmation for the same response is always allowed, so a
    temporary Calendar or Sheet failure cannot consume the visitor's quota.
    Transaction-scoped advisory locks serialize counters across app instances.
    """
    attempted_at = now or _now()
    with transaction() as conn:
        existing = conn.execute(
            "SELECT 1 FROM booking_attempts WHERE response_id = %s",
            (response_id,),
        ).fetchone()
        if existing is not None:
            return True

        # Stable order prevents two requests with crossed email/network pairs
        # from deadlocking while both counters are being checked.
        for key in sorted({f"client:{client_hash}", f"email:{email_hash}"}):
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"booking-rate:{form_id}:{key}",),
            )

        # A concurrent retry for this response may have inserted while this
        # transaction waited for the counter locks.
        existing = conn.execute(
            "SELECT 1 FROM booking_attempts WHERE response_id = %s",
            (response_id,),
        ).fetchone()
        if existing is not None:
            return True

        counts = conn.execute(
            """SELECT
                   COUNT(*) FILTER (
                       WHERE client_hash = %s
                         AND attempted_at > %s - INTERVAL '1 hour'
                   ) AS client_count,
                   COUNT(*) FILTER (
                       WHERE email_hash = %s
                         AND attempted_at > %s - INTERVAL '24 hours'
                   ) AS email_count
                 FROM booking_attempts
                WHERE form_id = %s""",
            (client_hash, attempted_at, email_hash, attempted_at, form_id),
        ).fetchone()
        if (
            int(counts["client_count"]) >= BOOKING_CLIENT_HOURLY_LIMIT
            or int(counts["email_count"]) >= BOOKING_EMAIL_DAILY_LIMIT
        ):
            return False

        conn.execute(
            """INSERT INTO booking_attempts
                   (response_id, form_id, client_hash, email_hash, attempted_at)
               VALUES (%s,%s,%s,%s,%s)""",
            (response_id, form_id, client_hash, email_hash, attempted_at),
        )
        return True


def reserve_booking(
    form_id: str,
    response_id: str,
    start_at: datetime,
    end_at: datetime,
    visitor_timezone: str,
    calendar_profile: str = "booking",
    calendar_id: str = "primary",
) -> dict[str, Any] | None:
    booking_id = _new_id()
    try:
        with transaction() as conn:
            return conn.execute(
                """INSERT INTO bookings
                       (id, form_id, response_id, calendar_profile, calendar_id,
                        start_at, end_at, visitor_timezone, calendar_event_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *""",
                (
                    booking_id,
                    form_id,
                    response_id,
                    calendar_profile,
                    calendar_id,
                    start_at,
                    end_at,
                    visitor_timezone,
                    f"fc{booking_id}",
                ),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        return None


def claim_expired_pending_booking(
    stale_booking_id: str,
    form_id: str,
    response_id: str,
    start_at: datetime,
    end_at: datetime,
    visitor_timezone: str,
    calendar_profile: str = "booking",
    calendar_id: str = "primary",
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Atomically replace exactly one expired, still-pending reservation.

    The caller must hold ``booking_claim(stale_booking_id)`` and verify that
    Google Calendar has no event for the stale reservation before calling.
    If another request changed either row first, the transaction leaves the
    existing reservation untouched and returns ``None``.
    """
    claimed_at = now or _now()
    lease_cutoff = claimed_at - BOOKING_RESERVATION_LEASE
    booking_id = _new_id()
    try:
        with transaction() as conn:
            removed = conn.execute(
                """DELETE FROM bookings
                    WHERE id = %s AND calendar_profile = %s AND calendar_id = %s
                      AND start_at = %s AND status IN ('pending', 'event_created')
                      AND NOT invitation_sent AND created_at <= %s
                RETURNING id""",
                (
                    stale_booking_id,
                    calendar_profile,
                    calendar_id,
                    start_at,
                    lease_cutoff,
                ),
            ).fetchone()
            if removed is None:
                return None
            return conn.execute(
                """INSERT INTO bookings
                       (id, form_id, response_id, calendar_profile, calendar_id,
                        start_at, end_at, visitor_timezone, calendar_event_id,
                        created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *""",
                (
                    booking_id,
                    form_id,
                    response_id,
                    calendar_profile,
                    calendar_id,
                    start_at,
                    end_at,
                    visitor_timezone,
                    f"fc{booking_id}",
                    claimed_at,
                ),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        # The delete and insert share one transaction, so a competing claim or
        # another reservation owned by this response rolls the deletion back.
        return None


def record_booking_event(
    booking_id: str, calendar_event_url: str, meet_url: str
) -> dict[str, Any] | None:
    with transaction() as conn:
        return conn.execute(
            """UPDATE bookings
                  SET status = 'event_created', calendar_event_url = %s,
                      meet_url = %s, event_created_at = COALESCE(event_created_at, %s)
                WHERE id = %s AND status IN ('pending', 'event_created')
            RETURNING *""",
            (calendar_event_url or None, meet_url or None, _now(), booking_id),
        ).fetchone()


def mark_booking_invited(booking_id: str) -> dict[str, Any] | None:
    with transaction() as conn:
        invited_at = _now()
        return conn.execute(
            """UPDATE bookings
                  SET status = 'confirmed', invitation_sent = TRUE,
                      invitation_sent_at = COALESCE(invitation_sent_at, %s),
                      confirmed_at = COALESCE(confirmed_at, %s)
                WHERE id = %s AND status IN ('event_created', 'confirmed')
                  AND calendar_event_url IS NOT NULL AND meet_url IS NOT NULL
            RETURNING *""",
            (invited_at, invited_at, booking_id),
        ).fetchone()


def delete_pending_booking(booking_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            "DELETE FROM bookings WHERE id = %s AND status = 'pending'", (booking_id,)
        )


def delete_expired_unconfirmed_booking(
    booking_id: str, *, now: datetime | None = None
) -> bool:
    lease_cutoff = (now or _now()) - BOOKING_RESERVATION_LEASE
    with transaction() as conn:
        row = conn.execute(
            """DELETE FROM bookings
                WHERE id = %s AND status IN ('pending', 'event_created')
                  AND NOT invitation_sent AND created_at <= %s
            RETURNING id""",
            (booking_id, lease_cutoff),
        ).fetchone()
    return row is not None


def expired_unconfirmed_bookings(
    calendar_profile: str,
    calendar_id: str,
    starts_after: datetime,
    starts_before: datetime,
) -> list[dict[str, Any]]:
    lease_cutoff = _now() - BOOKING_RESERVATION_LEASE
    with readonly() as conn:
        return conn.execute(
            """SELECT * FROM bookings
                WHERE calendar_profile = %s AND calendar_id = %s
                  AND status IN ('pending', 'event_created')
                  AND NOT invitation_sent AND created_at <= %s
                  AND start_at < %s AND end_at > %s
                ORDER BY created_at""",
            (
                calendar_profile,
                calendar_id,
                lease_cutoff,
                starts_before,
                starts_after,
            ),
        ).fetchall()


def booking_intervals(
    calendar_profile: str,
    calendar_id: str,
    starts_after: datetime,
    starts_before: datetime,
) -> list[dict[str, Any]]:
    lease_cutoff = _now() - BOOKING_RESERVATION_LEASE
    with readonly() as conn:
        return conn.execute(
            """SELECT start_at, end_at FROM bookings
                WHERE calendar_profile = %s AND calendar_id = %s
                  AND (status = 'confirmed'
                       OR (status IN ('pending', 'event_created') AND created_at > %s))
                  AND start_at < %s AND end_at > %s
                ORDER BY start_at""",
            (
                calendar_profile,
                calendar_id,
                lease_cutoff,
                starts_before,
                starts_after,
            ),
        ).fetchall()


def update_response(
    form_id: str,
    response_id: str,
    answers: dict[str, Any],
    *,
    sync_ready: bool | None = None,
) -> dict[str, Any] | None:
    """Merge later metadata into one response and queue its Sheet row again."""
    with transaction() as conn:
        if sync_ready is None:
            return conn.execute(
                """UPDATE responses
                      SET payload = payload || %s,
                          synced = FALSE,
                          sync_error = NULL
                    WHERE id = %s AND form_id = %s
                RETURNING *""",
                (Jsonb(answers), response_id, form_id),
            ).fetchone()
        return conn.execute(
            """UPDATE responses
                  SET payload = payload || %s,
                      sync_ready = %s,
                      synced = FALSE,
                      sync_error = NULL
                WHERE id = %s AND form_id = %s
            RETURNING *""",
            (Jsonb(answers), sync_ready, response_id, form_id),
        ).fetchone()


def mark_synced(response_id: str, error: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE responses SET synced = %s, sync_error = %s WHERE id = %s",
            (not error, error or None, response_id),
        )


def list_responses(form_id: str, limit: int = 500) -> list[dict[str, Any]]:
    with readonly() as conn:
        return conn.execute(
            """SELECT * FROM responses WHERE form_id = %s
                ORDER BY submitted_at DESC LIMIT %s""",
            (form_id, limit),
        ).fetchall()


def pending_sync(limit: int = 50, form_id: str = "") -> list[dict[str, Any]]:
    with readonly() as conn:
        return conn.execute(
            """SELECT r.* FROM responses r
                JOIN forms f ON f.id = r.form_id
               WHERE NOT r.synced AND r.sync_ready AND f.sheet_id IS NOT NULL
                 AND (%s = '' OR r.form_id = %s)
               ORDER BY r.submitted_at LIMIT %s""",
            (form_id, form_id, limit),
        ).fetchall()
