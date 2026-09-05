# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Create or refresh the Booking-owned follow-up meeting form."""

from __future__ import annotations

from formcraft import db, repository, sheets
from formcraft.app import _attach_sheet
from formcraft.config import settings
from formcraft.follow_up_meeting import (
    FOLLOW_UP_BOOKING_CONFIG,
    FORM_TITLE,
    follow_up_meeting_form,
)


def _publication(payload, *, published: bool):
    return payload.model_copy(update={"is_published": published})


def _verified_booking_sheet(form: dict | None) -> bool:
    if form is None or form.get("sheet_profile") != "booking":
        return False
    return bool(str(form.get("sheet_id") or "").strip()) and bool(
        str(form.get("sheet_url") or "").strip()
    )


def main() -> None:
    db.init_db()
    existing_summary = next(
        (form for form in repository.list_forms() if form["title"] == FORM_TITLE),
        None,
    )
    existing = (
        repository.get_form(form_id=existing_summary["id"])
        if existing_summary
        else None
    )
    desired = follow_up_meeting_form(existing)
    draft = _publication(desired, published=False)

    if existing:
        form_id = existing["id"]
        # Keep it private while both Booking-owned integrations are verified.
        repository.update_form(form_id, draft)
        repository.set_booking_config(form_id, "google_api", FOLLOW_UP_BOOKING_CONFIG)
        action = "Updated"
    else:
        form_id = repository.create_form(
            draft,
            sheet_profile="booking",
            booking_mode="google_api",
            booking_config=FOLLOW_UP_BOOKING_CONFIG,
        )
        action = "Created"

    form = repository.get_form(form_id=form_id)
    if form is None:
        raise RuntimeError("The form was saved but could not be reloaded.")
    if form.get("sheet_profile") != "booking":
        raise RuntimeError(
            "The form remains private because it is not assigned to the "
            "Booking Google account."
        )
    if not sheets.enabled():
        raise RuntimeError(
            "The form remains private because Google synchronization is disabled."
        )

    if form.get("sheet_id"):
        form["sheet_questions"] = form["questions"]
        sheets.sync_spreadsheet(form)
        sheet = {"url": form["sheet_url"]}
    else:
        sheet = _attach_sheet(form_id, include_archived=False)

    linked = repository.get_form(form_id=form_id)
    if not _verified_booking_sheet(linked):
        detail = str(sheet.get("detail") or "Sheet attachment was not completed.")
        raise RuntimeError(f"The form remains private. {detail}")

    published = _publication(follow_up_meeting_form(linked), published=True)
    repository.update_form(form_id, published)
    repository.set_booking_config(form_id, "google_api", FOLLOW_UP_BOOKING_CONFIG)
    final = repository.get_form(form_id=form_id)
    if (
        not _verified_booking_sheet(final)
        or not final["is_published"]
        or final.get("booking_mode") != "google_api"
    ):
        raise RuntimeError("The form could not be safely published.")

    print(f"{action}: {final['title']}")
    print(f"Public form: {settings.base_url}/f/{final['public_ref']}")
    print("Booking: shared Booking Google Calendar availability")
    print(f"Google Sheet: {final['sheet_url']}")


if __name__ == "__main__":
    main()
