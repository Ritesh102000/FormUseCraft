# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Tests that need no database."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from formcraft import calendar_booking, config, sheets
from formcraft.business_inquiry import (
    GOOGLE_SERVICE_DESCRIPTION,
    business_inquiry_form,
)
from formcraft.follow_up_meeting import (
    FOLLOW_UP_BOOKING_CONFIG,
    follow_up_meeting_form,
)
from formcraft.lead_followup import STATUS_OPTIONS, lead_followup_form
from formcraft.models import FormIn, validate_answer
from formcraft.repository import slugify
from formcraft.sheets import RESPONSE_ID_KEY, _column_letter


@pytest.mark.parametrize(
    ("question", "raw", "expected_ok"),
    [
        ({"type": "short_text", "required": True, "options": [], "config": {}}, "", False),
        ({"type": "short_text", "required": False, "options": [], "config": {}}, "", True),
        ({"type": "email", "required": True, "options": [], "config": {}}, "nope", False),
        ({"type": "email", "required": True, "options": [], "config": {}}, "a@b.co", True),
        ({"type": "radio", "required": True, "options": ["A"], "config": {}}, "B", False),
        ({"type": "radio", "required": True, "options": ["A"], "config": {}}, "A", True),
        ({"type": "scale", "required": True, "options": [], "config": {"min": 1, "max": 5}}, "9", False),
        ({"type": "scale", "required": True, "options": [], "config": {"min": 1, "max": 5}}, "3", True),
        ({"type": "number", "required": True, "options": [], "config": {}}, "abc", False),
    ],
)
def test_validate_answer(question, raw, expected_ok):
    _, error = validate_answer(question, raw)
    assert (error is None) is expected_ok


def test_checkbox_rejects_unknown_option():
    question = {"type": "checkbox", "required": False, "options": ["A", "B"], "config": {}}
    value, error = validate_answer(question, ["A", "B"])
    assert error is None and value == ["A", "B"]
    _, error = validate_answer(question, ["A", "Z"])
    assert error is not None


def test_required_checkbox_needs_a_selection():
    question = {"type": "checkbox", "required": True, "options": ["A"], "config": {}}
    _, error = validate_answer(question, [])
    assert error is not None


def test_column_letter():
    assert _column_letter(0) == "A"
    assert _column_letter(25) == "Z"
    assert _column_letter(26) == "AA"
    assert _column_letter(51) == "AZ"
    assert _column_letter(701) == "ZZ"


def test_response_id_mapping_key_cannot_collide_with_question_ids():
    assert RESPONSE_ID_KEY.startswith("__formcraft_")


def test_booking_credentials_never_fall_back_to_default(monkeypatch, tmp_path):
    patched = replace(
        config.settings,
        google_token_json='{"refresh_token":"default-only"}',
        google_booking_token_json="",
        google_booking_token_file=tmp_path / "missing-booking.json",
    )
    monkeypatch.setattr(sheets, "settings", patched)

    assert sheets.token_payload("default") == {"refresh_token": "default-only"}
    assert sheets.token_payload("booking") is None


def test_native_booking_hours_are_monday_to_saturday_9_to_midnight_ist():
    config = {
        **calendar_booking.DEFAULT_BOOKING_CONFIG,
        "minimum_notice_hours": 0,
        "booking_window_days": 7,
    }
    slots = calendar_booking.candidate_slots(
        config, now=datetime(2026, 8, 30, 0, 0, tzinfo=UTC)
    )
    owner_zone = calendar_booking.ZoneInfo("Asia/Kolkata")
    local_slots = [
        (start.astimezone(owner_zone), end.astimezone(owner_zone))
        for start, end in slots
    ]
    local_starts = [start for start, _ in local_slots]

    assert local_starts
    assert all(start.weekday() in range(6) for start in local_starts)
    assert {start.hour for start in local_starts} == set(range(9, 24))
    assert all(start.minute == 0 for start in local_starts)
    assert all(end - start == timedelta(hours=1) for start, end in slots)
    assert set(Counter(start.date() for start in local_starts).values()) == {15}

    for weekday in (0, 5):
        start, end = next(
            slot for slot in local_slots if slot[0].weekday() == weekday and slot[0].hour == 23
        )
        assert end.hour == 0
        assert end.date() == start.date() + timedelta(days=1)


def test_native_booking_rejects_24_hour_as_a_start_time():
    with pytest.raises(ValueError):
        calendar_booking.normalized_config({"last_start": "24:00"})


def test_native_booking_timezone_falls_back_from_ip_to_browser_then_utc():
    assert calendar_booking.best_viewer_timezone(
        "America/New_York", "Europe/London"
    ) == ("America/New_York", "ip")
    assert calendar_booking.best_viewer_timezone("invalid/ip", "Europe/London") == (
        "Europe/London",
        "browser",
    )
    assert calendar_booking.best_viewer_timezone("", "also-invalid") == (
        "UTC",
        "fallback",
    )


