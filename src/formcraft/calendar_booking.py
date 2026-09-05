# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Native Google Calendar booking for owner-configured forms."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as wall_time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import sheets
from .config import settings

BOOKING_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar.freebusy",
]

DEFAULT_BOOKING_CONFIG: dict[str, Any] = {
    "timezone": "Asia/Kolkata",
    "weekdays": [0, 1, 2, 3, 4, 5],
    "first_start": "09:00",
    # The final one-hour meeting starts at 23:00 and ends at midnight.
    "last_start": "23:00",
    "duration_minutes": 60,
    "slot_step_minutes": 60,
    # Allow any still-future slot; the user did not request an advance-notice rule.
    "minimum_notice_hours": 0,
    "booking_window_days": 30,
}

_lock = threading.Lock()
_services: dict[str, Any] = {}
_busy_cache_lock = threading.Lock()
_busy_cache: dict[
    tuple[str, str, str, str], tuple[float, list[tuple[datetime, datetime]]]
] = {}
BUSY_CACHE_TTL_SECONDS = 30.0


class CalendarUnavailable(RuntimeError):
    """Raised when Google Calendar credentials or APIs are not usable."""


def _service(profile: str) -> Any:
    if profile != "booking":
        raise CalendarUnavailable(
            "Native Google booking is only configured for the booking profile."
        )
    with _lock:
        if not settings.is_hosted_role and profile in _services:
            return _services[profile]
        payload = sheets.token_payload(profile)
        if payload is None:
            raise CalendarUnavailable(
                "The booking Google profile is not authorized for Calendar yet."
            )
        if settings.is_hosted_role and not set(BOOKING_SCOPES) <= set(
            payload.get("scopes", [])
        ):
            raise CalendarUnavailable(
                "Connect Sheets and Calendar from Integrations first."
            )
        creds = Credentials.from_authorized_user_info(
            payload,
            payload.get("scopes") if settings.is_hosted_role else BOOKING_SCOPES,
        )
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                if settings.is_hosted_role:
                    from .google_connection import persist_refresh

                    persist_refresh(payload, json.loads(creds.to_json()))
            else:
                raise CalendarUnavailable(
                    "The Google Calendar authorization is invalid."
                )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        if not settings.is_hosted_role:
            _services[profile] = service
        return service


def valid_timezone(value: str) -> str:
    candidate = (value or "").strip()
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError):
        return ""
    return candidate


def normalized_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    config = {**DEFAULT_BOOKING_CONFIG, **(raw or {})}
    timezone = valid_timezone(str(config["timezone"]))
    if not timezone:
        raise ValueError("Booking configuration has an invalid timezone.")
    config["timezone"] = timezone
    config["weekdays"] = [int(day) for day in config["weekdays"] if 0 <= int(day) <= 6]
    for key in (
        "duration_minutes",
        "slot_step_minutes",
        "minimum_notice_hours",
        "booking_window_days",
    ):
        config[key] = int(config[key])
    if config["duration_minutes"] <= 0 or config["slot_step_minutes"] <= 0:
        raise ValueError("Booking duration and slot step must be positive.")
    if config["booking_window_days"] < 1:
        raise ValueError("Booking window must include at least one day.")
    _parse_wall_time(str(config["first_start"]))
    _parse_wall_time(str(config["last_start"]))
    return config


def _parse_wall_time(value: str) -> wall_time:
    return datetime.strptime(value, "%H:%M").time()


def candidate_slots(
    raw_config: dict[str, Any] | None, now: datetime | None = None
) -> list[tuple[datetime, datetime]]:
    config = normalized_config(raw_config)
    owner_zone = ZoneInfo(config["timezone"])
    current = (now or datetime.now(UTC)).astimezone(owner_zone)
    earliest = current + timedelta(hours=config["minimum_notice_hours"])
    first = _parse_wall_time(config["first_start"])
    last = _parse_wall_time(config["last_start"])
    duration = timedelta(minutes=config["duration_minutes"])
    step = timedelta(minutes=config["slot_step_minutes"])
    slots: list[tuple[datetime, datetime]] = []

    for offset in range(config["booking_window_days"] + 1):
        day: date = current.date() + timedelta(days=offset)
        if day.weekday() not in config["weekdays"]:
            continue
        start = datetime.combine(day, first, tzinfo=owner_zone)
        last_start = datetime.combine(day, last, tzinfo=owner_zone)
        while start <= last_start:
            if start >= earliest:
                slots.append(
                    (start.astimezone(UTC), (start + duration).astimezone(UTC))
                )
            start += step
    return slots


