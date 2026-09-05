# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Hosted ownership, OAuth state, encrypted grants, and browser meeting setup."""

from __future__ import annotations

import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from formcraft import (
    app,
    auth,
    calendar_booking,
    config,
    db,
    google_connection,
    hosted,
    repository,
    sheets,
)
from formcraft.models import FormIn

ORIGIN = "https://forms.example.com"
PASSWORD = "owner-password-for-tests"


@pytest.fixture
def site(monkeypatch):
    db.init_db()
    with db.transaction() as conn:
        for table in (
            "forms",
            "google_connection",
            "google_oauth_states",
            "admin_login_limits",
        ):
            conn.execute(f"DELETE FROM {table}")
    patched = replace(
        config.settings,
        role="hosted",
        admin_password=PASSWORD,
        admin_password_hash="",
        secret_key="a-unique-long-installation-secret-for-tests",
        base_url=ORIGIN,
        secure_cookies=True,
        google_default_profile="booking",
        google_client_id="example-client.apps.googleusercontent.com",
        google_client_secret="synthetic-client-secret",
    )
    for module in (
        config,
        app,
        auth,
        db,
        sheets,
        calendar_booking,
        hosted,
        google_connection,
    ):
        monkeypatch.setattr(module, "settings", patched)
    auth.clear_failures()
    with TestClient(app.create_app(), base_url=ORIGIN) as client:
        yield client


