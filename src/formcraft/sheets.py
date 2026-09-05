# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Google Sheets sync.

Every form gets its own spreadsheet, created when the form is created. Each
question owns a stable column index, so adding or removing questions later
never shifts existing data.

The whole module degrades to no-ops when FORMCRAFT_GOOGLE_ENABLED is off, so
the app is fully usable without any Google setup.
"""

from __future__ import annotations

import contextlib
import json
import threading
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .config import settings
from .db import readonly, transaction

# The default integration only needs access to files Formcraft created. Native
# Native booking uses the same credential for Sheets and Calendar, so its
# scope set must stay intact when the Sheets service refreshes and persists it.
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
CALENDAR_EVENTS_OWNED_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned"
CALENDAR_FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
SCOPES = [DRIVE_FILE_SCOPE]
BOOKING_SCOPES = [
    DRIVE_FILE_SCOPE,
    CALENDAR_EVENTS_OWNED_SCOPE,
    CALENDAR_FREEBUSY_SCOPE,
]

TIMESTAMP_HEADER = "Submitted at"
RESPONSE_ID_HEADER = "Formcraft response ID"
RESPONSE_ID_KEY = "__formcraft_response_id__"
MEETING_TIME_FIELDS = {"starts_at", "ends_at"}
MEETING_TIME_ZONE = ZoneInfo("Asia/Kolkata")

_lock = threading.Lock()
_services: dict[str, Any] = {}


class SheetsUnavailable(RuntimeError):
    """Raised when Sheets is enabled but not usable."""


def enabled() -> bool:
    if settings.uses_browser_google:
        from .google_connection import summary

        return summary()["connected"]
    return settings.google_enabled


def _form_profile(form: dict[str, Any] | None = None) -> str:
    """Return the credential alias stored on a form, never a secret."""
    return str((form or {}).get("sheet_profile") or settings.google_default_profile)


def _profile_file(profile: str):
    if profile == "default":
        return settings.google_token_file
    if profile == "booking":
        return settings.google_booking_token_file
    raise SheetsUnavailable(f"Unknown Google credential profile: {profile}")


def scopes_for_profile(profile: str) -> list[str]:
    """Return a copy so callers cannot mutate the profile's required scopes."""
    if profile == "default":
        return list(SCOPES)
    if profile == "booking":
        return list(BOOKING_SCOPES)
    raise SheetsUnavailable(f"Unknown Google credential profile: {profile}")


def _column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _load_service(profile: str = "default") -> Any:
    with _lock:
        if not settings.uses_browser_google and profile in _services:
            return _services[profile]

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        payload = _token_source(profile)
        if payload is None:
            raise SheetsUnavailable(
                f"Google profile {profile!r} has no credentials. Run "
                f"`uv run python scripts/google_setup.py --profile {profile}` "
                "locally, then deploy its profile-specific token."
            )

        # Do not load the booking token with the default-only scope list. If a
        # refresh is needed, to_json() below must preserve Calendar access too.
        creds = Credentials.from_authorized_user_info(
            payload,
            payload.get("scopes")
            if settings.uses_browser_google
            else scopes_for_profile(profile),
        )
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                if settings.uses_browser_google:
                    from .google_connection import persist_refresh

                    persist_refresh(payload, json.loads(creds.to_json()))
                # Read-only filesystem on serverless hosts: refreshing in memory
                # is enough, the refresh token itself does not change.
                token_file = _profile_file(profile)
                if (
                    not settings.uses_browser_google
                    and not settings.serverless
                    and token_file.exists()
                ):
                    with contextlib.suppress(OSError):
                        token_file.write_text(creds.to_json())
            else:
                raise SheetsUnavailable(
                    "Google credentials are invalid. Re-run "
                    f"scripts/google_setup.py --profile {profile}"
                )

        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        if not settings.uses_browser_google:
            _services[profile] = service
        return service


def _read_columns(form_id: str) -> dict[str, int]:
    with readonly() as conn:
        rows = conn.execute(
            "SELECT question_id, col_index FROM sheet_columns WHERE form_id = %s",
            (form_id,),
        ).fetchall()
    return {row["question_id"]: row["col_index"] for row in rows}


def _submitted_label(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="seconds")
    return str(value)


def _write_columns(form_id: str, mapping: dict[str, int]) -> None:
    with transaction() as conn:
        conn.cursor().executemany(
            """INSERT INTO sheet_columns (form_id, question_id, col_index)
               VALUES (%s,%s,%s)
               ON CONFLICT (form_id, question_id)
               DO UPDATE SET col_index = EXCLUDED.col_index""",
            [(form_id, qid, idx) for qid, idx in mapping.items()],
        )


