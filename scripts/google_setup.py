# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Guided Google authorisation, with verification.

This does everything except the two things that need your Google password:
creating the OAuth client in the Cloud Console, and clicking Allow. It walks
you through those, runs the flow, then proves the result works by creating a
real spreadsheet and deleting it again.

The token stays in a protected local file. Copy its contents into your
Vercel environment settings when you want live synchronization.

    uv run python scripts/google_setup.py
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from formcraft.config import settings  # noqa: E402
from formcraft.sheets import scopes_for_profile, token_payload  # noqa: E402

CONSOLE = "https://console.cloud.google.com"

CHECKLIST = f"""
Do these once in the Google Cloud Console. They need your Google password,
so they are yours to click — everything after is automatic.

  1. {CONSOLE}/projectcreate
     Create a project (any name).

  2. {CONSOLE}/apis/library/drive.googleapis.com
     Enable the Google Drive API.

  3. {CONSOLE}/apis/library/sheets.googleapis.com
     Enable the Google Sheets API.

  4. {CONSOLE}/apis/library/calendar-json.googleapis.com
     For the optional booking profile, enable the Google Calendar API.

  5. {CONSOLE}/auth/branding
     Fill in the app name and your email.

  6. {CONSOLE}/auth/audience
     Set publishing status to PRODUCTION, not Testing.

     This matters: in Testing, Google expires the refresh token after 7 days
     and your deployment silently stops syncing. The default profile requests
     only drive.file. The optional booking profile also requests sensitive
     Calendar scopes and can show Google's unverified-app warning while the
     OAuth app is used privately or is awaiting verification.

  7. {CONSOLE}/auth/clients
     Create client → Desktop app → download the JSON.

  8. Save that file to:
     {settings.google_client_secret_file}
"""

AUTH_TIMEOUT_SECONDS = 15 * 60


def _fail(message: str) -> int:
    print(f"\n✗ {message}")
    return 1


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("default", "booking"), default="default")
    parser.add_argument("--expected-email", default="")
    return parser.parse_args()


def _meet_url(event: dict) -> str:
    if event.get("hangoutLink"):
        return str(event["hangoutLink"])
    for entry in event.get("conferenceData", {}).get("entryPoints", []):
        if entry.get("entryPointType") == "video" and entry.get("uri"):
            return str(entry["uri"])
    return ""


def _verify_calendar_event_and_meet(
    calendar,
    calendar_id: str,
    *,
    attempts: int = 12,
    poll_seconds: float = 0.5,
) -> dict:
    """Create a private attendee-free test event, prove Meet, then delete it."""
    now = datetime.now(UTC).replace(microsecond=0)
    start = now + timedelta(minutes=10)
    end = start + timedelta(minutes=5)
    event_id = ""
    event = {}
    try:
        event = (
            calendar.events()
            .insert(
                calendarId=calendar_id,
                conferenceDataVersion=1,
                sendUpdates="none",
                fields="id,hangoutLink,conferenceData",
                body={
                    "summary": "Formcraft — setup check",
                    "description": "Temporary event used to verify native booking.",
                    "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                    "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
                    "transparency": "transparent",
                    "visibility": "private",
                    "guestsCanModify": False,
                    "guestsCanInviteOthers": False,
                    "conferenceData": {
                        "createRequest": {
                            "requestId": f"formcraft-setup-{uuid4().hex}",
                            "conferenceSolutionKey": {"type": "hangoutsMeet"},
                        }
                    },
                },
            )
            .execute(num_retries=3)
        )
        event_id = str(event.get("id", ""))
        if not event_id:
            raise RuntimeError("Google created no Calendar event ID.")

        for attempt in range(attempts):
            if _meet_url(event):
                return event
            status = (
                event.get("conferenceData", {})
                .get("createRequest", {})
                .get("status", {})
                .get("statusCode")
            )
            if status == "failure":
                raise RuntimeError("Google reported that Meet creation failed.")
            if attempt + 1 < attempts:
                time.sleep(poll_seconds)
                event = (
                    calendar.events()
                    .get(
                        calendarId=calendar_id,
                        eventId=event_id,
                        fields="id,hangoutLink,conferenceData",
                    )
                    .execute(num_retries=3)
                )
        raise RuntimeError("Google did not finish creating the Meet link in time.")
    finally:
        if event_id:
            calendar.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendUpdates="none",
            ).execute(num_retries=3)


