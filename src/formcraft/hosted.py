# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Owner-only browser setup for a single independently hosted installation."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import auth, calendar_booking, google_connection, repository
from .config import settings
from .db import transaction
from .follow_up_meeting import follow_up_meeting_form


def login_attempt_allowed() -> bool:
    """Shared global budget cannot be bypassed by spoofing proxy/IP headers."""
    with transaction() as conn:
        row = conn.execute(
            "INSERT INTO admin_login_limits (bucket, attempts, expires_at) "
            "VALUES ('owner', 1, now() + interval '5 minutes') "
            "ON CONFLICT (bucket) DO UPDATE SET "
            "attempts = CASE WHEN admin_login_limits.expires_at <= now() "
            "THEN 1 ELSE admin_login_limits.attempts + 1 END, "
            "expires_at = CASE WHEN admin_login_limits.expires_at <= now() "
            "THEN now() + interval '5 minutes' ELSE admin_login_limits.expires_at END "
            "RETURNING attempts"
        ).fetchone()
    return row["attempts"] <= 20


def register(app: FastAPI, render: Callable, attach_sheet: Callable) -> None:
    @app.middleware("http")
    async def owner_boundary(request: Request, call_next):
        # Public responses remain unauthenticated; all owner mutations require
        # the browser's exact configured Origin, including login/logout/OAuth start.
        owner_path = not (
            request.url.path.startswith("/f/")
            or request.url.path.startswith("/static/")
        )
        if (
            owner_path and request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("origin", "").rstrip("/") != settings.base_url
        ):
            return JSONResponse(
                {"detail": "Untrusted request origin."}, status_code=403
            )
        # Never make the formerly localhost-only bearer CSV feed internet-accessible.
        if request.url.path.startswith("/feed/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        response = await call_next(request)
        if owner_path:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @app.get("/admin/integrations")
    def integrations(request: Request):
        if not auth.read_session(request):
            return RedirectResponse("/login", status_code=302)
        return render(
            request,
            "integrations.html",
            connection=google_connection.summary(),
            configured=google_connection.configured(),
            callback_url=google_connection.redirect_uri(),
            result=request.query_params.get("result", ""),
        )

    @app.post("/oauth/google/start", dependencies=[Depends(auth.require_admin)])
    async def connect(request: Request):
        form = await request.form()
        try:
            url = google_connection.start(
                request.cookies[auth.SESSION_COOKIE],
                form.get("calendar") == "1",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(url, status_code=303)

    @app.get("/oauth/google/callback", dependencies=[Depends(auth.require_admin)])
    def callback(request: Request):
        try:
            state = google_connection.consume_state(
                request.query_params.get("state", ""),
                request.cookies[auth.SESSION_COOKIE],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if request.query_params.get("error") or not request.query_params.get("code"):
            return RedirectResponse(
                "/admin/integrations?result=cancelled", status_code=303
            )
        try:
            identity, payload = google_connection.exchange(
                request.query_params["code"], state
            )
            google_connection.save(identity, payload)
        except Exception:
            # Provider exceptions can contain codes/tokens; never render or log them.
            return RedirectResponse(
                "/admin/integrations?result=failed", status_code=303
            )
        return RedirectResponse("/admin/integrations?result=connected", status_code=303)

    @app.post("/oauth/google/disconnect", dependencies=[Depends(auth.require_admin)])
    def disconnect():
        google_connection.disconnect()
        return RedirectResponse(
            "/admin/integrations?result=disconnected", status_code=303
        )

    def meeting_page(request: Request, form=None, error=""):
        schedule = (form or {}).get("booking_config") or {
            "timezone": "UTC",
            "weekdays": [0, 1, 2, 3, 4],
            "first_start": "09:00",
            "last_start": "16:30",
            "duration_minutes": 30,
            "minimum_notice_hours": 2,
            "booking_window_days": 30,
        }
        return render(
            request,
            "meeting_setup.html",
            form=form,
            schedule=schedule,
            connection=google_connection.summary(),
            error=error,
        )

    @app.get("/admin/new-meeting", dependencies=[Depends(auth.require_admin)])
    def new_meeting(request: Request):
        return meeting_page(request)

    @app.get("/admin/{form_id}/booking", dependencies=[Depends(auth.require_admin)])
    def meeting_settings(request: Request, form_id: str):
        return meeting_page(request, _native_form(form_id))

    async def save_meeting(request: Request, form_id: str = ""):
        existing = _native_form(form_id) if form_id else None
        connection = google_connection.summary()
        if not connection["connected"] or not connection["calendar"]:
            raise HTTPException(
                status_code=400, detail="Connect Google Calendar first."
            )
        fields = await request.form()
        try:
            schedule = _schedule(fields)
            if existing:
                repository.set_booking_config(form_id, "google_api", schedule)
            else:
                title = str(fields.get("title", "")).strip()
                if not title or len(title) > 300:
                    raise ValueError("Add a form title of up to 300 characters.")
                payload = follow_up_meeting_form().model_copy(
                    update={
                        "title": title,
                        "description": "Enter your details and choose a meeting time.",
                        "is_published": False,
                        "meeting_label": "Choose a meeting time",
                    }
                )
                form_id = repository.create_form(
                    payload,
                    sheet_profile="booking",
                    booking_mode="google_api",
                    booking_config=schedule,
                )
        except (ValueError, TypeError) as exc:
            return meeting_page(request, existing, str(exc))
        if not existing:
            attach_sheet(form_id)  # Response/draft persistence always precedes Google.
        return RedirectResponse(f"/admin/{form_id}", status_code=303)

    @app.post("/admin/new-meeting", dependencies=[Depends(auth.require_admin)])
    async def create_meeting(request: Request):
        return await save_meeting(request)

    @app.post("/admin/{form_id}/booking", dependencies=[Depends(auth.require_admin)])
    async def update_meeting(request: Request, form_id: str):
        return await save_meeting(request, form_id)



def _native_form(form_id: str) -> dict:
    form = repository.get_form(form_id=form_id)
    if not form or form["booking_mode"] != "google_api":
        raise HTTPException(status_code=404, detail="Meeting form not found.")
    return form


def _schedule(fields) -> dict:
    duration = int(fields.get("duration_minutes", 30))
    notice = int(fields.get("minimum_notice_hours", 2))
    window = int(fields.get("booking_window_days", 30))
    weekdays = sorted(set(int(value) for value in fields.getlist("weekdays")))
    if duration not in {15, 30, 45, 60, 90, 120}:
        raise ValueError("Choose a supported meeting duration.")
    if not 0 <= notice <= 168 or not 1 <= window <= 60:
        raise ValueError("Notice must be 0–168 hours and window 1–60 days.")
    if not weekdays or not set(weekdays) <= set(range(7)):
        raise ValueError("Choose at least one valid weekday.")
    first = str(fields.get("first_start", "09:00"))
    last = str(fields.get("last_start", "16:30"))
    schedule = calendar_booking.normalized_config(
        {
            "timezone": str(fields.get("timezone", "UTC")),
            "weekdays": weekdays,
            "first_start": first,
            "last_start": last,
            "duration_minutes": duration,
            "slot_step_minutes": duration,
            "minimum_notice_hours": notice,
            "booking_window_days": window,
        }
    )
    if first > last:
        raise ValueError("Last start must be after the first start on the same day.")
    return schedule
