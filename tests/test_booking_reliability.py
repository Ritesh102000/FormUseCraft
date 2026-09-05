# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Focused regression tests for native-booking recovery guarantees."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from formcraft import repository
from formcraft.db import init_db, transaction


@pytest.fixture(autouse=True)
def _clean_db():
    init_db()
    with transaction() as conn:
        conn.execute("DELETE FROM forms")


def _native_form():
    from formcraft.business_inquiry import business_inquiry_form

    payload = business_inquiry_form(
        title="Booking recovery test",
        provider="google_api",
        meeting_url="",
    )
    form_id = repository.create_form(
        payload,
        sheet_profile="booking",
        booking_mode="google_api",
    )
    repository.set_sheet(form_id, "sheet-test", "https://docs.google.com/test")
    return repository.get_form(form_id=form_id)


def _identity_payload(form):
    fields = {
        question["config"].get("booking_field"): question["id"]
        for question in form["questions"]
        if question["config"].get("booking_field")
    }
    return {
        fields["attendee_name"]: "Ada Visitor",
        fields["attendee_email"]: "ada@example.com",
        fields["business_name"]: "Analytical Engines",
    }


def test_confirmed_retry_repairs_response_and_sheet_once(monkeypatch):
    from formcraft import app, sheets

    form = _native_form()
    response_id = repository.save_response(
        form["id"], _identity_payload(form), sync_ready=False
    )
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=2)
    booking = repository.reserve_booking(
        form["id"], response_id, start, start + timedelta(hours=1), "Asia/Kolkata"
    )
    booking = repository.record_booking_event(
        booking["id"],
        "https://calendar.google.com/event/test",
        "https://meet.google.com/test-meet-link",
    )

    writes: list[str] = []
    monkeypatch.setattr(sheets, "enabled", lambda: True)
    monkeypatch.setattr(
        sheets,
        "append_response",
        lambda form, response_id, answers, submitted_at=None: writes.append(response_id),
    )
    event = {
        "id": booking["calendar_event_id"],
        "htmlLink": booking["calendar_event_url"],
        "hangoutLink": booking["meet_url"],
    }
    monkeypatch.setattr(
        "formcraft.calendar_booking.get_event", lambda profile, event_id: event
    )
    monkeypatch.setattr(
        "formcraft.calendar_booking.invite_attendee",
        lambda profile, event, name, email: event,
    )

    first = app._confirmed_booking_response(form, response_id, booking)
    assert json.loads(first.body)["sheet_synced"] is True
    repaired = repository.get_response(form["id"], response_id)
    assert repaired["sync_ready"] is True
    assert repaired["synced"] is True
    assert any(value == "Booked" for value in repaired["payload"].values())

    second = app._confirmed_booking_response(
        form, response_id, repository.get_booking(response_id)
    )
    assert json.loads(second.body)["sheet_synced"] is True
    assert writes == [response_id]


def test_expired_pending_reservation_can_be_claimed_atomically():
    form = _native_form()
    first_response = repository.save_response(form["id"], {}, sync_ready=False)
    second_response = repository.save_response(form["id"], {}, sync_ready=False)
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=2)
    stale = repository.reserve_booking(
        form["id"],
        first_response,
        start,
        start + timedelta(hours=1),
        "UTC",
    )
    expired_at = datetime.now(UTC) - repository.BOOKING_RESERVATION_LEASE
    expired_at -= timedelta(minutes=1)
    with transaction() as conn:
        conn.execute(
            "UPDATE bookings SET created_at = %s WHERE id = %s",
            (expired_at, stale["id"]),
        )

    assert repository.booking_intervals(
        "booking",
        "primary",
        start - timedelta(minutes=1),
        start + timedelta(hours=2),
    ) == []
    claimed = repository.claim_expired_pending_booking(
        stale["id"],
        form["id"],
        second_response,
        start,
        start + timedelta(hours=1),
        "America/New_York",
    )
    assert claimed is not None
    assert claimed["response_id"] == second_response
    assert repository.claim_expired_pending_booking(
        stale["id"],
        form["id"],
        first_response,
        start,
        start + timedelta(hours=1),
        "UTC",
    ) is None


def test_cross_form_slot_is_unique_for_the_same_calendar():
    first = _native_form()
    from formcraft.business_inquiry import business_inquiry_form

    second_id = repository.create_form(
        business_inquiry_form(
            title="Second booking form", provider="google_api", meeting_url=""
        ),
        sheet_profile="booking",
        booking_mode="google_api",
    )
    first_response = repository.save_response(first["id"], {}, sync_ready=False)
    second_response = repository.save_response(second_id, {}, sync_ready=False)
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    assert repository.reserve_booking(
        first["id"], first_response, start, start + timedelta(hours=1), "UTC"
    )
    assert repository.reserve_booking(
        second_id, second_response, start, start + timedelta(hours=1), "UTC"
    ) is None