def create_spreadsheet(form: dict[str, Any]) -> tuple[str, str]:
    """Create the spreadsheet for a form and write its header row."""
    if not enabled():
        return "", ""

    service = _load_service(_form_profile(form))
    questions = form.get("sheet_questions", form["questions"])

    created = (
        service.spreadsheets()
        .create(
            body={
                "properties": {"title": f"{form['title']} — responses"},
                "sheets": [{"properties": {"title": "Responses"}}],
            },
            fields="spreadsheetId,spreadsheetUrl,sheets.properties.sheetId",
        )
        .execute(num_retries=3)
    )
    sheet_id = created["spreadsheetId"]
    sheet_url = created["spreadsheetUrl"]

    header = [TIMESTAMP_HEADER] + [_header_label(q) for q in questions]
    mapping = {q["id"]: index + 1 for index, q in enumerate(questions)}
    response_id_index = len(header)
    mapping[RESPONSE_ID_KEY] = response_id_index
    header.append(RESPONSE_ID_HEADER)

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"Responses!A1:{_column_letter(len(header) - 1)}1",
        valueInputOption="RAW",
        body={"values": [header]},
    ).execute(num_retries=3)

    worksheet_id = (
        created.get("sheets", [{}])[0].get("properties", {}).get("sheetId", 0)
    )
    _format_sheet(
        service,
        sheet_id,
        worksheet_id,
        response_id_index,
        _meeting_time_indexes(questions, mapping),
    )
    _write_columns(form["id"], mapping)
    return sheet_id, sheet_url


def _format_sheet(
    service: Any,
    sheet_id: str,
    worksheet_id: int,
    response_id_index: int,
    meeting_time_indexes: list[int] | None = None,
) -> None:
    # Cosmetic only — never let this block sheet creation.
    with contextlib.suppress(Exception):
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": worksheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": worksheet_id, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": response_id_index,
                        "endIndex": response_id_index + 1,
                    },
                    "properties": {"hiddenByUser": True},
                    "fields": "hiddenByUser",
                }
            },
        ]
        requests.extend(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": index,
                        "endIndex": index + 1,
                    },
                    "properties": {"pixelSize": 250},
                    "fields": "pixelSize",
                }
            }
            for index in meeting_time_indexes or []
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": requests},
        ).execute(num_retries=3)


def _header_label(question: dict[str, Any]) -> str:
    suffix = " (removed)" if question.get("archived") else ""
    timezone_suffix = (
        " (IST)"
        if question.get("config", {}).get("booking_field") in MEETING_TIME_FIELDS
        else ""
    )
    return f"{question['label']}{timezone_suffix}{suffix}"


def _meeting_time_indexes(
    questions: list[dict[str, Any]], mapping: dict[str, int]
) -> list[int]:
    return [
        mapping[question["id"]]
        for question in questions
        if question.get("config", {}).get("booking_field") in MEETING_TIME_FIELDS
        and question["id"] in mapping
    ]


def _ensure_response_id_column(
    service: Any, form: dict[str, Any], mapping: dict[str, int]
) -> dict[str, int]:
    """Add the private idempotency column to spreadsheets from older releases."""
    if RESPONSE_ID_KEY in mapping:
        return mapping

    index = max(mapping.values(), default=0) + 1
    service.spreadsheets().values().update(
        spreadsheetId=form["sheet_id"],
        range=f"Responses!{_column_letter(index)}1",
        valueInputOption="RAW",
        body={"values": [[RESPONSE_ID_HEADER]]},
    ).execute(num_retries=3)
    mapping[RESPONSE_ID_KEY] = index
    _write_columns(form["id"], {RESPONSE_ID_KEY: index})

    with contextlib.suppress(Exception):
        service.spreadsheets().batchUpdate(
            spreadsheetId=form["sheet_id"],
            body={
                "requests": [
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": 0,
                                "dimension": "COLUMNS",
                                "startIndex": index,
                                "endIndex": index + 1,
                            },
                            "properties": {"hiddenByUser": True},
                            "fields": "hiddenByUser",
                        }
                    }
                ]
            },
        ).execute(num_retries=3)
    return mapping


def _ensure_columns(
    service: Any, form: dict[str, Any], questions: list[dict[str, Any]]
) -> dict[str, int]:
    """Assign columns to any question added after the sheet was created."""
    mapping = _read_columns(form["id"])
    mapping = _ensure_response_id_column(service, form, mapping)
    missing = [q for q in questions if q["id"] not in mapping]
    if not missing:
        return mapping

    next_index = max(mapping.values(), default=0) + 1
    additions: dict[str, int] = {}
    header_cells: list[str] = []
    for question in missing:
        additions[question["id"]] = next_index
        header_cells.append(_header_label(question))
        next_index += 1

    start = _column_letter(min(additions.values()))
    end = _column_letter(max(additions.values()))
    service.spreadsheets().values().update(
        spreadsheetId=form["sheet_id"],
        range=f"Responses!{start}1:{end}1",
        valueInputOption="RAW",
        body={"values": [header_cells]},
    ).execute(num_retries=3)

    mapping.update(additions)
    _write_columns(form["id"], additions)
    return mapping


