# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Contract tests for the Google event and invitation sequence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from formcraft import calendar_booking


class _Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _Events:
    def __init__(self):
        self.insert_call = None
        self.patch_call = None

    def insert(self, **kwargs):
        self.insert_call = kwargs
        return _Request(
            {
                "id": kwargs["body"]["id"],
                "htmlLink": "https://calendar.google.com/event/created",
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
            }
        )

    def patch(self, **kwargs):
        self.patch_call = kwargs
        return _Request(
            {
                "id": kwargs["eventId"],
                "htmlLink": "https://calendar.google.com/event/created",
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
                "attendees": kwargs["body"]["attendees"],
            }
        )


class _CalendarService:
    def __init__(self):
        self.api = _Events()

    def events(self):
        return self.api


def test_meet_exists_before_google_invitation_is_sent(monkeypatch):
    service = _CalendarService()
    monkeypatch.setattr(calendar_booking, "_service", lambda profile: service)
    monkeypatch.setattr(calendar_booking, "get_event", lambda profile, event_id: None)
    start = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    booking = {
        "id": "booking123",
        "calendar_event_id": "fcbooking123",
        "start_at": start,
        "end_at": start + timedelta(hours=1),
    }

    event = calendar_booking.create_or_recover_event(
        profile="booking",
        booking=booking,
        response_id="response123",
        attendee_name="Ada Visitor",
        business_name="Analytical Engines",
        owner_timezone="Asia/Kolkata",
    )

    inserted = service.api.insert_call
    assert inserted["sendUpdates"] == "none"
    assert inserted["conferenceDataVersion"] == 1
    assert "attendees" not in inserted["body"]
    assert (
        inserted["body"]["conferenceData"]["createRequest"]["requestId"]
        == booking["id"]
    )
    assert calendar_booking.event_details(event)["meet_url"]

    invited = calendar_booking.invite_attendee(
        "booking", event, "Ada Visitor", "ada@example.com"
    )

    patched = service.api.patch_call
    assert patched["sendUpdates"] == "all"
    assert patched["conferenceDataVersion"] == 1
    assert patched["body"]["attendees"] == [
        {
            "email": "ada@example.com",
            "displayName": "Ada Visitor",
            "responseStatus": "needsAction",
        }
    ]
    assert invited["attendees"][0]["email"] == "ada@example.com"


def test_meet_creation_is_polled_before_returning(monkeypatch):
    pending = {
        "id": "fcbooking123",
        "conferenceData": {"createRequest": {"status": {"statusCode": "pending"}}},
    }
    ready = {
        **pending,
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
    }
    calls = []
    monkeypatch.setattr(calendar_booking.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        calendar_booking,
        "get_event",
        lambda profile, event_id: calls.append((profile, event_id)) or ready,
    )

    result = calendar_booking._wait_for_meet("booking", pending)

    assert result == ready
    assert calls == [("booking", "fcbooking123")]


def test_follow_up_event_uses_its_own_calendar_label(monkeypatch):
    service = _CalendarService()
    monkeypatch.setattr(calendar_booking, "_service", lambda profile: service)
    monkeypatch.setattr(calendar_booking, "get_event", lambda profile, event_id: None)
    start = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    booking = {
        "id": "followup123",
        "calendar_event_id": "fcfollowup123",
        "start_at": start,
        "end_at": start + timedelta(hours=1),
    }

    calendar_booking.create_or_recover_event(
        profile="booking",
        booking=booking,
        response_id="response123",
        attendee_name="Ada Visitor",
        business_name="",
        owner_timezone="Asia/Kolkata",
        event_title="Booking follow-up meeting",
        event_description="Follow-up meeting booked through Booking.",
    )

    body = service.api.insert_call["body"]
    assert body["summary"] == "Booking follow-up meeting — Ada Visitor"
    assert body["description"] == "Follow-up meeting booked through Booking."