def _client_config_from_default_token() -> dict | None:
    payload = token_payload("default")
    if not payload or not payload.get("client_id") or not payload.get("client_secret"):
        return None
    return {
        "installed": {
            "client_id": payload["client_id"],
            "client_secret": payload["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": payload.get(
                "token_uri", "https://oauth2.googleapis.com/token"
            ),
            "redirect_uris": ["http://localhost"],
        }
    }


def main() -> int:  # noqa: C901 - a linear setup script reads better flat
    args = _arguments()
    profile = args.profile
    scopes = scopes_for_profile(profile)
    token_file = (
        settings.google_booking_token_file
        if profile == "booking"
        else settings.google_token_file
    )
    token_env = (
        "FORMCRAFT_GOOGLE_TOKEN_JSON_BOOKING"
        if profile == "booking"
        else "FORMCRAFT_GOOGLE_TOKEN_JSON"
    )
    expected_email = args.expected_email.strip().casefold()
    secret_file = settings.google_client_secret_file

    if secret_file.exists():
        try:
            client = json.loads(secret_file.read_text())
        except json.JSONDecodeError as exc:
            return _fail(f"{secret_file} is not valid JSON: {exc}")
    else:
        client = _client_config_from_default_token()
        if client is None:
            print(CHECKLIST)
            answer = (
                input("Open the console in your browser now? [Y/n] ").strip().lower()
            )
            if answer in ("", "y", "yes"):
                webbrowser.open(f"{CONSOLE}/projectcreate")
            print(f"\nRe-run this script once {secret_file} exists.")
            return 1
        print("Using the existing Formcraft OAuth client without changing its token.")

    if "installed" not in client and "web" not in client:
        return _fail(
            f"{secret_file} does not look like an OAuth client file. "
            "Create credentials of type 'Desktop app' and download that JSON."
        )
    if "web" in client:
        print(
            "! This is a Web application client. A Desktop app client is easier "
            "here — if the browser step fails, create one of those instead.\n"
        )

    print(f"Authorizing Google profile: {profile}")
    print(f"Requesting scope: {', '.join(scopes)}")
    if expected_email:
        print(f"Required Google account: {expected_email}")
    print("A browser window will open. Sign in and click Allow.\n")

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(client, scopes)
    try:
        creds = flow.run_local_server(
            port=0,
            prompt="consent",
            open_browser=True,
            timeout_seconds=AUTH_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return _fail(
            "Authorisation timed out after 15 minutes. Run this command again, "
            "then finish the Google sign-in and Allow screen before it expires."
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(f"Authorisation failed: {exc}")

    if not creds.refresh_token:
        return _fail(
            "Google returned no refresh token. Revoke the app at "
            "https://myaccount.google.com/permissions and run this again."
        )

    # --- prove it actually works -------------------------------------------
    print("\nVerifying by creating a real spreadsheet…")
    from googleapiclient.discovery import build

    try:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        user = (
            drive.about()
            .get(fields="user(emailAddress,displayName)")
            .execute(num_retries=3)["user"]
        )
        account_email = str(user.get("emailAddress", "")).casefold()
        if expected_email and account_email != expected_email:
            return _fail(
                f"Google authorized {account_email or 'an unknown account'}, not "
                f"{expected_email}. No token was saved or deployed."
            )
        print(f"✓ Authorized as {account_email}")

        sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        created = (
            sheets.spreadsheets()
            .create(
                body={"properties": {"title": "Formcraft — setup check"}},
                fields="spreadsheetId,spreadsheetUrl",
            )
            .execute(num_retries=3)
        )
        sheet_id = created["spreadsheetId"]
        sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1:B1",
            valueInputOption="RAW",
            body={"values": [["Formcraft", "works"]]},
        ).execute(num_retries=3)
        print(f"✓ Created and wrote to {created['spreadsheetUrl']}")

        with contextlib.suppress(Exception):
            drive.files().delete(fileId=sheet_id).execute(num_retries=3)
            print("✓ Test spreadsheet deleted")

    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Authorisation succeeded but the Sheet check failed: {exc}\n"
            "  Enable both the Google Drive API and Google Sheets API "
            "(steps 2 and 3 above), then run this command again."
        )

    if profile == "booking":
        try:
            calendar = build(
                "calendar", "v3", credentials=creds, cache_discovery=False
            )
            now = datetime.now(UTC)
            calendar.freebusy().query(
                body={
                    "timeMin": now.isoformat(),
                    "timeMax": (now + timedelta(minutes=1)).isoformat(),
                    "items": [{"id": settings.google_calendar_id}],
                }
            ).execute(num_retries=3)
            print("✓ Google Calendar availability access verified")
            event = _verify_calendar_event_and_meet(
                calendar, settings.google_calendar_id
            )
            print(f"✓ Google Calendar event + Meet verified ({_meet_url(event)})")
            print("✓ Temporary Calendar event deleted; no attendee was invited")
        except Exception as exc:  # noqa: BLE001
            return _fail(
                f"Authorisation succeeded but the Calendar/Meet check failed: {exc}\n"
                f"  Enable the Google Calendar API at "
                f"{CONSOLE}/apis/library/calendar-json.googleapis.com (step 4), "
                "then run this command again. No credential was saved or deployed."
            )

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())
    token_file.chmod(0o600)
    print(f"✓ Token saved to {token_file}")

    print("Local setup is done. Set FORMCRAFT_GOOGLE_ENABLED=1 in .env.")
    print(f"For Vercel, copy the contents of {token_file} into {token_env}.")
    print("Treat this file as a password. Never commit it or paste it into logs.")
    print("Set the Vercel variable only for your intended environment, then redeploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