def login(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": PASSWORD},
        headers={"Origin": ORIGIN},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return response


def connect(client, monkeypatch, subject="owner-subject", calendar=False):
    response = client.post(
        "/oauth/google/start",
        data={"calendar": "1" if calendar else "0"},
        headers={"Origin": ORIGIN},
        follow_redirects=False,
    )
    assert response.status_code == 303
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["redirect_uri"] == [ORIGIN + "/oauth/google/callback"]
    assert query["code_challenge_method"] == ["S256"]
    payload = {
        "refresh_token": "synthetic-refresh-secret",
        "token": "synthetic-access-secret",
        "client_id": "test-client",
        "client_secret": "test-client-secret",
        "scopes": google_connection.SHEETS_SCOPES
        + (google_connection.CALENDAR_SCOPES if calendar else []),
    }
    monkeypatch.setattr(
        google_connection,
        "exchange",
        lambda code, state: ({"sub": subject, "email": "owner@example.com"}, payload),
    )
    response = client.get(
        "/oauth/google/callback",
        params={"state": query["state"][0], "code": "test-code"},
        follow_redirects=False,
    )
    return response, query["state"][0], payload


def test_hosted_owner_routes_and_csrf(site):
    assert site.get("/", follow_redirects=False).headers["location"] == "/login"
    for path in ("/api/forms", "/oauth/google/disconnect"):
        assert site.post(path, json={}, headers={"Origin": ORIGIN}).status_code == 401
    assert site.get("/admin/integrations", follow_redirects=False).status_code == 302
    assert (
        site.get("/oauth/google/callback?state=forged&code=forged").status_code == 401
    )
    assert site.post("/login", data={}).status_code == 403
    assert (
        site.post(
            "/login", data={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    response = login(site)
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert site.get("/").status_code == 200
    assert site.get("/").headers["cache-control"] == "no-store"
    assert site.get("/admin/integrations").status_code == 200
    assert site.get("/feed/any.csv?key=any").status_code == 404
    assert site.get("/healthz").json() == {"ok": True}


def test_oauth_state_once_encryption_and_disconnect(site, monkeypatch):
    login(site)
    response, state, payload = connect(site, monkeypatch)
    assert response.headers["location"].endswith("result=connected")
    with db.readonly() as conn:
        row = conn.execute("SELECT * FROM google_connection").fetchone()
    assert payload["refresh_token"] not in row["encrypted_token"]
    assert (
        google_connection.token_payload()["refresh_token"] == payload["refresh_token"]
    )
    assert sheets.enabled()
    assert (
        site.get(
            "/oauth/google/callback", params={"state": state, "code": "replay"}
        ).status_code
        == 400
    )
    page = site.get("/admin/integrations")
    assert "owner@example.com" in page.text
    assert payload["refresh_token"] not in page.text
    assert payload["token"] not in page.text
    assert (
        site.post("/oauth/google/disconnect", headers={"Origin": ORIGIN}).status_code
        == 200
    )
    assert google_connection.token_payload() is None
    assert not sheets.enabled()
    # An in-flight refresh cannot resurrect the removed credential.
    google_connection.persist_refresh(payload, {**payload, "token": "later-token"})
    assert google_connection.token_payload() is None


def test_oauth_state_bound_to_login_session_and_expiry(site):
    login(site)
    response = site.post(
        "/oauth/google/start", headers={"Origin": ORIGIN}, follow_redirects=False
    )
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    login(site)  # Different random session ID, even for the same owner.
    assert (
        site.get(
            "/oauth/google/callback", params={"state": state, "code": "x"}
        ).status_code
        == 400
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE google_oauth_states SET expires_at = now() - interval '1 second'"
        )
    assert (
        site.get(
            "/oauth/google/callback", params={"state": state, "code": "x"}
        ).status_code
        == 400
    )


def test_google_account_switch_cannot_retarget_existing_sheets(site, monkeypatch):
    login(site)
    assert connect(site, monkeypatch)[0].headers["location"].endswith("connected")
    form_id = repository.create_form(FormIn(title="Survey", sections=[{"questions": [{"type": "short_text", "label": "Name"}]}]))
    repository.set_sheet(
        form_id, "existing-sheet", "https://docs.google.com/existing-sheet"
    )
    response, _, _ = connect(site, monkeypatch, subject="another-account")
    assert response.headers["location"].endswith("result=failed")
    with db.readonly() as conn:
        assert (
            conn.execute("SELECT provider_subject FROM google_connection").fetchone()[
                "provider_subject"
            ]
            == "owner-subject"
        )


def test_login_budget_persists_across_requests(site):
    for _ in range(20):
        assert hosted.login_attempt_allowed()
    assert not hosted.login_attempt_allowed()
    assert (
        site.post(
            "/login",
            headers={"Origin": ORIGIN},
            data={"username": "admin", "password": PASSWORD},
        ).status_code
        == 429
    )


def test_password_change_invalidates_owner_cookie(site, monkeypatch):
    login(site)
    monkeypatch.setattr(
        auth, "settings", replace(auth.settings, admin_password="replacement-password")
    )
    assert site.get("/", follow_redirects=False).status_code == 302


def test_hosted_settings_fail_closed(site, monkeypatch):
    for changes in (
        {"secret_key": "short"},
        {"admin_password": "short"},
        {"base_url": "http://forms.example.com"},
        {"secure_cookies": False},
        {"database_url": ""},
        {"base_url": "https://forms.example.com/other"},
    ):
        monkeypatch.setattr(config, "settings", replace(app.settings, **changes))
        with pytest.raises(RuntimeError, match="Hosted setup requires"):
            config.validate_hosted_settings()


def test_meeting_wizard_creates_draft_and_keeps_google_optional(site, monkeypatch):
    login(site)
    assert "Connect Google Sheets + Calendar" in site.get("/admin/new-meeting").text
    connect(site, monkeypatch, calendar=True)
    monkeypatch.setattr(sheets, "create_spreadsheet", lambda form: (
        "wizard-sheet", "https://docs.google.com/spreadsheets/d/wizard-sheet/edit"
    ))
    fields = {
        "title": "Meet our team",
        "timezone": "Europe/London",
        "weekdays": ["0", "2"],
        "first_start": "10:00",
        "last_start": "16:00",
        "duration_minutes": "30",
        "minimum_notice_hours": "2",
        "booking_window_days": "14",
    }
    response = site.post(
        "/admin/new-meeting",
        data=fields,
        headers={"Origin": ORIGIN},
        follow_redirects=False,
    )
    assert response.status_code == 303
    form_id = response.headers["location"].split("/")[-1]
    form = repository.get_form(form_id=form_id)
    assert not form["is_published"]
    assert form["booking_mode"] == "google_api"
    assert form["sheet_id"] == "wizard-sheet"
    assert form["sheet_profile"] == "booking"
    assert form["booking_config"]["timezone"] == "Europe/London"
    assert form["booking_config"]["weekdays"] == [0, 2]
    assert site.get(f"/admin/{form_id}").status_code == 200
    assert "Meeting settings" in site.get(f"/admin/{form_id}").text
    assert site.get(f"/admin/{form_id}/booking").status_code == 200
    before = len(repository.list_forms())
    site.post(
        "/admin/new-meeting",
        data={**fields, "booking_window_days": "999999"},
        headers={"Origin": ORIGIN},
    )
    assert len(repository.list_forms()) == before


def test_owner_creates_two_forms_respondent_sees_only_published_links(
    site, monkeypatch
):
    login(site)
    ids = []
    for title in ("Contact", "Feedback"):
        response = site.post(
            "/api/forms",
            headers={"Origin": ORIGIN},
            json={
                "title": title,
                "is_published": title == "Contact",
                "sections": [
                    {
                        "questions": [
                            {"type": "short_text", "label": "Name", "required": True}
                        ]
                    }
                ],
            },
        )
        assert response.status_code == 201
        ids.append(response.json()["id"])
    first, second = [repository.get_form(form_id=i) for i in ids]
    assert first["public_ref"] != second["public_ref"]
    assert site.get(f"/f/{second['public_ref']}").status_code == 200  # Owner preview.
    site.cookies.clear()
    assert site.get(f"/f/{second['public_ref']}").status_code == 404
    page = site.get(f"/f/{first['public_ref']}")
    assert page.status_code == 200 and "catapultaiwork" in page.text
    response = site.post(
        f"/f/{first['public_ref']}",
        json={first["questions"][0]["id"]: "Visitor"},
    )
    assert response.status_code == 200
    assert (
        repository.list_responses(first["id"])[0]["payload"][
            first["questions"][0]["id"]
        ]
        == "Visitor"
    )
    assert (
        site.get(f"/admin/{first['id']}/responses", follow_redirects=False).status_code
        == 302
    )
    assert site.get(f"/admin/{first['id']}/export.csv").status_code == 401


def test_exchange_verifies_nonce_and_permissions(site, monkeypatch):
    class Credentials:
        id_token = "synthetic-id-token"
        granted_scopes = google_connection.SHEETS_SCOPES

        def to_json(self):
            return json.dumps({"refresh_token": "synthetic-refresh"})

    class Flow:
        credentials = Credentials()

        def fetch_token(self, **kwargs):
            assert kwargs["code"] == "synthetic-code"

    monkeypatch.setattr(google_connection, "_flow", lambda *a, **kw: Flow())
    monkeypatch.setattr(
        google_connection.id_token,
        "verify_oauth2_token",
        lambda *a: {
            "sub": "owner",
            "email": "owner@example.com",
            "email_verified": True,
            "nonce": "expected",
        },
    )
    data = {
        "scopes": google_connection.SHEETS_SCOPES,
        "verifier": "verifier",
        "nonce": "expected",
    }
    identity, payload = google_connection.exchange("synthetic-code", data)
    assert identity["sub"] == "owner" and payload["refresh_token"]
    with pytest.raises(ValueError, match="identity"):
        google_connection.exchange("synthetic-code", {**data, "nonce": "wrong"})