def _parse_google_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def busy_intervals(
    profile: str, time_min: datetime, time_max: datetime
) -> list[tuple[datetime, datetime]]:
    result = (
        _service(profile)
        .freebusy()
        .query(
            body={
                "timeMin": time_min.astimezone(UTC).isoformat(),
                "timeMax": time_max.astimezone(UTC).isoformat(),
                "timeZone": "UTC",
                "items": [{"id": settings.google_calendar_id}],
            }
        )
        .execute()
    )
    calendar = result.get("calendars", {}).get(settings.google_calendar_id, {})
    if calendar.get("errors"):
        raise CalendarUnavailable("Google could not read this calendar's availability.")
    return [
        (_parse_google_time(item["start"]), _parse_google_time(item["end"]))
        for item in calendar.get("busy", [])
    ]


def cached_busy_intervals(
    profile: str, time_min: datetime, time_max: datetime
) -> list[tuple[datetime, datetime]]:
    """Reuse a very recent FreeBusy read on warm serverless instances.

    Confirmation deliberately calls ``busy_intervals`` directly, so this
    presentation cache can never approve a stale slot. Current Formcraft
    reservations are also subtracted separately on every availability read.
    """
    if not settings.serverless:
        return busy_intervals(profile, time_min, time_max)

    key = (
        profile,
        settings.google_calendar_id,
        time_min.astimezone(UTC).isoformat(),
        time_max.astimezone(UTC).isoformat(),
    )
    now = time.monotonic()
    with _busy_cache_lock:
        cached = _busy_cache.get(key)
        if cached and now - cached[0] < BUSY_CACHE_TTL_SECONDS:
            return list(cached[1])
        expired = [
            candidate
            for candidate, (saved_at, _) in _busy_cache.items()
            if now - saved_at >= BUSY_CACHE_TTL_SECONDS
        ]
        for candidate in expired:
            _busy_cache.pop(candidate, None)

    intervals = busy_intervals(profile, time_min, time_max)
    with _busy_cache_lock:
        _busy_cache[key] = (time.monotonic(), list(intervals))
        while len(_busy_cache) > 16:
            _busy_cache.pop(next(iter(_busy_cache)))
    return intervals


def overlaps(
    start: datetime, end: datetime, intervals: list[tuple[datetime, datetime]]
) -> bool:
    return any(
        start < busy_end and end > busy_start for busy_start, busy_end in intervals
    )


def available_slots(
    form: dict[str, Any], local_busy: list[dict[str, Any]], now: datetime | None = None
) -> list[tuple[datetime, datetime]]:
    candidates = candidate_slots(form.get("booking_config"), now=now)
    if not candidates:
        return []
    calendar_busy = cached_busy_intervals(
        form["sheet_profile"], candidates[0][0], candidates[-1][1]
    )
    database_busy = [(item["start_at"], item["end_at"]) for item in local_busy]
    blocked = calendar_busy + database_busy
    return [slot for slot in candidates if not overlaps(*slot, blocked)]


def event_details(event: dict[str, Any]) -> dict[str, str]:
    meet_url = event.get("hangoutLink", "")
    if not meet_url:
        entries = event.get("conferenceData", {}).get("entryPoints", [])
        meet_url = next(
            (
                item.get("uri", "")
                for item in entries
                if item.get("entryPointType") == "video"
            ),
            "",
        )
    return {
        "event_id": event.get("id", ""),
        "event_url": event.get("htmlLink", ""),
        "meet_url": meet_url,
    }


def get_event(profile: str, event_id: str) -> dict[str, Any] | None:
    try:
        return (
            _service(profile)
            .events()
            .get(calendarId=settings.google_calendar_id, eventId=event_id)
            .execute()
        )
    except HttpError as exc:
        if exc.resp.status == 404:
            return None
        raise


