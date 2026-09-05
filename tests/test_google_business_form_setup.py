# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Publication safety for the Booking-owned business-form duplicate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from formcraft import repository
from formcraft.business_inquiry import business_inquiry_form
from formcraft.db import init_db, transaction
from formcraft.models import FormIn

_SCRIPT = Path(__file__).parents[1] / "scripts/setup_google_business_inquiry_form.py"
_SPEC = importlib.util.spec_from_file_location("google_business_form_setup", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
setup = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(setup)


@pytest.fixture(autouse=True)
def _clean_db():
    init_db()
    with transaction() as conn:
        conn.execute("DELETE FROM forms")


def _form_by_title(title: str) -> dict:
    summary = next(form for form in repository.list_forms() if form["title"] == title)
    form = repository.get_form(form_id=summary["id"])
    assert form is not None
    return form


def _old_default_form() -> dict:
    form_id = repository.create_form(
        FormIn.model_validate(
            {
                "title": "Existing default form",
                "is_published": True,
                "sections": [
                    {
                        "title": "Existing section",
                        "questions": [{"type": "short_text", "label": "Existing"}],
                    }
                ],
            }
        )
    )
    form = repository.get_form(form_id=form_id)
    assert form is not None
    return form


def test_new_duplicate_publishes_only_after_booking_sheet_is_linked(
    monkeypatch, capsys
):
    old = _old_default_form()
    ids_while_draft: list[str] = []
    monkeypatch.setattr(setup.sheets, "enabled", lambda: True)

    def attach(form_id: str, include_archived: bool = True):  # noqa: ARG001
        draft = repository.get_form(form_id=form_id)
        assert draft is not None
        assert draft["is_published"] is False
        assert draft["sheet_profile"] == "booking"
        ids_while_draft.extend(question["id"] for question in draft["questions"])
        repository.set_sheet(
            form_id,
            "booking-sheet-id",
            "https://docs.google.com/spreadsheets/d/booking-sheet-id/edit",
        )
        return {
            "created": True,
            "linked": True,
            "url": "https://docs.google.com/spreadsheets/d/booking-sheet-id/edit",
        }

    monkeypatch.setattr(setup, "_attach_sheet", attach)

    setup.main()

    created = _form_by_title(setup.FORM_TITLE)
    assert created["is_published"] is True
    assert created["sheet_profile"] == "booking"
    assert created["sheet_id"] == "booking-sheet-id"
    assert created["sheet_url"].endswith("/booking-sheet-id/edit")
    assert [question["id"] for question in created["questions"]] == ids_while_draft
    assert created["booking_mode"] == "google_api"
    assert "Public form:" in capsys.readouterr().out

    untouched = repository.get_form(form_id=old["id"])
    assert untouched is not None
    assert untouched["is_published"] is True
    assert untouched["sheet_profile"] == "default"


def test_attachment_failure_exits_and_leaves_duplicate_private(monkeypatch):
    old = _old_default_form()
    monkeypatch.setattr(setup.sheets, "enabled", lambda: True)
    monkeypatch.setattr(
        setup,
        "_attach_sheet",
        lambda form_id, include_archived=True: {  # noqa: ARG005
            "created": False,
            "status": "error",
            "detail": "Google refused the Sheet request.",
        },
    )

    with pytest.raises(RuntimeError, match="remains private"):
        setup.main()

    failed = _form_by_title(setup.FORM_TITLE)
    assert failed["is_published"] is False
    assert failed["sheet_profile"] == "booking"
    assert not failed["sheet_id"]
    assert not failed["sheet_url"]

    untouched = repository.get_form(form_id=old["id"])
    assert untouched is not None
    assert untouched["is_published"] is True
    assert untouched["sheet_profile"] == "default"


def test_wrong_profile_existing_duplicate_is_unpublished_before_failure(monkeypatch):
    payload = business_inquiry_form(
        title=setup.FORM_TITLE,
        provider="google_api",
        meeting_url="",
    )
    form_id = repository.create_form(payload, sheet_profile="default")
    monkeypatch.setattr(setup.sheets, "enabled", lambda: True)

    with pytest.raises(RuntimeError, match="not assigned to the booking"):
        setup.main()

    failed = repository.get_form(form_id=form_id)
    assert failed is not None
    assert failed["is_published"] is False
    assert failed["sheet_profile"] == "default"
