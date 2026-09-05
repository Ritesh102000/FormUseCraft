# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Reusable definition for the organizer’s follow-up meeting form."""

from __future__ import annotations

from typing import Any

from .business_inquiry import GOOGLE_BOOKING_METADATA
from .calendar_booking import DEFAULT_BOOKING_CONFIG
from .models import FormIn

FORM_TITLE = "Follow-up Meetings"

# Keep every scheduling rule identical to the business meeting form. The two
# forms also use the same Booking calendar, so busy times and reservations are
# shared even though their response spreadsheets remain separate.
FOLLOW_UP_BOOKING_CONFIG: dict[str, Any] = {
    **DEFAULT_BOOKING_CONFIG,
    "event_title": "Follow-up meeting",
    "event_description": "Follow-up meeting booked through Formcraft.",
}

VISIBLE_QUESTIONS = [
    {
        "type": "short_text",
        "label": "Name",
        "placeholder": "Your full name",
        "required": True,
        "config": {"booking_field": "attendee_name"},
    },
    {
        "type": "email",
        "label": "Email",
        "placeholder": "you@business.com",
        "required": True,
        "config": {"booking_field": "attendee_email"},
    },
    {
        "type": "short_text",
        "label": "Business name",
        "placeholder": "Optional",
        "required": False,
        "config": {"booking_field": "business_name"},
    },
    {
        "type": "long_text",
        "label": "Follow-up notes",
        "help_text": "Optional context for this follow-up meeting.",
        "placeholder": "What would you like to continue discussing?",
        "required": False,
    },
]


def follow_up_meeting_form(existing: dict | None = None) -> FormIn:
    """Build the form while preserving IDs on safe, idempotent updates."""
    old_questions = {
        question["label"]: question
        for question in (existing or {}).get("questions", [])
    }
    definitions = [dict(item) for item in VISIBLE_QUESTIONS]
    definitions.extend(dict(item) for item in GOOGLE_BOOKING_METADATA)

    questions = []
    for definition in definitions:
        question = dict(definition)
        if old := old_questions.get(question["label"]):
            question["id"] = old["id"]
        questions.append(question)

    section: dict[str, Any] = {
        "title": "Arrange your follow-up",
        "description": "Enter your details, then choose an available meeting time.",
        "questions": questions,
    }
    old_sections = {
        saved["title"]: saved for saved in (existing or {}).get("sections", [])
    }
    if old := old_sections.get(section["title"]):
        section["id"] = old["id"]

    return FormIn.model_validate(
        {
            "title": FORM_TITLE,
            "description": (
                "Arrange a follow-up meeting using the organizer’s "
                "current availability."
            ),
            "display_mode": "section",
            "accent": "#4f46e5",
            "is_published": True,
            "confirm_msg": (
                "Your details are saved. Choose your follow-up meeting time below."
            ),
            "meeting_url": "",
            "meeting_label": "Choose a follow-up meeting time",
            "sections": [section],
        }
    )
