# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Question types and payload schemas."""

from __future__ import annotations

import math
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DisplayMode = Literal["single", "section", "one_by_one"]

QUESTION_TYPES: dict[str, dict[str, Any]] = {
    "short_text": {"label": "Short text", "has_options": False},
    "long_text": {"label": "Paragraph", "has_options": False},
    "email": {"label": "Email", "has_options": False},
    "number": {"label": "Number", "has_options": False},
    "date": {"label": "Date", "has_options": False},
    "time": {"label": "Time", "has_options": False},
    "select": {"label": "Dropdown", "has_options": True},
    "radio": {"label": "Single choice", "has_options": True},
    "checkbox": {"label": "Multiple choice", "has_options": True},
    "scale": {"label": "Linear scale", "has_options": False},
    "rating": {"label": "Star rating", "has_options": False},
}

MULTI_VALUE_TYPES = {"checkbox"}


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuestionIn(InputModel):
    id: str | None = Field(default=None, max_length=100)
    section_id: str | None = Field(default=None, max_length=100)
    type: str
    label: str = Field(min_length=1, max_length=500)
    help_text: str = Field(default="", max_length=2000)
    placeholder: str = Field(default="", max_length=500)
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question name cannot be empty")
        return value

    @field_validator("type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in QUESTION_TYPES:
            raise ValueError(f"unknown question type: {value}")
        return value

    @field_validator("options")
    @classmethod
    def clean_options(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if any(len(item) > 500 for item in cleaned):
            raise ValueError("option names must be 500 characters or fewer")
        return cleaned

    @model_validator(mode="after")
    def valid_configuration(self) -> QuestionIn:
        if self.type in {"select", "radio", "checkbox"}:
            if len(self.options) < 2:
                raise ValueError("choice questions need at least two options")
            normalized = [option.casefold() for option in self.options]
            if len(normalized) != len(set(normalized)):
                raise ValueError("option names must be unique within a question")

        if self.type in {"number", "scale", "rating"}:
            minimum = self.config.get("min")
            maximum = self.config.get("max")
            if self.type in {"scale", "rating"}:
                minimum = 1 if minimum is None else minimum
                maximum = 5 if maximum is None else maximum
                self.config = {**self.config, "min": minimum, "max": maximum}
            elif minimum is None and maximum is None:
                return self
            try:
                parsed_min = float(minimum) if minimum is not None else None
                parsed_max = float(maximum) if maximum is not None else None
            except (TypeError, ValueError) as exc:
                raise ValueError("minimum and maximum must be numbers") from exc
            bounds = [bound for bound in (parsed_min, parsed_max) if bound is not None]
            if not all(math.isfinite(bound) for bound in bounds):
                raise ValueError("minimum and maximum must be finite numbers")
            if (
                parsed_min is not None
                and parsed_max is not None
                and parsed_min >= parsed_max
            ):
                raise ValueError("maximum must be greater than minimum")
        return self


class SectionIn(InputModel):
    id: str | None = Field(default=None, max_length=100)
    title: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=2000)
    questions: list[QuestionIn] = Field(default_factory=list, max_length=200)


class FormIn(InputModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    display_mode: DisplayMode = "single"
    accent: str = "#6366f1"
    is_published: bool = False
    ai_voice_enabled: bool = False
    confirm_msg: str = Field(
        default="Thanks — your response has been recorded.", max_length=1000
    )
    meeting_url: str = Field(default="", max_length=1000)
    meeting_label: str = Field(default="Book a meeting", max_length=100)
    sections: list[SectionIn] = Field(default_factory=list, max_length=50)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("form name cannot be empty")
        return value

    @field_validator("confirm_msg")
    @classmethod
    def clean_confirmation(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("confirmation message cannot be empty")
        return value

    @field_validator("meeting_url")
    @classmethod
    def valid_meeting_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("meeting link must be a complete https URL")
        return value

    @field_validator("meeting_label")
    @classmethod
    def clean_meeting_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("meeting button text cannot be empty")
        return value

    @field_validator("accent")
    @classmethod
    def valid_hex(cls, value: str) -> str:
        value = value.strip()
        digits = value[1:] if value.startswith("#") else ""
        if len(digits) not in (3, 6) or any(
            c not in "0123456789abcdefABCDEF" for c in digits
        ):
            raise ValueError("accent must be a hex colour like #6366f1")
        return value

    @model_validator(mode="after")
    def valid_structure(self) -> FormIn:
        if not self.sections:
            raise ValueError("add at least one section")

        questions = [q for section in self.sections for q in section.questions]
        if not questions:
            raise ValueError("add at least one question")
        if len(questions) > 500:
            raise ValueError("a form can contain at most 500 questions")
        for index, section in enumerate(self.sections, start=1):
            if not section.questions:
                raise ValueError(f"section {index} needs at least one question")

        question_names = [q.label.casefold() for q in questions]
        if len(question_names) != len(set(question_names)):
            raise ValueError("question names must be unique within a form")

        section_names = [
            s.title.strip().casefold() for s in self.sections if s.title.strip()
        ]
        if len(section_names) != len(set(section_names)):
            raise ValueError("section names must be unique within a form")

        question_ids = [q.id for q in questions if q.id]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("the form contains a duplicated question reference")
        section_ids = [section.id for section in self.sections if section.id]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("the form contains a duplicated section reference")
        return self




def validate_answer(question: dict[str, Any], raw: Any) -> tuple[Any, str | None]:
    """Return (normalised value, error). Error is None when the answer is valid."""
    qtype = question["type"]
    required = bool(question["required"])
    options = question["options"]

    if qtype in MULTI_VALUE_TYPES:
        values = (
            raw if isinstance(raw, list) else ([raw] if raw not in (None, "") else [])
        )
        values = [str(v) for v in values if str(v).strip()]
        if required and not values:
            return None, "This question is required."
        unknown = [v for v in values if v not in options]
        if unknown:
            return None, f"Unexpected option: {unknown[0]}"
        return values, None

    value = "" if raw is None else str(raw).strip()
    if not value:
        return ("", None) if not required else (None, "This question is required.")

    if qtype in {"select", "radio"} and value not in options:
        return None, f"Unexpected option: {value}"

    if qtype == "email" and ("@" not in value or "." not in value.split("@")[-1]):
        return None, "Enter a valid email address."

    if qtype in {"number", "scale", "rating"}:
        try:
            number = float(value)
        except ValueError:
            return None, "Enter a number."
        config = question["config"]
        minimum = config.get("min")
        maximum = config.get("max")
        if minimum is not None and number < float(minimum):
            return None, f"Must be at least {minimum}."
        if maximum is not None and number > float(maximum):
            return None, f"Must be at most {maximum}."
        return (int(number) if number.is_integer() else number), None

    return value, None
