# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Reusable definitions for the organizer’s business inquiry meeting forms."""

from __future__ import annotations

from typing import Literal

from .models import FormIn

BookingProvider = Literal["calendly", "google_calendar", "google_api"]

GOOGLE_SERVICE_DESCRIPTION = (
    "Tell us what you need help with, then choose a meeting time. "
    "Customize this example for your organization before sharing it."
)

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
        "label": "Phone number",
        "help_text": "Include your country code so we can reach you.",
        "placeholder": "e.g. +91 98765 43210",
        "required": True,
    },
    {
        "type": "short_text",
        "label": "Business name",
        "placeholder": "Your business or brand name",
        "required": True,
        "config": {"booking_field": "business_name"},
    },
    {
        "type": "long_text",
        "label": "Business description",
        "help_text": "Briefly tell us what your business does.",
        "placeholder": "What do you sell, and who do you help?",
        "required": True,
    },
    {
        "type": "long_text",
        "label": "Main business problem",
        "help_text": (
            "Keep it short—what is the biggest problem you want help solving?"
        ),
        "placeholder": "The main issue is…",
        "required": True,
    },
    {
        "type": "radio",
        "label": "Budget currency",
        "options": ["US Dollar ($)", "Indian Rupee (₹)"],
        "required": True,
    },
    {
        "type": "number",
        "label": "Approximate budget",
        "help_text": "Enter the amount in the currency selected above.",
        "placeholder": "e.g. 1000 or 50000",
        "required": True,
        "config": {"min": 0},
    },
]

CALENDLY_METADATA = [
    {
        "type": "short_text",
        "label": "Calendly booking status",
        "required": False,
        "config": {"hidden": True, "calendly_field": "status"},
    },
    {
        "type": "short_text",
        "label": "Calendly event URI",
        "required": False,
        "config": {"hidden": True, "calendly_field": "event_uri"},
    },
    {
        "type": "short_text",
        "label": "Calendly invitee URI",
        "required": False,
        "config": {"hidden": True, "calendly_field": "invitee_uri"},
    },
    {
        "type": "short_text",
        "label": "Calendly booking completed at",
        "required": False,
        "config": {"hidden": True, "calendly_field": "completed_at"},
    },
]

GOOGLE_BOOKING_METADATA = [
    {
        "type": "short_text",
        "label": "Booking status",
        "config": {"hidden": True, "booking_field": "status"},
    },
    {
        "type": "short_text",
        "label": "Meeting starts at",
        "config": {"hidden": True, "booking_field": "starts_at"},
    },
    {
        "type": "short_text",
        "label": "Meeting ends at",
        "config": {"hidden": True, "booking_field": "ends_at"},
    },
    {
        "type": "short_text",
        "label": "Visitor timezone",
        "config": {"hidden": True, "booking_field": "visitor_timezone"},
    },
    {
        "type": "short_text",
        "label": "Google Calendar event ID",
        "config": {"hidden": True, "booking_field": "event_id"},
    },
    {
        "type": "short_text",
        "label": "Google Calendar event URL",
        "config": {"hidden": True, "booking_field": "event_url"},
    },
    {
        "type": "short_text",
        "label": "Google Meet link",
        "config": {"hidden": True, "booking_field": "meet_url"},
    },
    {
        "type": "short_text",
        "label": "Booking confirmed at",
        "config": {"hidden": True, "booking_field": "confirmed_at"},
    },
]


def business_inquiry_form(
    *,
    title: str,
    provider: BookingProvider,
    meeting_url: str,
    existing: dict | None = None,
) -> FormIn:
    """Build one idempotent form without borrowing IDs from another copy."""
    old_questions = {
        question["label"]: question
        for question in (existing or {}).get("questions", [])
    }
    old_sections = {
        section["title"]: section for section in (existing or {}).get("sections", [])
    }

    definitions = [dict(item) for item in VISIBLE_QUESTIONS]
    if provider == "calendly":
        definitions.extend(dict(item) for item in CALENDLY_METADATA)
    elif provider == "google_api":
        definitions.extend(dict(item) for item in GOOGLE_BOOKING_METADATA)

    questions = []
    for definition in definitions:
        question = dict(definition)
        if old := old_questions.get(question["label"]):
            question["id"] = old["id"]
        questions.append(question)

    section = {
        "title": "Tell us about your business",
        "description": (
            "Share a few details, then book an available meeting slot below."
        ),
        "questions": questions,
    }
    if old := old_sections.get(section["title"]):
        section["id"] = old["id"]

    is_google = provider in {"google_calendar", "google_api"}
    description = (
        GOOGLE_SERVICE_DESCRIPTION
        if provider == "google_api"
        else (
            "Tell us about your business, the problem you want to solve, "
            "and your approximate budget, then book an available time."
        )
    )
    return FormIn.model_validate(
        {
            "title": title,
            "description": description,
            "display_mode": "section",
            "accent": "#4f46e5",
            "is_published": True,
            "confirm_msg": (
                "Thanks—your business details are saved. Choose a meeting time below."
                if is_google
                else "Thanks—your details are saved. You can now book a meeting."
            ),
            "meeting_url": meeting_url,
            "meeting_label": (
                "Choose a time in Google Calendar"
                if is_google
                else "Choose a time in Calendly"
            ),
            "sections": [section],
        }
    )
