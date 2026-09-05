# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Database-backed limits for public Calendar invitation attempts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from formcraft import repository
from formcraft.db import init_db, transaction
from formcraft.models import FormIn


@pytest.fixture(autouse=True)
def _clean_db():
    init_db()
    with transaction() as conn:
        conn.execute("DELETE FROM forms")


def _response(form_id: str) -> str:
    return repository.save_response(form_id, {}, sync_ready=False)


def _form(title: str) -> str:
    return repository.create_form(
        FormIn.model_validate(
            {
            "title": title,
            "is_published": True,
            "sections": [
                {"questions": [{"type": "short_text", "label": "Name"}]}
            ],
            }
        )
    )


def test_same_response_retry_does_not_consume_booking_quota():
    form_id = _form("Booking quota retry")
    response_id = _response(form_id)
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    assert repository.register_booking_attempt(
        form_id, response_id, "network-a", "email-a", now=now
    )
    assert repository.register_booking_attempt(
        form_id, response_id, "network-a", "email-a", now=now
    )


def test_email_booking_quota_blocks_only_new_responses(monkeypatch):
    form_id = _form("Booking email quota")
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(repository, "BOOKING_EMAIL_DAILY_LIMIT", 2)

    assert repository.register_booking_attempt(
        form_id, _response(form_id), "network-a", "same-email", now=now
    )
    assert repository.register_booking_attempt(
        form_id, _response(form_id), "network-b", "same-email", now=now
    )
    assert not repository.register_booking_attempt(
        form_id, _response(form_id), "network-c", "same-email", now=now
    )


def test_network_booking_quota_blocks_only_new_responses(monkeypatch):
    form_id = _form("Booking network quota")
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(repository, "BOOKING_CLIENT_HOURLY_LIMIT", 2)

    assert repository.register_booking_attempt(
        form_id, _response(form_id), "same-network", "email-a", now=now
    )
    assert repository.register_booking_attempt(
        form_id, _response(form_id), "same-network", "email-b", now=now
    )
    assert not repository.register_booking_attempt(
        form_id, _response(form_id), "same-network", "email-c", now=now
    )