def test_serverless_availability_reuses_a_recent_google_freebusy_read(monkeypatch):
    patched = replace(config.settings, serverless=True)
    monkeypatch.setattr(calendar_booking, "settings", patched)
    calendar_booking._busy_cache.clear()
    calls = []
    start = datetime(2026, 8, 31, 4, 30, tzinfo=UTC)
    end = start + timedelta(days=30)

    def read_busy(profile, time_min, time_max):
        calls.append((profile, time_min, time_max))
        return [(start, start + timedelta(hours=1))]

    monkeypatch.setattr(calendar_booking, "busy_intervals", read_busy)

    first = calendar_booking.cached_busy_intervals("booking", start, end)
    second = calendar_booking.cached_busy_intervals("booking", start, end)

    assert first == second
    assert len(calls) == 1
    calendar_booking._busy_cache.clear()


def test_native_business_form_has_booking_metadata_and_eight_visible_fields():
    form = business_inquiry_form(
        title="Business Inquiry & Google Meeting",
        provider="google_api",
        meeting_url="",
    )
    questions = form.sections[0].questions
    visible = [question for question in questions if not question.config.get("hidden")]
    metadata = {
        question.config.get("booking_field")
        for question in questions
        if question.config.get("hidden")
    }

    assert len(visible) == 8
    assert {"status", "starts_at", "ends_at", "meet_url"} <= metadata


def test_sheet_meeting_times_are_human_readable_ist_with_weekday():
    question = {
        "id": "starts",
        "label": "Meeting starts at",
        "config": {"booking_field": "starts_at"},
    }

    assert sheets._format_answer(question, "2026-08-31T04:30:00+00:00") == (
        "Monday, 31 Aug 2026, 10:00 IST"
    )
    assert sheets._header_label(question) == "Meeting starts at (IST)"


def test_existing_sheet_response_is_updated_in_place(monkeypatch):
    class Request:
        def __init__(self, result=None):
            self.result = result or {}

        def execute(self, **kwargs):
            return self.result

    class Values:
        def __init__(self):
            self.updates = []
            self.appends = []

        def get(self, **kwargs):
            return Request({"values": [["different-id"], ["response-1"]]})

        def update(self, **kwargs):
            self.updates.append(kwargs)
            return Request()

        def append(self, **kwargs):
            self.appends.append(kwargs)
            return Request()

    class Spreadsheets:
        def __init__(self, values):
            self._values = values

        def values(self):
            return self._values

    class Service:
        def __init__(self, values):
            self._spreadsheets = Spreadsheets(values)

        def spreadsheets(self):
            return self._spreadsheets

    values = Values()
    monkeypatch.setattr(sheets, "enabled", lambda: True)
    monkeypatch.setattr(
        sheets, "_load_service", lambda profile="default": Service(values)
    )
    monkeypatch.setattr(
        sheets,
        "_ensure_columns",
        lambda service, form, questions: {
            "question-1": 1,
            RESPONSE_ID_KEY: 2,
        },
    )

    sheets.append_response(
        {
            "id": "form-1",
            "sheet_id": "sheet-1",
            "questions": [{"id": "question-1"}],
        },
        "response-1",
        {"question-1": "Updated"},
        "2026-08-08T12:00:00Z",
    )

    assert values.appends == []
    assert values.updates[0]["range"] == "Responses!A3:C3"
    assert values.updates[0]["body"]["values"] == [
        ["2026-08-08T12:00:00Z", "Updated", "response-1"]
    ]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Creator Intake", "creator-intake"),
        ("  Weird   Title!! ", "weird-title"),
        ("2026 — Q1 Feedback", "2026-q1-feedback"),
        ("!!!", "form"),
    ],
)
def test_slugify(title, expected):
    assert slugify(title) == expected


def test_form_rejects_unknown_question_type():
    with pytest.raises(ValueError, match="unknown question type"):
        FormIn.model_validate(
            {"title": "x", "sections": [{"questions": [{"type": "wat", "label": "y"}]}]}
        )


def test_form_rejects_bad_accent():
    with pytest.raises(ValueError, match="hex colour"):
        FormIn.model_validate({"title": "x", "accent": "red"})


def test_form_accepts_https_meeting_link():
    form = FormIn.model_validate(
        {
            "title": "x",
            "meeting_url": "https://calendly.com/example/intro",
            "sections": [{"questions": [{"type": "short_text", "label": "Name"}]}],
        }
    )
    assert form.meeting_url == "https://calendly.com/example/intro"


def test_form_rejects_unsafe_meeting_link():
    with pytest.raises(ValueError, match="complete https URL"):
        FormIn.model_validate(
            {
                "title": "x",
                "meeting_url": "javascript:alert(1)",
                "sections": [
                    {"questions": [{"type": "short_text", "label": "Name"}]}
                ],
            }
        )


def test_lead_followup_form_has_requested_fields_and_statuses():
    form = lead_followup_form()
    questions = {question.label: question for question in form.sections[0].questions}

    assert list(questions) == [
        "Lead name",
        "Phone number",
        "Email",
        "Follow-up date",
        "Status",
    ]
    assert questions["Lead name"].required is True
    assert questions["Phone number"].required is False
    assert questions["Email"].required is False
    assert questions["Follow-up date"].required is True
    assert questions["Status"].required is True
    assert questions["Status"].options == STATUS_OPTIONS


