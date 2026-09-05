# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Focused checks for the dual-profile Google setup path."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from formcraft import config, sheets

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "google_setup.py"
_SPEC = importlib.util.spec_from_file_location("formcraft_google_setup", _SCRIPT)
assert _SPEC and _SPEC.loader
google_setup = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(google_setup)


def test_booking_sheet_service_keeps_calendar_scopes(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakeCredentials:
        valid = True
        expired = False
        refresh_token = "refresh"

        def to_json(self):
            return "{}"

    def authorized_user_info(payload, scopes):
        captured["payload"] = payload
        captured["scopes"] = scopes
        return FakeCredentials()

    def build(api, version, **kwargs):
        captured["api"] = (api, version)
        return object()

    patched = replace(
        config.settings,
        google_booking_token_json=(
            '{"refresh_token":"r","client_id":"c","client_secret":"s"}'
        ),
        google_booking_token_file=tmp_path / "booking.json",
    )
    monkeypatch.setattr(sheets, "settings", patched)
    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_info",
        staticmethod(authorized_user_info),
    )
    monkeypatch.setattr("googleapiclient.discovery.build", build)
    sheets._services.clear()
    try:
        sheets._load_service("booking")
    finally:
        sheets._services.clear()

    assert captured["api"] == ("sheets", "v4")
    assert captured["scopes"] == sheets.BOOKING_SCOPES
    assert set(sheets.SCOPES) < set(sheets.BOOKING_SCOPES)


class _Request:
    def __init__(self, result):
        self.result = result

    def execute(self, **kwargs):
        return self.result


class _Events:
    def __init__(self, *, meet_succeeds=True):
        self.meet_succeeds = meet_succeeds
        self.insert_kwargs = None
        self.delete_kwargs = None
        self.get_calls = 0

    def insert(self, **kwargs):
        self.insert_kwargs = kwargs
        return _Request(
            {
                "id": "temporary-event",
                "conferenceData": {
                    "createRequest": {"status": {"statusCode": "pending"}}
                },
            }
        )

    def get(self, **kwargs):
        self.get_calls += 1
        result = {"id": "temporary-event"}
        if self.meet_succeeds:
            result["hangoutLink"] = "https://meet.google.com/test-link"
        return _Request(result)

    def delete(self, **kwargs):
        self.delete_kwargs = kwargs
        return _Request({})


class _Calendar:
    def __init__(self, events):
        self._events = events

    def events(self):
        return self._events


def test_calendar_setup_check_creates_meet_without_attendee_and_cleans_up(
    monkeypatch,
):
    events = _Events()
    monkeypatch.setattr(google_setup.time, "sleep", lambda _: None)

    result = google_setup._verify_calendar_event_and_meet(
        _Calendar(events), "primary", attempts=2, poll_seconds=0
    )

    assert result["hangoutLink"] == "https://meet.google.com/test-link"
    assert events.insert_kwargs["sendUpdates"] == "none"
    assert "attendees" not in events.insert_kwargs["body"]
    assert events.insert_kwargs["conferenceDataVersion"] == 1
    assert events.delete_kwargs == {
        "calendarId": "primary",
        "eventId": "temporary-event",
        "sendUpdates": "none",
    }


def test_calendar_setup_check_cleans_up_when_meet_never_appears(monkeypatch):
    events = _Events(meet_succeeds=False)
    monkeypatch.setattr(google_setup.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="Meet link"):
        google_setup._verify_calendar_event_and_meet(
            _Calendar(events), "primary", attempts=2, poll_seconds=0
        )

    assert events.delete_kwargs["eventId"] == "temporary-event"