def test_verified_attendee_free_orphan_is_released_after_lease(monkeypatch):
    from formcraft import app, calendar_booking

    form = _native_form()
    response_id = repository.save_response(form["id"], {}, sync_ready=False)
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    booking = repository.reserve_booking(
        form["id"], response_id, start, start + timedelta(hours=1), "UTC"
    )
    booking = repository.record_booking_event(
        booking["id"], "https://calendar/event", "https://meet.google.com/test"
    )
    with transaction() as conn:
        conn.execute(
            "UPDATE bookings SET created_at = %s WHERE id = %s",
            (
                datetime.now(UTC)
                - repository.BOOKING_RESERVATION_LEASE
                - timedelta(minutes=1),
                booking["id"],
            ),
        )
    event = {
        "id": booking["calendar_event_id"],
        "extendedProperties": {
            "private": {
                "formcraft_booking_id": booking["id"],
                "formcraft_response_id": response_id,
            }
        },
    }
    reads = iter([event, None])
    monkeypatch.setattr(
        calendar_booking, "get_event", lambda profile, event_id: next(reads)
    )
    deleted = []
    monkeypatch.setattr(
        calendar_booking,
        "delete_event",
        lambda profile, event_id: deleted.append(event_id),
    )

    app._release_expired_booking_orphans(
        form, start - timedelta(minutes=1), start + timedelta(hours=2)
    )

    assert deleted == [booking["calendar_event_id"]]
    assert repository.get_booking(response_id) is None


def test_uncertain_invitation_does_not_publish_booked(monkeypatch):
    from fastapi import HTTPException

    from formcraft import app, calendar_booking, sheets

    form = _native_form()
    response_id = repository.save_response(
        form["id"], _identity_payload(form), sync_ready=False
    )
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=4)
    booking = repository.reserve_booking(
        form["id"], response_id, start, start + timedelta(hours=1), "UTC"
    )
    booking = repository.record_booking_event(
        booking["id"], "https://calendar/event", "https://meet.google.com/test"
    )
    event = {
        "id": booking["calendar_event_id"],
        "htmlLink": booking["calendar_event_url"],
        "hangoutLink": booking["meet_url"],
        "attendees": [],
    }
    monkeypatch.setattr(calendar_booking, "get_event", lambda profile, event_id: event)
    calls = 0

    def uncertain_invite(profile, current, name, email):
        nonlocal calls
        calls += 1
        if not current["attendees"]:
            current["attendees"] = [{"email": email}]
            raise TimeoutError("Google response was lost")
        return current

    monkeypatch.setattr(calendar_booking, "invite_attendee", uncertain_invite)
    monkeypatch.setattr(sheets, "enabled", lambda: True)
    writes = []
    monkeypatch.setattr(
        sheets,
        "append_response",
        lambda *args, **kwargs: writes.append(args[1]),
    )

    with pytest.raises(HTTPException) as first:
        app._confirmed_booking_response(form, response_id, booking)
    assert first.value.status_code == 503
    response = repository.get_response(form["id"], response_id)
    assert response["sync_ready"] is False
    assert "Booked" not in response["payload"].values()
    assert writes == []

    result = app._confirmed_booking_response(
        form, response_id, repository.get_booking(response_id)
    )
    assert json.loads(result.body)["invitation_sent"] is True
    assert repository.get_booking(response_id)["status"] == "confirmed"
    assert writes == [response_id]
    assert calls == 2


def test_sheet_sync_is_serialized_per_response(monkeypatch):
    from formcraft import app, sheets

    form = _native_form()
    response_id = repository.save_response(form["id"], {"value": "x"})
    response = repository.get_response(form["id"], response_id)
    monkeypatch.setattr(sheets, "enabled", lambda: True)
    writes = []

    def slow_write(*args, **kwargs):
        writes.append(args[1])
        time.sleep(0.05)

    monkeypatch.setattr(sheets, "append_response", slow_write)
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(app._sync_response_to_sheet(form, response))
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [True, True]
    assert writes == [response_id]


def test_deployed_booking_hash_requires_a_secret(monkeypatch):
    from fastapi import HTTPException

    from formcraft import app

    deployed = replace(
        app.settings,
        serverless=True,
        booking_hmac_secret="",
        secret_key="",
    )
    monkeypatch.setattr(app, "settings", deployed)
    request = type(
        "RequestStub",
        (),
        {"headers": {}, "client": type("Client", (), {"host": "127.0.0.1"})()},
    )()
    with pytest.raises(HTTPException) as exc:
        app._booking_attempt_allowed(request, "form", "response", "a@example.com")
    assert exc.value.status_code == 503
