# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Definition for the reusable lead follow-up tracker form."""

from __future__ import annotations

from .models import FormIn

FORM_TITLE = "Lead Follow-up Tracker"
STATUS_OPTIONS = [
    "New",
    "Contacted",
    "Interested",
    "Needs follow-up",
    "Lost",
    "Won",
]


def lead_followup_form(existing: dict | None = None) -> FormIn:
    """Build the form while preserving stable IDs during later updates."""
    old_questions = {
        question["label"]: question
        for question in (existing or {}).get("questions", [])
    }
    definitions = [
        {
            "type": "short_text",
            "label": "Lead name",
            "placeholder": "Full name",
            "required": True,
        },
        {
            "type": "short_text",
            "label": "Phone number",
            "placeholder": "Optional",
            "required": False,
        },
        {
            "type": "email",
            "label": "Email",
            "placeholder": "Optional",
            "required": False,
        },
        {
            "type": "date",
            "label": "Follow-up date",
            "required": True,
        },
        {
            "type": "select",
            "label": "Status",
            "options": STATUS_OPTIONS,
            "required": True,
        },
    ]

    questions = []
    for definition in definitions:
        question = dict(definition)
        if old := old_questions.get(question["label"]):
            question["id"] = old["id"]
        questions.append(question)

    section: dict = {
        "title": "Lead details",
        "description": "Add the lead and choose when you need to follow up.",
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
                "Keep each lead's contact details, next follow-up date, and "
                "current sales status in one place."
            ),
            "display_mode": "section",
            "accent": "#D9431F",
            "is_published": True,
            "confirm_msg": "Lead saved successfully.",
            "sections": [section],
        }
    )
