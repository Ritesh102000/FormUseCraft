# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Create or update the ready-to-share lead follow-up tracker form."""

from __future__ import annotations

from formcraft import db, repository, sheets
from formcraft.app import _attach_sheet
from formcraft.config import settings
from formcraft.lead_followup import FORM_TITLE, lead_followup_form


def main() -> None:
    db.init_db()
    summary = next(
        (form for form in repository.list_forms() if form["title"] == FORM_TITLE),
        None,
    )
    existing = repository.get_form(form_id=summary["id"]) if summary else None
    payload = lead_followup_form(existing)

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

    if form.get("sheet_id"):
        form["sheet_questions"] = repository.all_questions(form_id)
        sheets.sync_spreadsheet(form)
        sheet = {"url": form["sheet_url"]}
    else:
        sheet = _attach_sheet(form_id, include_archived=False)

    print(f"{action}: {form['title']}")
    print(f"Public form: {settings.base_url}/f/{form['public_ref']}")
    print(f"Google Sheet: {sheet.get('url') or sheet.get('detail')}")


if __name__ == "__main__":
    main()