def is_owned_attendee_free_event(
    event: dict[str, Any], booking: dict[str, Any]
) -> bool:
    """True only for the exact Formcraft orphan represented by this DB row."""
    private = event.get("extendedProperties", {}).get("private", {})
    return (
        event.get("id") == booking.get("calendar_event_id")
        and private.get("formcraft_booking_id") == booking.get("id")
        and private.get("formcraft_response_id") == booking.get("response_id")
        and not event.get("attendees")
    )


def delete_event(profile: str, event_id: str) -> None:
    """Delete one known event; a missing event is already the desired state."""
    try:
        (
            _service(profile)
            .events()
            .delete(calendarId=settings.google_calendar_id, eventId=event_id)
            .execute()
        )
    except HttpError as exc:
        if exc.resp.status != 404:
            raise


def create_or_recover_event(
    *,
    profile: str,
    booking: dict[str, Any],
    response_id: str,
    attendee_name: str,
    business_name: str,
    owner_timezone: str,
    event_title: str = "Business meeting",
    event_description: str = "Business consultation booked through Formcraft.",
) -> dict[str, Any]:
    event_id = booking["calendar_event_id"]
    existing = get_event(profile, event_id)
    if existing is not None:
        return _wait_for_meet(profile, existing)

    summary_name = business_name or attendee_name
    owner_zone = ZoneInfo(owner_timezone)
    body = {
        "id": event_id,
        "summary": f"{event_title} — {summary_name}",
        "description": event_description,
        "start": {
            "dateTime": booking["start_at"].astimezone(owner_zone).isoformat(),
            "timeZone": owner_timezone,
        },
        "end": {
            "dateTime": booking["end_at"].astimezone(owner_zone).isoformat(),
            "timeZone": owner_timezone,
        },
        "guestsCanModify": False,
        "guestsCanInviteOthers": False,
        "transparency": "opaque",
        "visibility": "private",
        "conferenceData": {
            "createRequest": {
                "requestId": booking["id"],
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "extendedProperties": {
            "private": {
                "formcraft_booking_id": booking["id"],
                "formcraft_response_id": response_id,
            }
        },
    }
    try:
        event = (
            _service(profile)
            .events()
            .insert(
                calendarId=settings.google_calendar_id,
                conferenceDataVersion=1,
                sendUpdates="none",
                body=body,
            )
            .execute()
        )
    except HttpError as exc:
        if exc.resp.status != 409:
            raise
        event = get_event(profile, event_id)
        if event is None:
            raise
    return _wait_for_meet(profile, event)


def invite_attendee(
    profile: str,
    event: dict[str, Any],
    attendee_name: str,
    attendee_email: str,
) -> dict[str, Any]:
    """Add the visitor only after Meet exists, so the invite contains its link."""
    if any(
        str(item.get("email", "")).casefold() == attendee_email.casefold()
        for item in event.get("attendees", [])
    ):
        return event
    return (
        _service(profile)
        .events()
        .patch(
            calendarId=settings.google_calendar_id,
            eventId=event["id"],
            sendUpdates="all",
            body={
                "attendees": [
                    {
                        "email": attendee_email,
                        "displayName": attendee_name,
                        "responseStatus": "needsAction",
                    }
                ],
                "guestsCanModify": False,
                "guestsCanInviteOthers": False,
            },
            conferenceDataVersion=1,
        )
        .execute()
    )


def _wait_for_meet(
    profile: str, event: dict[str, Any], attempts: int = 4
) -> dict[str, Any]:
    for _ in range(attempts):
        if event_details(event)["meet_url"]:
            break
        status = (
            event.get("conferenceData", {}).get("createRequest", {}).get("status", {})
        )
        if status.get("statusCode") == "failure":
            raise CalendarUnavailable("Google could not create the Meet link.")
        time.sleep(0.25)
        refreshed = get_event(profile, event.get("id", ""))
        if refreshed is not None:
            event = refreshed
    if not event_details(event)["meet_url"]:
        raise CalendarUnavailable(
            "Google is still preparing the Meet link. Retry shortly."
        )
    return event


def best_viewer_timezone(ip_timezone: str, browser_timezone: str) -> tuple[str, str]:
    ip_value = valid_timezone(ip_timezone)
    if ip_value:
        return ip_value, "ip"
    browser_value = valid_timezone(browser_timezone)
    if browser_value:
        return browser_value, "browser"
    return "UTC", "fallback"
