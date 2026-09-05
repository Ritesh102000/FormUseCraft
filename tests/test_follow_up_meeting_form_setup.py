# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Publication and ownership safety for the follow-up meeting form."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from formcraft import repository
from formcraft.db import init_db, transaction
from formcraft.follow_up_meeting import FORM_TITLE

_SCRIPT = Path(__file__).parents[1] / "scripts/setup_follow_up_meeting_form.py"
_SPEC = importlib.util.spec_from_file_location("follow_up_meeting_setup", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
setup = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(setup)


@pytest.fixture(autouse=True)
def _clean_db():
    init_db()
    with transaction() as conn:
        conn.execute("DELETE FROM forms")


def _form() -> dict:
    summary = next(
        form for form in repository.list_forms() if form["title"] == FORM_TITLE
    )
    saved = repository.get_form(form_id=summary["id"])
    assert saved is not None
    return saved


def test_form_publishes_only_with_separate_booking_sheet(monkeypatch):
    monkeypatch.setattr(setup.sheets, "enabled", lambda: True)

    def attach(form_id: str, include_archived: bool = True):  # noqa: ARG001
        draft = repository.get_form(form_id=form_id)
        assert draft is not None
        assert draft["is_published"] is False
        assert draft["sheet_profile"] == "booking"
        repository.set_sheet(
            form_id,
            "follow-up-sheet-id",
            "https://docs.google.com/spreadsheets/d/follow-up-sheet-id/edit",
        )
        return {
            "created": True,
            "linked": True,
            "url": "https://docs.google.com/spreadsheets/d/follow-up-sheet-id/edit",
        }

    monkeypatch.setattr(setup, "_attach_sheet", attach)
    setup.main()

    form = _form()
    assert form["is_published"] is True
    assert form["sheet_profile"] == "booking"
    assert form["sheet_id"] == "follow-up-sheet-id"
    assert form["booking_mode"] == "google_api"
    assert form["booking_config"] == setup.FOLLOW_UP_BOOKING_CONFIG


def test_form_remains_private_when_sheet_attachment_fails(monkeypatch):
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

    form = _form()
    assert form["is_published"] is False
    assert form["sheet_profile"] == "booking"
    assert not form["sheet_id"]