def sync_spreadsheet(form: dict[str, Any]) -> None:
    """Synchronize a form title and question headers after an admin edit."""
    if not enabled() or not form.get("sheet_id"):
        return

    service = _load_service(_form_profile(form))
    questions = form.get("sheet_questions", form["questions"])
    mapping = _ensure_columns(service, form, questions)

    data = [
        {
            "range": "Responses!A1",
            "values": [[TIMESTAMP_HEADER]],
        },
        {
            "range": f"Responses!{_column_letter(mapping[RESPONSE_ID_KEY])}1",
            "values": [[RESPONSE_ID_HEADER]],
        },
    ]
    data.extend(
        {
            "range": f"Responses!{_column_letter(mapping[q['id']])}1",
            "values": [[_header_label(q)]],
        }
        for q in questions
    )
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=form["sheet_id"],
        body={"valueInputOption": "RAW", "data": data},
    ).execute(num_retries=3)
    service.spreadsheets().batchUpdate(
        spreadsheetId=form["sheet_id"],
        body={
            "requests": [
                {
                    "updateSpreadsheetProperties": {
                        "properties": {"title": f"{form['title']} — responses"},
                        "fields": "title",
                    }
                }
            ]
        },
    ).execute(num_retries=3)


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _meeting_time_label(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(MEETING_TIME_ZONE).strftime("%A, %d %b %Y, %H:%M IST")


def _format_answer(question: dict[str, Any], value: Any) -> str:
    if question.get("config", {}).get("booking_field") in MEETING_TIME_FIELDS:
        with contextlib.suppress(TypeError, ValueError):
            return _meeting_time_label(value)
    return _format_value(value)


def append_response(
    form: dict[str, Any],
    response_id: str,
    answers: dict[str, Any],
    submitted_at: Any = None,
) -> None:
    """Append or refresh one response row. Raises so the caller can retry."""
    if not enabled() or not form.get("sheet_id"):
        return

    service = _load_service(_form_profile(form))
    questions = form.get("sheet_questions", form["questions"])
    mapping = _ensure_columns(service, form, questions)

    response_id_index = mapping[RESPONSE_ID_KEY]
    response_id_column = _column_letter(response_id_index)
    existing = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=form["sheet_id"],
            range=f"Responses!{response_id_column}2:{response_id_column}",
        )
        .execute(num_retries=3)
        .get("values", [])
    )
    existing_row = next(
        (
            index + 2
            for index, row in enumerate(existing)
            if row and row[0] == response_id
        ),
        None,
    )

    width = max(mapping.values(), default=0) + 1
    row: list[str] = [""] * width
    row[0] = _submitted_label(
        submitted_at or datetime.now(UTC).isoformat(timespec="seconds")
    )
    row[response_id_index] = response_id
    questions_by_id = {question["id"]: question for question in questions}
    for question_id, value in answers.items():
        index = mapping.get(question_id)
        if index is not None and index < width:
            question = questions_by_id.get(question_id, {})
            row[index] = _format_answer(question, value)

    values = service.spreadsheets().values()
    if existing_row is not None:
        values.update(
            spreadsheetId=form["sheet_id"],
            range=(
                f"Responses!A{existing_row}:{_column_letter(width - 1)}{existing_row}"
            ),
            valueInputOption="RAW",
            body={"values": [row]},
        ).execute(num_retries=3)
    else:
        values.append(
            spreadsheetId=form["sheet_id"],
            range="Responses!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute(num_retries=3)


def status_summary(form: dict[str, Any] | None = None) -> dict[str, Any]:
    """Small health blob for the admin dashboard."""
    if not enabled():
        return {"enabled": False, "ready": False, "detail": "Google sync is off."}
    profile = _form_profile(form)
    try:
        _load_service(profile)
    except SheetsUnavailable as exc:
        return {"enabled": True, "ready": False, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        return {"enabled": True, "ready": False, "detail": detail}
    return {
        "enabled": True,
        "ready": True,
        "detail": f"Connected ({profile} Google profile).",
    }


def _token_source(profile: str = "default") -> dict[str, Any] | None:
    """Env var first (Vercel), then the local file (your Mac)."""
    if settings.uses_browser_google:
        from .google_connection import token_payload

        return token_payload()
    if profile == "default":
        token_json = settings.google_token_json
        token_file = settings.google_token_file
        env_name = "FORMCRAFT_GOOGLE_TOKEN_JSON"
    elif profile == "booking":
        token_json = settings.google_booking_token_json
        token_file = settings.google_booking_token_file
        env_name = "FORMCRAFT_GOOGLE_TOKEN_JSON_BOOKING"
    else:
        raise SheetsUnavailable(f"Unknown Google credential profile: {profile}")

    if token_json:
        try:
            return json.loads(token_json)
        except json.JSONDecodeError as exc:
            raise SheetsUnavailable(f"{env_name} is not valid JSON: {exc}") from exc
    if token_file.exists():
        try:
            return json.loads(token_file.read_text())
        except (OSError, json.JSONDecodeError):
            return None
    return None


token_payload = _token_source
