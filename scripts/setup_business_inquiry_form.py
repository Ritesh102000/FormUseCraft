# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Create or update the ready-to-share business inquiry form."""

from __future__ import annotations

import argparse

from formcraft import db, repository, sheets
from formcraft.app import _attach_sheet
from formcraft.business_inquiry import business_inquiry_form
from formcraft.config import settings

FORM_TITLE = "Business Inquiry & Meeting"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calendly-url",
        default="",
        help="Your complete Calendly event URL, such as https://calendly.com/name/intro",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    db.init_db()
    existing_summary = next(
        (form for form in repository.list_forms() if form["title"] == FORM_TITLE), None
    )
    existing = (
        repository.get_form(form_id=existing_summary["id"])
        if existing_summary
        else None
    )
    payload = business_inquiry_form(
        title=FORM_TITLE,
        provider="calendly",
        meeting_url=args.calendly_url or (existing or {}).get("meeting_url", ""),
        existing=existing,
    )

    if existing:
        form_id = existing["id"]
        repository.update_form(form_id, payload)
        action = "Updated"
    else:
        form_id = repository.create_form(payload)
        action = "Created"

    form = repository.get_form(form_id=form_id)
    if form is None:
        raise RuntimeError("The form was saved but could not be reloaded.")

    print(f"{action}: {form['title']}")
    print(f"Public form: {settings.base_url}/f/{form['public_ref']}")
    if form["meeting_url"]:
        print(f"Calendly: {form['meeting_url']}")
    else:
        print("Calendly: not set—paste the link in Form settings > Meeting link")

    if form.get("sheet_id"):
        form["sheet_questions"] = form["questions"]
        sheets.sync_spreadsheet(form)
        sheet = {"url": form["sheet_url"]}
    else:
        sheet = _attach_sheet(form_id, include_archived=False)
    print(f"Google Sheet: {sheet.get('url') or sheet.get('detail')}")


if __name__ == "__main__":
    main()