def test_follow_up_meeting_form_is_minimal_and_uses_business_hours():
    form = follow_up_meeting_form()
    visible = [
        question
        for question in form.sections[0].questions
        if not question.config.get("hidden")
    ]

    assert [question.label for question in visible] == [
        "Name",
        "Email",
        "Business name",
        "Follow-up notes",
    ]
    assert visible[0].config["booking_field"] == "attendee_name"
    assert visible[1].config["booking_field"] == "attendee_email"
    assert visible[2].config["booking_field"] == "business_name"
    assert visible[2].required is False
    assert visible[3].required is False
    assert {
        key: FOLLOW_UP_BOOKING_CONFIG[key]
        for key in calendar_booking.DEFAULT_BOOKING_CONFIG
    } == calendar_booking.DEFAULT_BOOKING_CONFIG


def test_google_business_form_uses_generic_customizable_description():
    form = business_inquiry_form(
        title="Business Inquiry & Google Meeting",
        provider="google_api",
        meeting_url="",
    )

    assert form.description == GOOGLE_SERVICE_DESCRIPTION
    assert "Customize this example" in form.description

    visible = [
        question
        for question in form.sections[0].questions
        if not question.config.get("hidden")
    ]
    assert [question.label for question in visible[:4]] == [
        "Name",
        "Email",
        "Phone number",
        "Business name",
    ]
    assert visible[2].required is True
    assert "country code" in visible[2].help_text


def test_options_are_trimmed_and_blanks_dropped():
    form = FormIn.model_validate(
        {
            "title": "x",
            "sections": [
                {
                    "questions": [
                        {
                            "type": "radio",
                            "label": "y",
                            "options": ["  A  ", "", "   ", "B"],
                        }
                    ]
                }
            ],
        }
    )
    assert form.sections[0].questions[0].options == ["A", "B"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"sections": []}, "add at least one section"),
        (
            {"sections": [{"questions": []}]},
            "add at least one question",
        ),
        (
            {
                "sections": [
                    {
                        "questions": [
                            {"type": "radio", "label": "Pick", "options": ["Only"]}
                        ]
                    }
                ]
            },
            "at least two options",
        ),
        (
            {
                "sections": [
                    {
                        "questions": [
                            {
                                "type": "scale",
                                "label": "Score",
                                "config": {"min": 5, "max": 1},
                            }
                        ]
                    }
                ]
            },
            "maximum must be greater",
        ),
    ],
)
def test_form_structure_errors_are_rejected(change, message):
    payload = {"title": "Validation test", **change}
    with pytest.raises(ValueError, match=message):
        FormIn.model_validate(payload)


# ------------------------------------------------------------- image slots


def test_every_slot_has_a_usable_brief():
    from formcraft.media import SLOTS

    for name, slot in SLOTS.items():
        assert slot.name == name, f"{name} key/name mismatch"
        assert "×" in slot.size, f"{name} has no pixel size"
        assert "/" in slot.ratio, f"{name} has no aspect ratio"
        assert len(slot.description) > 60, f"{name} brief is too thin to act on"


def test_unfilled_slot_resolves_to_none():
    from formcraft.media import resolve

    assert resolve("does-not-exist") is None


def test_slot_resolves_when_the_file_exists(tmp_path, monkeypatch):
    from dataclasses import replace

    from formcraft import config, media

    web = tmp_path / "web" / "static" / "img"
    web.mkdir(parents=True)
    (web / "brand-mark.webp").write_bytes(b"x")
    (web / "form-cover-creator-intake.png").write_bytes(b"x")

    monkeypatch.setattr(
        media, "settings", replace(config.settings, web_dir=tmp_path / "web")
    )

    assert media.resolve("brand-mark") == "/static/img/brand-mark.webp"
    # A per-form variant wins over the generic slot...
    assert (
        media.resolve("form-cover", "creator-intake")
        == "/static/img/form-cover-creator-intake.png"
    )
    # ...and falls back cleanly when that variant is absent.
    assert media.resolve("form-cover", "other-form") is None


def test_media_context_exposes_slots_and_resolver():
    from formcraft.media import SLOTS, context

    ctx = context()
    assert ctx["slots"] is SLOTS
    assert callable(ctx["media_url"])


def test_static_url_is_fingerprinted():
    """Cache-busting: /static is served immutable, so URLs must change on edit."""
    from formcraft.media import static_url

    url = static_url("form.js")
    assert url.startswith("/static/form.js?v=")
    assert len(url.split("?v=")[1]) > 3
    # Stable for the same file — no needless cache invalidation between renders.
    assert static_url("form.js") == url


def test_static_url_survives_a_missing_file():
    from formcraft.media import static_url

    assert static_url("does-not-exist.js") == "/static/does-not-exist.js?v=0"
