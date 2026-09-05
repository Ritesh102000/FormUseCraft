# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Create the separate business form backed by your Google services."""

from __future__ import annotations

from formcraft import db, repository, sheets
from formcraft.app import _attach_sheet
from formcraft.business_inquiry import business_inquiry_form
from formcraft.calendar_booking import DEFAULT_BOOKING_CONFIG
from formcraft.config import settings

FORM_TITLE = "Business Inquiry & Google Meeting"


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
    desired = business_inquiry_form(
        title=FORM_TITLE,
        provider="google_api",
        meeting_url="",
        existing=existing,
    )
    draft = _publication(desired, published=False)
    if existing:
        form_id = existing["id"]
        # Safety comes first on every re-run: even a previously published copy
        # is private while its Google linkage is being checked.
        repository.update_form(form_id, draft)
        repository.set_booking_config(form_id, "google_api", DEFAULT_BOOKING_CONFIG)
        action = "Updated"
    else:
        form_id = repository.create_form(
            draft,
            sheet_profile="booking",
            booking_mode="google_api",
            booking_config=DEFAULT_BOOKING_CONFIG,
        )
        action = "Created"

    form = repository.get_form(form_id=form_id)
    if form is None:
        raise RuntimeError("The form was saved but could not be reloaded.")
    if form.get("sheet_profile") != "booking":
        raise RuntimeError(
            "The duplicate remains private because it is not assigned to the "
            "booking Google profile."
        )
    if not sheets.enabled():
        raise RuntimeError(
            "The duplicate remains private because Google synchronization is disabled."
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
        raise RuntimeError(f"The duplicate remains private. {detail}")

    # Rebuild from the saved draft so a newly created form keeps its generated
    # section and question IDs when publication is flipped on.
    published = _publication(
        business_inquiry_form(
            title=FORM_TITLE,
            provider="google_api",
            meeting_url="",
            existing=linked,
        ),
        published=True,
    )
    repository.update_form(form_id, published)
    final = repository.get_form(form_id=form_id)
    if not _verified_booking_sheet(final) or not final["is_published"]:
        raise RuntimeError("The duplicate could not be safely published.")

    print(f"{action}: {final['title']}")
    print(f"Public form: {settings.base_url}/f/{final['public_ref']}")
    print("Booking: Formcraft slots backed by the configured Google account")
    print(f"Google Sheet: {final['sheet_url']}")


if __name__ == "__main__":
    main()
