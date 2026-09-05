# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""One owner-controlled Google connection, encrypted in this installation's DB."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any

from cryptography.fernet import Fernet
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from psycopg.types.json import Jsonb

from .config import settings
from .db import readonly, transaction

IDENTITY_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/drive.file", *IDENTITY_SCOPES]
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar.freebusy",
]


def _cipher() -> Fernet:
    if len(settings.secret_key) < 32:
        raise ValueError("A strong installation secret is required for Google storage.")
    key = hashlib.sha256(
        ("formcraft-google-v1:" + settings.secret_key).encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(payload: dict) -> str:
    return _cipher().encrypt(json.dumps(payload).encode()).decode()


def _decrypt(value: str) -> dict:
    return json.loads(_cipher().decrypt(value.encode()))


def configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    return settings.base_url + "/oauth/google/callback"


def summary() -> dict:
    with readonly() as conn:
        row = conn.execute(
            "SELECT email, encrypted_token <> '' AS connected, scopes "
            "FROM google_connection WHERE singleton"
        ).fetchone()
    return {
        "connected": bool(row and row["connected"]),
        "email": row["email"] if row else "",
        "calendar": bool(row and set(CALENDAR_SCOPES) <= set(row["scopes"])),
    }


def token_payload() -> dict | None:
    with readonly() as conn:
        row = conn.execute(
            "SELECT encrypted_token FROM google_connection WHERE singleton"
        ).fetchone()
    if not row or not row["encrypted_token"]:
        return None
    return _decrypt(row["encrypted_token"])


def persist_refresh(previous: dict, updated: dict) -> None:
    """Never resurrect a disconnected/replaced grant after an in-flight refresh."""
    with transaction() as conn:
        row = conn.execute(
            "SELECT encrypted_token FROM google_connection WHERE singleton FOR UPDATE"
        ).fetchone()
        if (
            row
            and row["encrypted_token"]
            and _decrypt(row["encrypted_token"]) == previous
        ):
            conn.execute(
                "UPDATE google_connection SET encrypted_token = %s, updated_at = now() "
                "WHERE singleton",
                (_encrypt(updated),),
            )


def _flow(scopes: list[str], **kwargs: Any) -> Flow:
    if not configured():
        raise ValueError("Configure your Google Web application OAuth client first.")
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri()],
            }
        },
        scopes=scopes,
        redirect_uri=redirect_uri(),
        **kwargs,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def start(session_cookie: str, calendar: bool) -> str:
    # Reconnection cannot silently downgrade an existing Calendar grant.
    scopes = SHEETS_SCOPES + (
        CALENDAR_SCOPES if calendar or summary()["calendar"] else []
    )
    flow = _flow(scopes, autogenerate_code_verifier=True)
    nonce = secrets.token_urlsafe(32)
    url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        nonce=nonce,
    )
    payload = {"scopes": scopes, "verifier": flow.code_verifier, "nonce": nonce}
    with transaction() as conn:
        conn.execute("DELETE FROM google_oauth_states WHERE expires_at < now()")
        conn.execute(
            "INSERT INTO google_oauth_states "
            "(state_hash, session_hash, encrypted_request, expires_at) "
            "VALUES (%s, %s, %s, now() + interval '10 minutes')",
            (_digest(state), _digest(session_cookie), _encrypt(payload)),
        )
    return url


def consume_state(state: str, session_cookie: str) -> dict:
    with transaction() as conn:
        row = conn.execute(
            "DELETE FROM google_oauth_states WHERE state_hash = %s "
            "AND session_hash = %s AND expires_at > now() RETURNING encrypted_request",
            (_digest(state), _digest(session_cookie)),
        ).fetchone()
    if not row:
        raise ValueError("This Google connection attempt expired or was already used.")
    return _decrypt(row["encrypted_request"])


def exchange(code: str, state_data: dict) -> tuple[dict, dict]:
    flow = _flow(state_data["scopes"], code_verifier=state_data["verifier"])
    flow.fetch_token(code=code, timeout=20)
    credentials = flow.credentials
    identity = id_token.verify_oauth2_token(
        credentials.id_token,
        GoogleRequest(),
        settings.google_client_id,
    )
    if (
        not identity.get("sub")
        or not identity.get("email_verified")
        or not secrets.compare_digest(
            str(identity.get("nonce", "")), str(state_data["nonce"])
        )
    ):
        raise ValueError("Google did not verify the expected account identity.")
    payload = json.loads(credentials.to_json())
    granted = credentials.granted_scopes or credentials.scopes or []
    if not set(state_data["scopes"]) <= set(granted):
        raise ValueError("Google did not grant all requested permissions.")
    payload["scopes"] = list(granted)
    return identity, payload


def save(identity: dict, payload: dict) -> None:
    """Keep Sheets and existing bookings tied to the same verified owner account."""
    with transaction() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(784246020)")
        previous = conn.execute(
            "SELECT * FROM google_connection WHERE singleton FOR UPDATE"
        ).fetchone()
        if previous and previous["provider_subject"] != identity["sub"]:
            used = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM forms WHERE sheet_id IS NOT NULL "
                "OR booking_mode = 'google_api') AS used"
            ).fetchone()["used"]
            if used:
                raise ValueError(
                    "Reconnect the original Google account. Existing forms use its "
                    "Sheets or Calendar; changing accounts would break those links."
                )
        if not payload.get("refresh_token"):
            if (
                previous
                and previous["encrypted_token"]
                and (previous["provider_subject"] == identity["sub"])
            ):
                payload["refresh_token"] = _decrypt(previous["encrypted_token"]).get(
                    "refresh_token"
                )
            if not payload.get("refresh_token"):
                raise ValueError(
                    "Google returned no refresh token. Reconnect with consent."
                )
        conn.execute(
            "INSERT INTO google_connection "
            "(singleton, provider_subject, email, encrypted_token, scopes) "
            "VALUES (TRUE, %s, %s, %s, %s) ON CONFLICT (singleton) DO UPDATE SET "
            "provider_subject = EXCLUDED.provider_subject, email = EXCLUDED.email, "
            "encrypted_token = EXCLUDED.encrypted_token, scopes = EXCLUDED.scopes, "
            "updated_at = now()",
            (
                identity["sub"],
                identity["email"],
                _encrypt(payload),
                Jsonb(payload["scopes"]),
            ),
        )


def disconnect() -> None:
    # Keep account identity so reconnecting cannot retarget existing forms.
    # Users can also revoke the grant in Google's account permissions UI.
    with transaction() as conn:
        conn.execute(
            "UPDATE google_connection SET encrypted_token = '', updated_at = now() "
            "WHERE singleton"
        )
        conn.execute("DELETE FROM google_oauth_states")
