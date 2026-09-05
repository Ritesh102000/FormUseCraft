# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""End-to-end tests against a real Postgres and the real HTTP app."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from formcraft import repository
from formcraft.auth import hash_password
from formcraft.db import init_db, transaction
from formcraft.models import FormIn

PASSWORD = "smoke-password-123"


@pytest.fixture(autouse=True)
def _clean_db():
    init_db()
    with transaction() as conn:
        conn.execute("DELETE FROM forms")


def patch_settings(monkeypatch, **overrides):
    """Settings is a frozen dataclass, and each module holds its own reference."""
    from formcraft import app, auth, config, db, sheets

    patched = replace(config.settings, **overrides)
    for module in (config, auth, app, db, sheets):
        monkeypatch.setattr(module, "settings", patched)
    return patched


@pytest.fixture
def admin_client(monkeypatch):
    from formcraft import app as app_module

    patch_settings(monkeypatch, admin_password_hash=hash_password(PASSWORD))
    client = TestClient(app_module.create_app())
    res = client.post(
        "/login",
        data={"username": "admin", "password": PASSWORD},
        follow_redirects=False,
    )
    assert res.status_code == 302, res.text
    return client


def sample_form(**overrides) -> dict:
    payload = {
        "title": "Creator intake",
        "display_mode": "section",
        "is_published": True,
        "sections": [
            {
                "title": "About you",
                "questions": [
                    {"type": "short_text", "label": "Handle", "required": True},
                    {"type": "email", "label": "Email", "required": True},
                    {
                        "type": "checkbox",
                        "label": "Platforms",
                        "options": ["IG", "TikTok", "YouTube"],
                    },
                    {
                        "type": "scale",
                        "label": "Confidence",
                        "config": {"min": 1, "max": 5},
                    },
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload






# ------------------------------------------------------------------ storage


def test_create_and_read_form():
    form_id = repository.create_form(FormIn.model_validate(sample_form()))
    form = repository.get_form(form_id=form_id)

    assert form is not None
    assert form["slug"] == "creator-intake"
    assert len(form["questions"]) == 4
    assert form["sections"][0]["questions"][2]["options"] == ["IG", "TikTok", "YouTube"]
    assert form["questions"][3]["config"] == {"min": 1, "max": 5}


def test_duplicate_form_title_is_rejected_case_insensitively():
    repository.create_form(FormIn.model_validate(sample_form()))
    duplicate = sample_form(title="  CREATOR INTAKE  ")

    with pytest.raises(repository.DuplicateFormTitleError):
        repository.create_form(FormIn.model_validate(duplicate))


def test_update_keeps_question_ids_and_archives_removals():
    form_id = repository.create_form(FormIn.model_validate(sample_form()))
    keep = repository.get_form(form_id=form_id)["questions"][0]["id"]

    repository.update_form(
        form_id,
        FormIn.model_validate(
            {
                "title": "Creator intake",
                "sections": [
                    {
                        "title": "About you",
                        "questions": [
                            {"id": keep, "type": "short_text", "label": "Handle"}
                        ],
                    }
                ],
            }
        ),
    )

    updated = repository.get_form(form_id=form_id)
    assert [q["id"] for q in updated["questions"]] == [keep]


def test_responses_survive_a_form_edit():
    form_id = repository.create_form(FormIn.model_validate(sample_form()))
    form = repository.get_form(form_id=form_id)
    qid = form["questions"][0]["id"]
    repository.save_response(form_id, {qid: "@someone"})

    payload = sample_form()
    payload["sections"][0]["questions"] = [
        {"id": qid, "type": "short_text", "label": "Handle"}
    ]
    repository.update_form(form_id, FormIn.model_validate(payload))

    rows = repository.list_responses(form_id)
    assert len(rows) == 1
    assert rows[0]["payload"][qid] == "@someone"


def test_linking_a_sheet_queues_every_existing_response_for_backfill():
    form_id = repository.create_form(FormIn.model_validate(sample_form()))
    response_id = repository.save_response(form_id, {})
    repository.mark_synced(response_id)

    repository.set_sheet(form_id, "sheet-123", "https://docs.google.com/sheet-123")

    rows = repository.list_responses(form_id)
    assert rows[0]["synced"] is False
    assert repository.pending_sync(form_id=form_id)[0]["id"] == response_id


def test_delete_cascades():
    form_id = repository.create_form(FormIn.model_validate(sample_form()))
    repository.save_response(form_id, {})
    repository.delete_form(form_id)
    assert repository.get_form(form_id=form_id) is None
    assert repository.list_responses(form_id) == []


# --------------------------------------------------------------------- HTTP


def test_admin_requires_login(admin_client):
    anon = TestClient(admin_client.app)
    assert anon.get("/", follow_redirects=False).headers["location"] == "/login"
    assert anon.post("/api/forms", json={"title": "x"}).status_code == 401


def test_duplicate_form_title_returns_clear_conflict(admin_client):
    first = admin_client.post("/api/forms", json=sample_form())
    assert first.status_code == 201

    duplicate = admin_client.post(
        "/api/forms", json=sample_form(title=" creator INTAKE ")
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_form_name"
    assert "already exists" in duplicate.json()["detail"]["message"]








def test_invalid_form_payload_returns_actionable_errors(admin_client):
    payload = sample_form()
    payload["sections"][0]["questions"][2]["options"] = ["IG", "ig"]

    response = admin_client.post("/api/forms", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error"
    messages = " ".join(item["message"] for item in detail["errors"])
    assert "option names must be unique" in messages

    payload = sample_form()
    payload["sections"][0]["questions"][1]["label"] = "Handle"
    response = admin_client.post("/api/forms", json=payload)
    messages = " ".join(
        item["message"] for item in response.json()["detail"]["errors"]
    )
    assert response.status_code == 422
    assert "question names must be unique" in messages


def test_malformed_json_is_not_an_internal_server_error(admin_client):
    response = admin_client.post(
        "/api/forms",
        content=b'{"title":',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_json"


def test_wrong_password_rejected(admin_client):
    anon = TestClient(admin_client.app)
    res = anon.post(
        "/login", data={"username": "admin", "password": "nope"}, follow_redirects=False
    )
    assert res.status_code == 200 and "Incorrect" in res.text


def test_full_submission_flow(admin_client):
    res = admin_client.post("/api/forms", json=sample_form())
    assert res.status_code == 201, res.text
    form_id = res.json()["id"]

    form = repository.get_form(form_id=form_id)
    qids = [q["id"] for q in form["questions"]]

    page = admin_client.get(f"/f/{form['public_ref']}")
    assert page.status_code == 200 and "Creator intake" in page.text

    # missing required field
    bad = admin_client.post(f"/f/{form['public_ref']}", json={qids[1]: "a@b.co"})
    assert bad.status_code == 422 and qids[0] in bad.json()["errors"]

    # bad email
    bad = admin_client.post(
        f"/f/{form['public_ref']}", json={qids[0]: "@me", qids[1]: "nope"}
    )
    assert bad.status_code == 422 and qids[1] in bad.json()["errors"]

    # option outside the allowlist
    bad = admin_client.post(
        f"/f/{form['public_ref']}",
        json={qids[0]: "@me", qids[1]: "a@b.co", qids[2]: ["Twitter"]},
    )
    assert bad.status_code == 422 and qids[2] in bad.json()["errors"]

    ok = admin_client.post(
        f"/f/{form['public_ref']}",
        json={
            qids[0]: "@samplecreator",
            qids[1]: "r@example.com",
            qids[2]: ["IG", "YouTube"],
            qids[3]: "4",
        },
    )
    assert ok.status_code == 200 and ok.json()["ok"]

    rows = repository.list_responses(form_id)
    assert len(rows) == 1
    assert rows[0]["payload"][qids[2]] == ["IG", "YouTube"]
    assert rows[0]["payload"][qids[3]] == 4
    # No spreadsheet is linked yet. "Synced" must not claim that there was
    # nothing to do: linking one later should backfill this response.
    assert rows[0]["synced"] is False


def test_direct_sheet_sync_creates_appends_and_updates_headers(
    monkeypatch, admin_client
):
    from formcraft import sheets

    patch_settings(monkeypatch, google_enabled=True)
    calls: list[tuple] = []

    monkeypatch.setattr(
        sheets,
        "create_spreadsheet",
        lambda form: ("sheet-123", "https://docs.google.com/sheet-123"),
    )
    monkeypatch.setattr(
        sheets,
        "append_response",
        lambda form, response_id, answers, submitted_at=None: calls.append(
            ("append", form["id"], response_id, answers)
        ),
    )
    monkeypatch.setattr(
        sheets,
        "sync_spreadsheet",
        lambda form: calls.append(("update", form["id"], form["title"])),
    )

    created = admin_client.post("/api/forms", json=sample_form())
    assert created.status_code == 201
    form_id = created.json()["id"]
    form = repository.get_form(form_id=form_id)
    assert form["sheet_id"] == "sheet-123"

    qids = [q["id"] for q in form["questions"]]
    submitted = admin_client.post(
        f"/f/{form['public_ref']}",
        json={qids[0]: "@direct", qids[1]: "direct@example.com"},
    )
    assert submitted.status_code == 200
    response = repository.list_responses(form_id)[0]
    assert response["synced"] is True
    assert ("append", form_id, response["id"], response["payload"]) in calls

    renamed = sample_form(title="Renamed intake")
    renamed["sections"][0]["questions"] = [
        {**question, "id": qid}
        for question, qid in zip(
            renamed["sections"][0]["questions"], qids, strict=True
        )
    ]
    updated = admin_client.put(f"/api/forms/{form_id}", json=renamed)
    assert updated.status_code == 200
    assert updated.json()["sheet"]["updated"] is True
    assert ("update", form_id, "Renamed intake") in calls


def test_sheet_creation_failure_keeps_form_and_returns_safe_guidance(
    monkeypatch, admin_client
):
    from formcraft import sheets

    patch_settings(monkeypatch, google_enabled=True)

    def fail_create(form):
        raise RuntimeError("429 quota exceeded sensitive-marker=never-show")

    monkeypatch.setattr(sheets, "create_spreadsheet", fail_create)

    created = admin_client.post("/api/forms", json=sample_form())

    assert created.status_code == 201
    form_id = created.json()["id"]
    assert repository.get_form(form_id=form_id) is not None
    sheet = created.json()["sheet"]
    assert sheet["status"] == "error"
    assert "request limit" in sheet["detail"]
    assert "sensitive-marker" not in sheet["detail"]
    assert repository.get_form(form_id=form_id)["sheet_error"] == sheet["detail"]


def test_draft_is_hidden_from_the_public(admin_client):
    res = admin_client.post("/api/forms", json=sample_form(is_published=False))
    form_id = res.json()["id"]
    ref = repository.get_form(form_id=form_id)["public_ref"]

    assert admin_client.get(f"/f/{ref}").status_code == 200  # admin preview
    anon = TestClient(admin_client.app)
    assert anon.get(f"/f/{ref}").status_code == 404
    assert anon.post(f"/f/{ref}", json={}).status_code == 404


def test_responses_page_renders(admin_client):
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    qid = repository.get_form(form_id=form_id)["questions"][0]["id"]
    repository.save_response(form_id, {qid: "@visible"})

    page = admin_client.get(f"/admin/{form_id}/responses")
    assert page.status_code == 200 and "@visible" in page.text


def test_new_form_redirect_target_renders_serializable_builder_data(admin_client):
    """Postgres timestamps and Sheet metadata must never enter FORM_DATA."""
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]

    page = admin_client.get(f"/admin/{form_id}")

    assert page.status_code == 200
    assert "window.FORM_DATA" in page.text
    assert "Creator intake" in page.text


# --------------------------------------------------------------- role split


def test_public_role_has_no_admin_surface(monkeypatch):
    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    public = TestClient(app_module.create_app())

    for path in ("/", "/login", "/admin/new"):
        assert public.get(path).status_code == 404, path
    assert public.post("/api/forms", json={"title": "x"}).status_code == 404
    assert public.get("/healthz").status_code == 200


def test_admin_routes_refuse_non_local_clients(monkeypatch, admin_client):
    from formcraft import app as app_module

    monkeypatch.setattr(app_module, "LOOPBACK", set())
    assert admin_client.get("/", follow_redirects=False).status_code == 404
    assert admin_client.post("/api/forms", json=sample_form()).status_code == 404
    # The public form surface stays reachable.
    assert admin_client.get("/healthz").status_code == 200


# ------------------------------------------------------------------- export


def test_csv_export_includes_archived_questions(admin_client):
    """A deleted question still has answers in old responses — keep the column."""
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    qids = [q["id"] for q in repository.get_form(form_id=form_id)["questions"]]
    repository.save_response(
        form_id, {qids[0]: "@early", qids[1]: "e@x.co", qids[2]: ["IG"], qids[3]: 5}
    )

    # Drop the last two questions from the form.
    payload = sample_form()
    payload["sections"][0]["questions"] = [
        {"id": qids[0], "type": "short_text", "label": "Handle"},
        {"id": qids[1], "type": "email", "label": "Email"},
    ]
    admin_client.put(f"/api/forms/{form_id}", json=payload)

    res = admin_client.get(f"/admin/{form_id}/export.csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]

    body = res.content.decode("utf-8-sig")
    assert "Submitted at,Handle,Email" in body
    assert "(removed)" in body, "archived columns must survive the export"
    assert "@early" in body and "IG" in body


def test_xlsx_export_is_a_real_workbook(admin_client):
    import io
    import zipfile

    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    qid = repository.get_form(form_id=form_id)["questions"][0]["id"]
    repository.save_response(form_id, {qid: "@someone"})

    res = admin_client.get(f"/admin/{form_id}/export.xlsx")
    assert res.status_code == 200
    assert "spreadsheetml" in res.headers["content-type"]

    # An xlsx is a zip; if it opens and has a workbook part, it is well formed.
    with zipfile.ZipFile(io.BytesIO(res.content)) as book:
        names = book.namelist()
        assert "xl/workbook.xml" in names
        shared = book.read("xl/sharedStrings.xml").decode()
        assert "@someone" in shared


def test_export_requires_admin(admin_client):
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    anon = TestClient(admin_client.app)
    assert anon.get(f"/admin/{form_id}/export.csv").status_code == 401
    assert anon.get(f"/admin/{form_id}/export.xlsx").status_code == 401


def test_feed_needs_the_right_key(admin_client):
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    qid = repository.get_form(form_id=form_id)["questions"][0]["id"]
    repository.save_response(form_id, {qid: "@feedtest"})

    # No key issued yet -> the feed does not exist.
    assert admin_client.get(f"/feed/{form_id}.csv").status_code == 404

    key = admin_client.post(f"/api/forms/{form_id}/export-key").json()["key"]
    assert admin_client.get(f"/feed/{form_id}.csv", params={"key": key}).status_code == 200
    assert "@feedtest" in admin_client.get(
        f"/feed/{form_id}.csv", params={"key": key}
    ).content.decode("utf-8-sig")

    # Wrong key, and a rotated key, both close the door.
    assert admin_client.get(f"/feed/{form_id}.csv", params={"key": "nope"}).status_code == 404
    new_key = admin_client.post(f"/api/forms/{form_id}/export-key").json()["key"]
    assert new_key != key
    assert admin_client.get(f"/feed/{form_id}.csv", params={"key": key}).status_code == 404

    admin_client.post(f"/api/forms/{form_id}/export-key", params={"rotate": "false"})
    assert admin_client.get(f"/feed/{form_id}.csv", params={"key": new_key}).status_code == 404


def test_feed_is_not_registered_on_the_public_instance(monkeypatch):
    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    public = TestClient(app_module.create_app())
    assert public.get("/feed/anything.csv", params={"key": "x"}).status_code == 404


# ---------------------------------------------------- visitor confinement


def test_public_ref_is_unguessable_and_slug_does_not_resolve(admin_client):
    """A readable slug must not be a working URL — otherwise one link leaks all."""
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    form = repository.get_form(form_id=form_id)

    assert form["slug"] == "creator-intake"
    assert form["public_ref"].startswith("creator-intake-")
    # ~12 random urlsafe chars appended
    assert len(form["public_ref"]) > len(form["slug"]) + 8

    assert admin_client.get(f"/f/{form['public_ref']}").status_code == 200
    assert admin_client.get("/f/creator-intake").status_code == 404


def test_public_ref_survives_a_rename(admin_client):
    """Shared links must keep working after the form is retitled."""
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    original_ref = repository.get_form(form_id=form_id)["public_ref"]

    renamed = sample_form(title="Totally Different Name")
    admin_client.put(f"/api/forms/{form_id}", json=renamed)

    after = repository.get_form(form_id=form_id)
    assert after["slug"] == "totally-different-name"
    assert after["public_ref"] == original_ref
    assert admin_client.get(f"/f/{original_ref}").status_code == 200


def test_one_form_link_does_not_expose_another(monkeypatch, admin_client):
    """The whole point: a visitor holding form A cannot reach form B."""
    a = admin_client.post("/api/forms", json=sample_form(title="Public Survey")).json()["id"]
    b = admin_client.post("/api/forms", json=sample_form(title="Private Intake")).json()["id"]
    ref_a = repository.get_form(form_id=a)["public_ref"]
    form_b = repository.get_form(form_id=b)

    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    visitor = TestClient(app_module.create_app())

    assert visitor.get(f"/f/{ref_a}").status_code == 200
    # Guessing form B by its readable slug, or by internal id, both fail.
    assert visitor.get(f"/f/{form_b['slug']}").status_code == 404
    assert visitor.get(f"/f/{b}").status_code == 404


def test_visitor_cannot_reach_exports_or_the_live_link(monkeypatch, admin_client):
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    key = admin_client.post(f"/api/forms/{form_id}/export-key").json()["key"]

    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    visitor = TestClient(app_module.create_app())

    for path in (
        f"/admin/{form_id}/export.csv",
        f"/admin/{form_id}/export.xlsx",
        f"/admin/{form_id}/responses",
        f"/api/forms/{form_id}/export-key",
        "/api/sync",
    ):
        assert visitor.get(path).status_code == 404, path
    # Even holding a valid export key, the feed route does not exist here.
    assert visitor.get(f"/feed/{form_id}.csv", params={"key": key}).status_code == 404


def test_public_form_is_not_indexable(admin_client):
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    ref = repository.get_form(form_id=form_id)["public_ref"]

    res = admin_client.get(f"/f/{ref}")
    assert "noindex" in res.headers.get("x-robots-tag", "")
    assert 'name="robots"' in res.text and "noindex" in res.text
    assert res.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert "s-maxage=300" in res.headers["vercel-cdn-cache-control"]


def test_public_form_embeds_configured_calendly_link(admin_client):
    meeting_url = "https://calendly.com/example/30min"
    form_id = admin_client.post(
        "/api/forms", json=sample_form(meeting_url=meeting_url)
    ).json()["id"]
    ref = repository.get_form(form_id=form_id)["public_ref"]

    page = admin_client.get(f"/f/{ref}")

    assert page.status_code == 200
    assert 'class="calendly-inline-widget"' in page.text
    assert f'data-url="{meeting_url}"' in page.text
    assert "https://assets.calendly.com/assets/external/widget.js" in page.text
    assert 'id="calendly-booking"' in page.text
    assert 'aria-labelledby="booking-title" hidden' in page.text
    assert "Your form response is already saved." in page.text
    assert "Open Calendly separately" not in page.text
    assert ">Submit form<" in page.text
    assert 'id="again" type="button" hidden>Submit another response<' in page.text


def test_public_form_hides_calendly_metadata_fields(admin_client):
    payload = sample_form(meeting_url="https://calendly.com/example/30min")
    payload["sections"][0]["questions"].append(
        {
            "type": "short_text",
            "label": "Calendly event URI",
            "required": False,
            "config": {"hidden": True, "calendly_field": "event_uri"},
        }
    )
    form_id = admin_client.post("/api/forms", json=payload).json()["id"]
    form = repository.get_form(form_id=form_id)

    page = admin_client.get(f"/f/{form['public_ref']}")

    assert page.status_code == 200
    assert 'data-calendly-field="event_uri"' in page.text
    assert 'type="hidden"' in page.text
    assert '>Calendly event URI<' not in page.text

    script = admin_client.get("/static/form.js").text
    assert "document.querySelectorAll('.field[data-hidden=\"0\"]')" in script
    assert "againBtn.hidden = false" in script


def test_booking_after_submission_updates_same_response_and_sheet(
    monkeypatch, admin_client
):
    from formcraft import sheets

    payload = sample_form(meeting_url="https://calendly.com/example/30min")
    payload["sections"][0]["questions"].extend(
        [
            {
                "type": "short_text",
                "label": "Calendly booking status",
                "config": {"hidden": True, "calendly_field": "status"},
            },
            {
                "type": "short_text",
                "label": "Calendly event URI",
                "config": {"hidden": True, "calendly_field": "event_uri"},
            },
        ]
    )
    form_id = admin_client.post("/api/forms", json=payload).json()["id"]
    repository.set_sheet(form_id, "sheet-123", "https://docs.google.com/sheet-123")
    patch_settings(monkeypatch, google_enabled=True)
    sheet_writes: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        sheets,
        "append_response",
        lambda form, response_id, answers, submitted_at=None: sheet_writes.append(
            (response_id, answers)
        ),
    )

    form = repository.get_form(form_id=form_id)
    submitted = admin_client.post(
        f"/f/{form['public_ref']}",
        json={
            form["questions"][0]["id"]: "@direct",
            form["questions"][1]["id"]: "direct@example.com",
        },
    )
    response_id = submitted.json()["id"]

    booked = admin_client.post(
        f"/f/{form['public_ref']}/responses/{response_id}/booking",
        json={"status": "Booked", "event_uri": "https://api.calendly.com/events/1"},
    )

    assert booked.status_code == 200
    assert booked.json()["sheet_synced"] is True
    responses = repository.list_responses(form_id)
    assert len(responses) == 1
    fields = {
        question["config"].get("calendly_field"): question["id"]
        for question in form["questions"]
        if question["config"].get("calendly_field")
    }
    assert responses[0]["payload"][fields["status"]] == "Booked"
    assert responses[0]["payload"][fields["event_uri"]].endswith("/events/1")
    assert [item[0] for item in sheet_writes] == [response_id, response_id]
    assert sheet_writes[-1][1] == responses[0]["payload"]


def test_native_google_booking_waits_then_updates_same_sheet_row(
    monkeypatch, admin_client
):
    from datetime import UTC, datetime, timedelta

    from formcraft import calendar_booking, sheets
    from formcraft.business_inquiry import business_inquiry_form

    payload = business_inquiry_form(
        title="Business Inquiry & Google Meeting",
        provider="google_api",
        meeting_url="",
    )
    form_id = repository.create_form(
        payload,
        sheet_profile="booking",
        booking_mode="google_api",
        booking_config=calendar_booking.DEFAULT_BOOKING_CONFIG,
    )
    repository.set_sheet(form_id, "sheet-native", "https://docs.google.com/native")
    patch_settings(monkeypatch, google_enabled=True)

    sheet_writes: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        sheets,
        "append_response",
        lambda form, response_id, answers, submitted_at=None: sheet_writes.append(
            (response_id, answers)
        ),
    )

    form = repository.get_form(form_id=form_id)
    fields = {
        question["config"].get("booking_field"): question["id"]
        for question in form["questions"]
        if question["config"].get("booking_field")
    }
    submitted = admin_client.post(
        f"/f/{form['public_ref']}",
        json={
                fields["attendee_name"]: "Ada Visitor",
                fields["attendee_email"]: "ada@example.com",
                fields["business_name"]: "Analytical Engines",
                next(q["id"] for q in form["questions"] if q["label"] == "Phone number"): "+1 555 0100",
                next(q["id"] for q in form["questions"] if q["label"] == "Business description"): "Computing",
            next(q["id"] for q in form["questions"] if q["label"] == "Main business problem"): "Growth",
            next(q["id"] for q in form["questions"] if q["label"] == "Budget currency"): "US Dollar ($)",
            next(q["id"] for q in form["questions"] if q["label"] == "Approximate budget"): "1000",
        },
    )
    assert submitted.status_code == 200
    response_id = submitted.json()["id"]
    token = submitted.json()["booking_token"]
    assert token
    assert sheet_writes == []
    assert repository.get_response(form_id, response_id)["sync_ready"] is False

    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=2)
    end = start + timedelta(hours=1)
    monkeypatch.setattr(
        calendar_booking, "candidate_slots", lambda config, now=None: [(start, end)]
    )
    monkeypatch.setattr(
        calendar_booking,
        "available_slots",
        lambda form, local_busy, now=None: [(start, end)],
    )
    monkeypatch.setattr(calendar_booking, "get_event", lambda profile, event_id: None)
    monkeypatch.setattr(
        calendar_booking, "busy_intervals", lambda profile, start, end: []
    )
    event = {
        "id": "fcevent123",
        "htmlLink": "https://calendar.google.com/event/123",
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
    }
    monkeypatch.setattr(
        calendar_booking, "create_or_recover_event", lambda **kwargs: event
    )
    invitations: list[str] = []

    def invite(profile, created_event, name, email):
        invitations.append(email)
        return created_event

    monkeypatch.setattr(calendar_booking, "invite_attendee", invite)

    headers = {
        "X-Booking-Token": token,
        "X-Vercel-IP-Timezone": "America/New_York",
    }
    slots = admin_client.get(
        f"/f/{form['public_ref']}/responses/{response_id}/booking/slots",
        headers=headers,
    )
    assert slots.status_code == 200
    assert slots.json()["viewer_timezone"] == "America/New_York"
    assert slots.json()["schedule"]["last_start"] == "23:00"
    assert slots.json()["schedule"]["duration_minutes"] == 60

    booked = admin_client.post(
        f"/f/{form['public_ref']}/responses/{response_id}/booking/confirm",
        headers=headers,
        json={"start": start.isoformat(), "timezone": "Europe/London"},
    )
    assert booked.status_code == 200, booked.text
    assert booked.json()["invitation_sent"] is True
    assert booked.json()["sheet_synced"] is True
    assert booked.json()["meet_url"] == event["hangoutLink"]
    assert invitations == ["ada@example.com"]
    assert [write[0] for write in sheet_writes] == [response_id]

    response = repository.get_response(form_id, response_id)
    assert response["sync_ready"] is True
    assert response["synced"] is True
    assert response["payload"][fields["status"]] == "Booked"
    assert response["payload"][fields["meet_url"]] == event["hangoutLink"]

    repeated = admin_client.post(
        f"/f/{form['public_ref']}/responses/{response_id}/booking/confirm",
        headers=headers,
        json={"start": start.isoformat(), "timezone": "Europe/London"},
    )
    assert repeated.status_code == 200
    assert invitations == ["ada@example.com"]
    assert len(sheet_writes) == 1

    forged = admin_client.get(
        f"/f/{form['public_ref']}/responses/{response_id}/booking/slots",
        headers={"X-Booking-Token": "wrong"},
    )
    assert forged.status_code == 404


def test_public_form_never_exposes_missing_media_placeholders(
    monkeypatch, admin_client
):
    """Recipients should never see internal slot names or generation briefs."""
    form_id = admin_client.post("/api/forms", json=sample_form()).json()["id"]
    ref = repository.get_form(form_id=form_id)["public_ref"]

    from formcraft import media

    monkeypatch.setattr(media, "resolve", lambda slot_name, variant="": None)
    page = admin_client.get(f"/f/{ref}")

    assert page.status_code == 200
    assert "media-ph" not in page.text
    assert 'class="trust"' not in page.text


def test_no_api_schema_is_served(monkeypatch, admin_client):
    """OpenAPI names the app and enumerates every route — never expose it."""
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert admin_client.get(path).status_code == 404, path

    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    visitor = TestClient(app_module.create_app())
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert visitor.get(path).status_code == 404, path


def test_public_healthz_leaks_no_deployment_detail(monkeypatch):
    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    visitor = TestClient(app_module.create_app())

    body = visitor.get("/healthz").json()
    assert body == {"ok": True}
    assert "role" not in body and "database" not in body


# --------------------------------------------------------------- assets & 404


def test_media_gallery_lists_every_slot(admin_client):
    from formcraft.media import SLOTS

    page = admin_client.get("/admin/media")
    assert page.status_code == 200
    # /admin/media must not be swallowed by the /admin/{form_id} route.
    assert "Form not found" not in page.text
    for name in SLOTS:
        assert f"{name}.webp" in page.text, name


def test_briefs_download_covers_every_slot(admin_client):
    from formcraft.media import SLOTS

    res = admin_client.get("/admin/media/briefs.txt")
    assert res.status_code == 200
    assert "attachment" in res.headers["content-disposition"]
    body = res.content.decode()
    for name in SLOTS:
        assert f"{name}.webp" in body, name
    assert body.count("[FILLED]") + body.count("[MISSING]") == len(SLOTS)


def test_mistyped_form_link_gets_a_branded_page(admin_client):
    res = admin_client.get("/f/does-not-exist-abc123")
    assert res.status_code == 404
    assert "This form isn't available" in res.text
    assert "noindex" in res.headers.get("x-robots-tag", "")
    # Never leak the raw API error to a visitor.
    assert '{"detail"' not in res.text


def test_non_form_paths_stay_bare_404(monkeypatch):
    """A styled page anywhere else would confirm what is running here."""
    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    visitor = TestClient(app_module.create_app())

    for path in ("/", "/login", "/admin/media", "/wp-admin"):
        res = visitor.get(path)
        assert res.status_code == 404, path
        assert "This form isn't available" not in res.text, path


def test_gallery_and_briefs_are_admin_only(monkeypatch, admin_client):
    anon = TestClient(admin_client.app)
    assert anon.get("/admin/media", follow_redirects=False).status_code == 302
    assert anon.get("/admin/media/briefs.txt").status_code == 401

    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", admin_password_hash="", secret_key="")
    visitor = TestClient(app_module.create_app())
    assert visitor.get("/admin/media").status_code == 404
    assert visitor.get("/admin/media/briefs.txt").status_code == 404


@pytest.mark.parametrize("mode", ["single", "section", "one_by_one"])
def test_provider_credit_is_independent_of_owner_brand(admin_client, monkeypatch, mode):
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.credit_links = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "a" and values.get("href") == "https://catapultaiwork.com":
                self.credit_links.append(values)

    patch_settings(monkeypatch, brand_name="Example organization")
    form_id = repository.create_form(FormIn.model_validate(sample_form(display_mode=mode)))
    form = repository.get_form(form_id=form_id)
    page = admin_client.get(f"/f/{form['public_ref']}")
    assert page.status_code == 200
    parsed = Links()
    parsed.feed(page.text)
    assert len(parsed.credit_links) == 1
    assert "Powered by <a" in page.text
    assert ">catapultaiwork</a>" in page.text
    assert "Example organization" in page.text
    assert "Powered by Example organization" not in page.text


def test_removed_private_ingestion_route_is_absent(monkeypatch):
    from formcraft import app as app_module

    patch_settings(monkeypatch, role="public", secret_key="", admin_password_hash="")
    app = app_module.create_app()
    assert not any("/api/integrations/" in getattr(route, "path", "") for route in app.routes)
    with TestClient(app) as client:
        for path in ("/login", "/admin/new", "/api/forms"):
            assert client.get(path).status_code == 404
