# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""FastAPI application: admin pages, JSON API, and the public form renderer."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlsplit

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.responses import Response as RawResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from . import auth, calendar_booking, db, export, media, repository, sheets
from .config import settings, validate_hosted_settings
from .models import QUESTION_TYPES, FormIn, validate_answer

log = logging.getLogger("formcraft")

templates = Jinja2Templates(directory=str(settings.web_dir / "templates"))

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _meeting_provider(meeting_url: str) -> str:
    """Identify supported booking embeds while leaving ordinary links usable."""
    host = (urlsplit(meeting_url).hostname or "").casefold()
    if host == "calendly.com" or host.endswith(".calendly.com"):
        return "calendly"
    if host in {"calendar.app.google", "calendar.google.com"}:
        return "google_calendar"
    return "link" if meeting_url else ""


def _booking_provider(form: dict[str, Any]) -> str:
    if form.get("booking_mode") == "google_api":
        return "google_api"
    return _meeting_provider(form.get("meeting_url", ""))


def create_app() -> FastAPI:
    validate_hosted_settings()
    db.init_db()
    # openapi_url=None matters as much as docs_url: the schema names the app and
    # enumerates every route, which is exactly what a visitor should not get.
    app = FastAPI(
        title="Formcraft", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.mount(
        "/static",
        StaticFiles(directory=str(settings.web_dir / "static")),
        name="static",
    )
    _register_public(app)
    if settings.is_hosted_role:
        from . import hosted

        hosted.register(
            app, _render, lambda form_id: _sheet_after_save(form_id, create=True)
        )
    if settings.is_admin_role:
        _register_admin(app)
    return app


def _is_local(request: Request) -> bool:
    """True when the client is on this machine.

    Deliberately reads the socket peer, never X-Forwarded-For — a header a
    remote caller controls must not be able to unlock the admin surface.
    """
    if settings.is_hosted_role or settings.admin_allow_remote:
        return True
    client = request.client
    return client is not None and client.host in LOOPBACK


def _require_local(request: Request) -> None:
    """Admin surface is invisible off-machine — 404, not 403, so it leaks nothing."""
    if not _is_local(request):
        raise HTTPException(status_code=404, detail="Not found")


def _render(request: Request, template: str, **context: Any) -> HTMLResponse:
    """Every template gets the brand and the image-slot registry for free."""
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "brand_name": settings.brand_name,
            "hosted": settings.is_hosted_role,
            "owner_name": settings.owner_name,
            "owner_role": settings.owner_role,
            **media.context(),
            **context,
        },
    )


def _register_admin(app: FastAPI) -> None:  # noqa: C901 - route table, flat by nature
    admin = Depends(auth.require_admin)
    local = Depends(_require_local)

    # ---------------------------------------------------------------- auth

    @app.get("/login", response_class=HTMLResponse, dependencies=[local])
    def login_page(request: Request) -> Response:
        if auth.read_session(request):
            return RedirectResponse("/", status_code=302)
        return _render(request, "login.html", error=None)

    @app.post("/login", response_class=HTMLResponse, dependencies=[local])
    async def login_submit(request: Request) -> Response:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))

        if settings.is_hosted_role:
            from .hosted import login_attempt_allowed

            if not login_attempt_allowed():
                return JSONResponse(
                    {"detail": "Too many sign-in attempts. Try again in five minutes."},
                    status_code=429, headers={"Retry-After": "300"},
                )
        if auth.throttled():
            return _render(
                request,
                "login.html",
                error="Too many attempts. Wait a few minutes and try again.",
            )

        if not auth.verify_credentials(username, password):
            auth.record_failure()
            return _render(
                request, "login.html", error="Incorrect username or password."
            )

        auth.clear_failures()
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(
            auth.SESSION_COOKIE,
            auth.issue_session(),
            max_age=auth.SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=settings.secure_cookies,
        )
        return response

    @app.post("/logout", dependencies=[local])
    def logout() -> Response:
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie(auth.SESSION_COOKIE)
        return response

    # ------------------------------------------------------------- admin UI

    @app.get("/", response_class=HTMLResponse, dependencies=[local])
    def dashboard(request: Request) -> Response:
        if not auth.read_session(request):
            return RedirectResponse("/login", status_code=302)
        return _render(
            request,
            "dashboard.html",
            forms=repository.list_forms(),
            base_url=settings.base_url,
            google=sheets.status_summary(),
        )

    @app.get("/admin/new", response_class=HTMLResponse, dependencies=[local])
    def builder_new(request: Request) -> Response:
        if not auth.read_session(request):
            return RedirectResponse("/login", status_code=302)
        return _render(
            request,
            "builder.html",
            form=None,
            form_data=None,
            question_types=QUESTION_TYPES,
            base_url=settings.base_url,
        )

    @app.get("/admin/media", response_class=HTMLResponse, dependencies=[local])
    def media_gallery(request: Request) -> Response:
        if not auth.read_session(request):
            return RedirectResponse("/login", status_code=302)
        filled = sum(1 for name in media.SLOTS if media.resolve(name))
        return _render(request, "media.html", filled=filled)

    @app.get("/admin/media/briefs.txt", dependencies=[local, admin])
    def media_briefs() -> RawResponse:
        return _file_response(
            media.briefs().encode("utf-8"), "text/plain; charset=utf-8",
            "formcraft-image-briefs.txt",
        )

    @app.get("/admin/{form_id}", response_class=HTMLResponse, dependencies=[local])
    def builder_edit(request: Request, form_id: str) -> Response:
        if not auth.read_session(request):
            return RedirectResponse("/login", status_code=302)
        form = repository.get_form(form_id=form_id)
        if form is None:
            raise HTTPException(status_code=404, detail="Form not found")
        return _render(
            request,
            "builder.html",
            form=form,
            form_data=_editor_payload(form),
            question_types=QUESTION_TYPES,
            base_url=settings.base_url,
        )

    @app.get(
        "/admin/{form_id}/responses",
        response_class=HTMLResponse,
        dependencies=[local],
    )
    def responses_page(request: Request, form_id: str) -> Response:
        if not auth.read_session(request):
            return RedirectResponse("/login", status_code=302)
        form = repository.get_form(form_id=form_id)
        if form is None:
            raise HTTPException(status_code=404, detail="Form not found")
        return _render(
            request,
            "responses.html",
            form=form,
            responses=repository.list_responses(form_id),
            base_url=settings.base_url,
            google=sheets.status_summary(form),
        )

    # --------------------------------------------------------------- export

    @app.get("/admin/{form_id}/export.csv", dependencies=[local, admin])
    def export_csv(form_id: str) -> RawResponse:
        form, questions, responses = _export_data(form_id)
        return _file_response(
            export.to_csv(questions, responses),
            "text/csv; charset=utf-8",
            export.filename(form["title"], "csv"),
        )

    @app.get("/admin/{form_id}/export.xlsx", dependencies=[local, admin])
    def export_xlsx(form_id: str) -> RawResponse:
        form, questions, responses = _export_data(form_id)
        return _file_response(
            export.to_xlsx(form["title"], questions, responses),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            export.filename(form["title"], "xlsx"),
        )

    @app.post("/api/forms/{form_id}/export-key", dependencies=[local, admin])
    def api_export_key(form_id: str, rotate: bool = True) -> JSONResponse:
        if not rotate:
            repository.clear_export_key(form_id)
            return JSONResponse({"key": None})
        key = repository.rotate_export_key(form_id)
        return JSONResponse(
            {"key": key, "url": f"{settings.base_url}/feed/{form_id}.csv?key={key}"}
        )

    @app.get("/feed/{form_id}.csv", dependencies=[local])
    def export_feed(form_id: str, key: str = "") -> RawResponse:
        """Refreshable CSV for Excel / Numbers / Sheets.

        Registered on the admin instance only, and gated on `local`, so the
        key never crosses the network — it is only ever fetched over loopback
        by a spreadsheet running on this same machine.
        """
        form = repository.form_by_export_key(form_id, key)
        if form is None:
            raise HTTPException(status_code=404, detail="Not found")
        questions = repository.all_questions(form_id)
        responses = repository.list_responses(form_id, limit=10000)
        return RawResponse(
            content=export.to_csv(questions, responses),
            media_type="text/csv; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    # ------------------------------------------------------------- JSON API

    @app.post("/api/forms", dependencies=[local, admin])
    async def api_create(request: Request) -> JSONResponse:
        payload = await _read_form(request)
        try:
            form_id = repository.create_form(
                payload, sheet_profile=settings.google_default_profile
            )
        except Exception as exc:  # converted into a safe, useful API response
            _raise_form_write_error(exc, action="created")
        sheet = _sheet_after_save(form_id, create=True)
        return JSONResponse(
            {"id": form_id, "sheet": sheet}, status_code=status.HTTP_201_CREATED
        )

    @app.put("/api/forms/{form_id}", dependencies=[local, admin])
    async def api_update(form_id: str, request: Request) -> JSONResponse:
        payload = await _read_form(request)
        try:
            repository.update_form(form_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Form not found") from exc
        except Exception as exc:  # converted into a safe, useful API response
            _raise_form_write_error(exc, action="updated")
        return JSONResponse(
            {"id": form_id, "sheet": _sheet_after_save(form_id, create=False)}
        )

    @app.delete("/api/forms/{form_id}", dependencies=[local, admin])
    def api_delete(form_id: str) -> JSONResponse:
        repository.delete_form(form_id)
        return JSONResponse({"deleted": form_id})

    @app.post("/api/forms/{form_id}/sheet", dependencies=[local, admin])
    def api_create_sheet(form_id: str) -> JSONResponse:
        return JSONResponse(_attach_sheet(form_id, force=True))

    @app.post("/api/sync", dependencies=[local, admin])
    def api_sync() -> JSONResponse:
        return JSONResponse(retry_pending())


def _register_public(app: FastAPI) -> None:

    @app.get("/f/{public_ref}", response_class=HTMLResponse)
    def public_form(request: Request, public_ref: str) -> Response:
        form = repository.get_form(public_ref=public_ref)
        if form is None:
            raise HTTPException(status_code=404, detail="Form not found")
        # Drafts are visible only to a logged-in admin on the local instance.
        preview_ok = settings.is_admin_role and auth.read_session(request)
        if not form["is_published"] and not preview_ok:
            raise HTTPException(status_code=404, detail="Form not found")
        response = _render(
            request,
            "form.html",
            form=form,
            meeting_provider=_booking_provider(form),
            preview=not form["is_published"],
        )
        # An unguessable URL is not private if a crawler indexes it.
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        if form["is_published"]:
            # The published HTML contains no visitor data. Let Vercel's edge
            # reuse it so opening a form does not wake Python and cross the
            # network to Postgres for every visitor. Browsers still revalidate,
            # and the short edge TTL keeps form edits quick to appear.
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
            response.headers["Vercel-CDN-Cache-Control"] = (
                "public, s-maxage=300, stale-while-revalidate=60"
            )
        else:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/f/{public_ref}")
    async def submit(public_ref: str, request: Request) -> JSONResponse:
        form = repository.get_form(public_ref=public_ref)
        if form is None or not form["is_published"]:
            raise HTTPException(status_code=404, detail="Form not found")

        body = await request.json()
        answers: dict[str, Any] = {}
        errors: dict[str, str] = {}

        for question in form["questions"]:
            value, error = validate_answer(question, body.get(question["id"]))
            if error:
                errors[question["id"]] = error
            else:
                answers[question["id"]] = value

        if errors:
            return JSONResponse({"errors": errors}, status_code=422)

        response_id = _save_form_response(form, answers)
        booking_token = ""
        if form.get("booking_mode") == "google_api":
            booking_token = repository.issue_booking_token(form["id"], response_id)

        return JSONResponse(
            {
                "ok": True,
                "id": response_id,
                "message": form["confirm_msg"],
                "booking_token": booking_token,
            }
        )

    @app.get("/f/{public_ref}/responses/{response_id}/booking/slots")
    def native_booking_slots(
        request: Request,
        public_ref: str,
        response_id: str,
        timezone: str = "",
    ) -> JSONResponse:
        form = _native_booking_access(
            public_ref,
            response_id,
            request.headers.get("x-booking-token", ""),
        )
        response = repository.get_response(form["id"], response_id)
        if response is None:
            raise HTTPException(status_code=404, detail="Response not found")
        identity = _booking_identity(form, response)
        if not _booking_attempt_allowed(
            request, form["id"], response_id, identity["attendee_email"]
        ):
            raise HTTPException(
                status_code=429,
                detail="Too many recent booking requests. Please try again later.",
            )
        if not repository.consume_booking_slot_check(form["id"], response_id):
            raise HTTPException(
                status_code=429,
                detail="Available times were refreshed too often. Try again shortly.",
            )
        viewer_timezone, timezone_source = calendar_booking.best_viewer_timezone(
            unquote(request.headers.get("x-vercel-ip-timezone", "")), timezone
        )
        booking_config = calendar_booking.normalized_config(form.get("booking_config"))
        candidates = calendar_booking.candidate_slots(booking_config)
        try:
            if candidates:
                _release_expired_booking_orphans(
                    form, candidates[0][0], candidates[-1][1]
                )
            calendar_profile, calendar_id = _booking_calendar_key(form)
            local_busy = (
                repository.booking_intervals(
                    calendar_profile,
                    calendar_id,
                    candidates[0][0],
                    candidates[-1][1],
                )
                if candidates
                else []
            )
            available = calendar_booking.available_slots(form, local_busy)
        except Exception as exc:  # noqa: BLE001 - safe public error
            log.warning("calendar availability failed for %s: %s", form["id"], exc)
            raise HTTPException(
                status_code=503,
                detail="Meeting times are temporarily unavailable. Please retry.",
            ) from exc
        return JSONResponse(
            {
                "slots": [
                    {"start": start.isoformat(), "end": end.isoformat()}
                    for start, end in available
                ],
                "viewer_timezone": viewer_timezone,
                "timezone_source": timezone_source,
                "owner_timezone": booking_config["timezone"],
                "schedule": {
                    "timezone": booking_config["timezone"],
                    "weekdays": booking_config["weekdays"],
                    "first_start": booking_config["first_start"],
                    "last_start": booking_config["last_start"],
                    "duration_minutes": booking_config["duration_minutes"],
                },
            }
        )

    @app.post("/f/{public_ref}/responses/{response_id}/booking/confirm")
    async def confirm_native_booking(
        request: Request, public_ref: str, response_id: str
    ) -> JSONResponse:
        form = _native_booking_access(
            public_ref,
            response_id,
            request.headers.get("x-booking-token", ""),
        )
        body = await request.json()
        try:
            requested = datetime.fromisoformat(
                str(body.get("start", "")).replace("Z", "+00:00")
            ).astimezone(UTC)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="Choose a valid meeting time."
            ) from exc

        existing = repository.get_booking(response_id)
        if existing and existing["status"] in {"event_created", "confirmed"}:
            with repository.booking_claim(existing["id"]) as claimed:
                if not claimed:
                    raise _booking_in_progress()
                current = repository.get_booking(response_id)
                if current is None or current["status"] not in {
                    "event_created",
                    "confirmed",
                }:
                    raise HTTPException(
                        status_code=409,
                        detail="The meeting status changed. Please retry.",
                    )
                return _confirmed_booking_response(form, response_id, current)

        candidates = dict(calendar_booking.candidate_slots(form.get("booking_config")))
        end_at = candidates.get(requested)
        if end_at is None:
            raise HTTPException(
                status_code=422,
                detail="That meeting time is outside the current booking window.",
            )

        viewer_timezone, _ = calendar_booking.best_viewer_timezone(
            unquote(request.headers.get("x-vercel-ip-timezone", "")),
            str(body.get("timezone", "")),
        )
        if existing and existing["start_at"].astimezone(UTC) != requested:
            raise HTTPException(
                status_code=409,
                detail="This response already has a different booking in progress.",
            )

        response = repository.get_response(form["id"], response_id)
        if response is None:
            raise HTTPException(status_code=404, detail="Response not found")
        identity = _booking_identity(form, response)
        if not _booking_attempt_allowed(
            request, form["id"], response_id, identity["attendee_email"]
        ):
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many recent booking requests from this email or "
                    "network. Please try again later."
                ),
            )

        profile = form["sheet_profile"]
        calendar_profile, calendar_id = _booking_calendar_key(form)
        booking = existing or repository.reserve_booking(
            form["id"],
            response_id,
            requested,
            end_at,
            viewer_timezone,
            calendar_profile,
            calendar_id,
        )
        if booking is None:
            # Another request from this same browser may have inserted the row
            # after our first read. Recover that row instead of treating an
            # idempotent retry as a competing visitor.
            raced = repository.get_booking(response_id)
            if raced and raced["start_at"].astimezone(UTC) == requested:
                booking = raced
            else:
                booking = _claim_expired_booking_slot(
                    form,
                    response_id,
                    requested,
                    end_at,
                    viewer_timezone,
                )
        if booking is None:
            raise _booking_slot_taken()

        with repository.booking_claim(booking["id"]) as claimed:
            if not claimed:
                raise _booking_in_progress()

            # Never act on a stale in-memory row. A lease claim may have
            # replaced it while this request was waiting for the advisory lock.
            current = repository.get_booking(response_id)
            if current is None or current["id"] != booking["id"]:
                raise HTTPException(
                    status_code=409,
                    detail="That reservation expired. Choose the meeting time again.",
                )
            booking = current
            if booking["status"] in {"event_created", "confirmed"}:
                return _confirmed_booking_response(form, response_id, booking)
            if booking["start_at"].astimezone(UTC) != requested:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This response already has a different booking in progress."
                    ),
                )

            try:
                recovered = calendar_booking.get_event(
                    profile, booking["calendar_event_id"]
                )
                if recovered is None:
                    busy = calendar_booking.busy_intervals(profile, requested, end_at)
                    if calendar_booking.overlaps(requested, end_at, busy):
                        repository.delete_pending_booking(booking["id"])
                        raise _booking_slot_taken()
                booking_config = calendar_booking.normalized_config(
                    form.get("booking_config")
                )
                event = calendar_booking.create_or_recover_event(
                    profile=profile,
                    booking=booking,
                    response_id=response_id,
                    attendee_name=identity["attendee_name"],
                    business_name=identity["business_name"],
                    owner_timezone=booking_config["timezone"],
                    event_title=str(
                        booking_config.get("event_title")
                        or "Business meeting"
                    ),
                    event_description=str(
                        booking_config.get("event_description")
                        or "Business consultation booked through Formcraft."
                    ),
                )
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001 - response remains retryable
                log.warning("calendar booking failed for %s: %s", response_id, exc)
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Google Calendar could not confirm the meeting yet. "
                        "Your form response is safe; please retry."
                    ),
                ) from exc

            details = calendar_booking.event_details(event)
            staged = repository.record_booking_event(
                booking["id"], details["event_url"], details["meet_url"]
            )
            if staged is None:
                raise HTTPException(
                    status_code=503, detail="Booking could not be saved."
                )
            return _confirmed_booking_response(
                form, response_id, staged, event=event
            )

    @app.post("/f/{public_ref}/responses/{response_id}/booking")
    async def save_booking(
        public_ref: str, response_id: str, request: Request
    ) -> JSONResponse:
        form = repository.get_form(public_ref=public_ref)
        if (
            form is None
            or not form["is_published"]
            or _booking_provider(form) != "calendly"
        ):
            raise HTTPException(status_code=404, detail="Form not found")

        body = await request.json()
        booking_answers: dict[str, Any] = {}
        for question in form["questions"]:
            field = question["config"].get("calendly_field")
            if not field:
                continue
            value, error = validate_answer(question, body.get(field))
            if error:
                return JSONResponse({"detail": error}, status_code=422)
            booking_answers[question["id"]] = value

        if not booking_answers or body.get("status") != "Booked":
            return JSONResponse({"detail": "Invalid booking data."}, status_code=422)

        saved = repository.update_response(form["id"], response_id, booking_answers)
        if saved is None:
            raise HTTPException(status_code=404, detail="Response not found")

        sheet_synced = _sync_response_to_sheet(form, saved)

        return JSONResponse(
            {
                "ok": True,
                "sheet_connected": bool(form.get("sheet_id")),
                "sheet_synced": sheet_synced,
            }
        )

    @app.exception_handler(404)
    async def form_not_found(request: Request, exc: Exception) -> Response:
        """A branded page for mistyped form links.

        Scoped to /f/ deliberately: everywhere else a bare 404 is the point,
        since a styled page would confirm what is running at that address.
        """
        if not request.url.path.startswith("/f/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        response = _render(request, "not_found.html")
        response.status_code = 404
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        # The public instance says only that it is up. Role, database state and
        # integration status are operator detail, not visitor-facing.
        if settings.is_hosted_role or not settings.is_admin_role:
            return JSONResponse({"ok": True})
        return JSONResponse(
            {
                "ok": True,
                "role": settings.role,
                "database": db.ping(),
                "google": sheets.status_summary(),
            }
        )


def _validation_detail(exc: Exception) -> str:
    if isinstance(exc, ValidationError) and exc.errors():
        return str(exc.errors()[0].get("msg", "Check the form and try again."))
    return "Check the form and try again."


def _save_form_response(form: dict[str, Any], answers: dict[str, Any]) -> str:
    """Persist first, then attempt Sheet delivery without risking the response."""
    waits_for_booking = form.get("booking_mode") == "google_api"
    response_id = repository.save_response(
        form["id"], answers, sync_ready=not waits_for_booking
    )
    if not waits_for_booking and sheets.enabled() and form.get("sheet_id"):
        response = repository.get_response(form["id"], response_id)
        if response is not None:
            _sync_response_to_sheet(form, response)
    return response_id


def _native_booking_access(
    public_ref: str, response_id: str, booking_token: str
) -> dict[str, Any]:
    form = repository.get_form(public_ref=public_ref)
    if (
        form is None
        or not form["is_published"]
        or form.get("booking_mode") != "google_api"
        or not repository.booking_token_valid(form["id"], response_id, booking_token)
    ):
        raise HTTPException(status_code=404, detail="Booking not found")
    return form


def _booking_identity(form: dict[str, Any], response: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for question in form["questions"]:
        semantic = question["config"].get("booking_field")
        if semantic in {"attendee_name", "attendee_email", "business_name"}:
            values[semantic] = str(response["payload"].get(question["id"], "")).strip()
    if not values.get("attendee_name") or not values.get("attendee_email"):
        raise HTTPException(
            status_code=422,
            detail="The response needs a name and email before booking.",
        )
    values.setdefault("business_name", "")
    return values


def _booking_attempt_allowed(
    request: Request, form_id: str, response_id: str, attendee_email: str
) -> bool:
    """Apply DB-backed public invitation limits without retaining raw identity."""
    forwarded = request.headers.get("x-vercel-forwarded-for", "").split(",", 1)[0]
    client_ip = (
        forwarded.strip()
        or request.headers.get("x-real-ip", "").strip()
        or (request.client.host if request.client else "unknown")
    )
    secret_value = (
        settings.booking_hmac_secret
        or settings.secret_key
    )
    if not secret_value and settings.serverless:
        raise HTTPException(
            status_code=503,
            detail="Booking security is not configured.",
        )
    # A deterministic local-only value keeps greenfield development easy. It
    # is explicitly forbidden on deployed/serverless instances above.
    secret = (secret_value or "formcraft-local-booking-rate-limit").encode()

    def digest(kind: str, value: str) -> str:
        message = f"{kind}:{form_id}:{value.strip().casefold()}".encode()
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    return repository.register_booking_attempt(
        form_id,
        response_id,
        digest("client", client_ip),
        digest("email", attendee_email),
    )


def _booking_answers(
    form: dict[str, Any], booking: dict[str, Any], details: dict[str, str]
) -> dict[str, Any]:
    confirmed_at = booking.get("confirmed_at") or datetime.now(UTC)
    values = {
        "status": "Booked",
        "starts_at": booking["start_at"].astimezone(UTC).isoformat(),
        "ends_at": booking["end_at"].astimezone(UTC).isoformat(),
        "visitor_timezone": booking["visitor_timezone"],
        "event_id": details["event_id"],
        "event_url": details["event_url"],
        "meet_url": details["meet_url"],
        "confirmed_at": confirmed_at.astimezone(UTC).isoformat(),
    }
    answers: dict[str, Any] = {}
    for question in form["questions"]:
        field = question["config"].get("booking_field")
        if field in values and question["config"].get("hidden"):
            answers[question["id"]] = values[field]
    return answers


def _booking_slot_taken() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="That time was just taken. Choose another available time.",
    )


def _booking_in_progress() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="This meeting is already being confirmed. Please retry shortly.",
    )


def _booking_calendar_key(form: dict[str, Any]) -> tuple[str, str]:
    return form["sheet_profile"], settings.google_calendar_id


def _release_expired_booking_orphans(
    form: dict[str, Any], starts_after: datetime, starts_before: datetime
) -> None:
    """Remove only verified, attendee-free Formcraft events after their lease."""
    profile, calendar_id = _booking_calendar_key(form)
    stale_rows = repository.expired_unconfirmed_bookings(
        profile, calendar_id, starts_after, starts_before
    )
    for stale in stale_rows:
        with repository.booking_claim(stale["id"]) as claimed:
            if not claimed:
                continue
            current = repository.get_booking(stale["response_id"])
            if (
                current is None
                or current["id"] != stale["id"]
                or not repository.pending_booking_expired(current)
            ):
                continue
            event = calendar_booking.get_event(profile, current["calendar_event_id"])
            if event is not None:
                if not calendar_booking.is_owned_attendee_free_event(event, current):
                    continue
                calendar_booking.delete_event(profile, current["calendar_event_id"])
                if calendar_booking.get_event(profile, current["calendar_event_id"]):
                    continue
            repository.delete_expired_unconfirmed_booking(current["id"])


def _claim_expired_booking_slot(
    form: dict[str, Any],
    response_id: str,
    start_at: datetime,
    end_at: datetime,
    visitor_timezone: str,
) -> dict[str, Any] | None:
    """Safely reuse an abandoned DB reservation only when Calendar is empty."""
    profile, calendar_id = _booking_calendar_key(form)
    stale = repository.get_booking_for_slot(profile, calendar_id, start_at)
    if not repository.pending_booking_expired(stale):
        return None

    # This claim protects against both a concurrent retry by the original
    # visitor and two new visitors attempting to recycle the same stale row.
    with repository.booking_claim(stale["id"]) as claimed:
        if not claimed:
            return None
        current = repository.get_booking_for_slot(profile, calendar_id, start_at)
        if (
            current is None
            or current["id"] != stale["id"]
            or not repository.pending_booking_expired(current)
        ):
            return None
        try:
            calendar_event = calendar_booking.get_event(
                profile, current["calendar_event_id"]
            )
        except Exception as exc:  # noqa: BLE001 - do not reclaim on uncertainty
            log.warning("stale booking check failed for %s: %s", current["id"], exc)
            raise HTTPException(
                status_code=503,
                detail="Meeting times are temporarily unavailable. Please retry.",
            ) from exc
        if calendar_event is not None:
            if not calendar_booking.is_owned_attendee_free_event(
                calendar_event, current
            ):
                return None
            calendar_booking.delete_event(profile, current["calendar_event_id"])
            if calendar_booking.get_event(profile, current["calendar_event_id"]):
                return None
        return repository.claim_expired_pending_booking(
            current["id"],
            form["id"],
            response_id,
            start_at,
            end_at,
            visitor_timezone,
            profile,
            calendar_id,
        )


def _confirmed_booking_response(
    form: dict[str, Any],
    response_id: str,
    booking: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
) -> JSONResponse:
    """Finish invitation first, then publish Booked metadata and Sheet state."""
    response = repository.get_response(form["id"], response_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Response not found")

    if booking.get("status") != "confirmed" or not booking.get("invitation_sent"):
        identity = _booking_identity(form, response)
        try:
            event = event or calendar_booking.get_event(
                form["sheet_profile"], booking["calendar_event_id"]
            )
            if event is None:
                raise calendar_booking.CalendarUnavailable(
                    "The Calendar event could not be recovered."
                )
            details = calendar_booking.event_details(event)
            if booking.get("status") == "pending":
                booking = repository.record_booking_event(
                    booking["id"], details["event_url"], details["meet_url"]
                )
                if booking is None:
                    raise RuntimeError("The Calendar event state could not be saved.")
            event = calendar_booking.invite_attendee(
                form["sheet_profile"],
                event,
                identity["attendee_name"],
                identity["attendee_email"],
            )
            invited = repository.mark_booking_invited(booking["id"])
            if invited is None:
                raise RuntimeError("The invitation state could not be saved.")
            booking = invited
        except Exception as exc:  # noqa: BLE001 - event phase remains retryable
            log.warning(
                "booking invitation reconciliation failed for %s: %s",
                response_id,
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "Google has not confirmed the attendee invitation yet. "
                    "Your form response is safe; please retry."
                ),
            ) from exc

    # Only a durably confirmed invitation can make the response or Sheet say
    # Booked. This keeps business data truthful during uncertain Google calls.
    details = {
        "event_id": booking.get("calendar_event_id") or "",
        "event_url": booking.get("calendar_event_url") or "",
        "meet_url": booking.get("meet_url") or "",
    }
    booking_answers = _booking_answers(form, booking, details)
    # The Calendar event is the source for fields that never reached the
    # response after a crash. Preserve already-saved values: for example, a
    # recovered provider event ID can legitimately differ from the requested
    # deterministic ID stored on the reservation.
    missing_answers = {
        question_id: value
        for question_id, value in booking_answers.items()
        if value and not response["payload"].get(question_id)
    }
    if not response.get("sync_ready") or missing_answers:
        response = repository.update_response(
            form["id"], response_id, missing_answers, sync_ready=True
        )
        if response is None:
            raise HTTPException(status_code=404, detail="Response not found")

    sheet_synced = bool(response.get("synced"))
    if form.get("sheet_id") and not sheet_synced:
        sheet_synced = _sync_response_to_sheet(form, response)
    return JSONResponse(
        _confirmed_booking_payload(
            booking,
            response,
            sheet_connected=bool(form.get("sheet_id")),
            sheet_synced=sheet_synced,
        )
    )


def _sync_response_to_sheet(form: dict[str, Any], response: dict[str, Any]) -> bool:
    if not sheets.enabled() or not form.get("sheet_id"):
        return False
    with repository.response_sync_claim(response["id"]):
        current = repository.get_response(form["id"], response["id"])
        if current is None:
            return False
        if current.get("synced"):
            return True
        try:
            sheets.append_response(
                form,
                current["id"],
                current["payload"],
                current["submitted_at"],
            )
        except Exception as exc:  # noqa: BLE001 - durable DB state remains retryable
            sync_error = f"{type(exc).__name__}: {exc}"
            log.warning(
                "response sheet sync failed for %s: %s", current["id"], sync_error
            )
            repository.mark_synced(current["id"], sync_error)
            return False
        repository.mark_synced(current["id"])
        return True


def _confirmed_booking_payload(
    booking: dict[str, Any],
    response: dict[str, Any] | None,
    *,
    sheet_connected: bool,
    sheet_synced: bool | None = None,
) -> dict[str, Any]:
    if sheet_synced is None:
        sheet_synced = bool(response and response.get("synced"))
    return {
        "ok": True,
        "status": "confirmed",
        "start": booking["start_at"].astimezone(UTC).isoformat(),
        "end": booking["end_at"].astimezone(UTC).isoformat(),
        "viewer_timezone": booking["visitor_timezone"],
        "meet_url": booking.get("meet_url") or "",
        "event_url": booking.get("calendar_event_url") or "",
        "invitation_sent": bool(booking.get("invitation_sent")),
        "sheet_connected": sheet_connected,
        "sheet_synced": sheet_synced,
    }


def _export_data(form_id: str) -> tuple[dict[str, Any], list, list]:
    form = repository.get_form(form_id=form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    return (
        form,
        repository.all_questions(form_id),
        repository.list_responses(form_id, limit=10000),
    )


def _file_response(body: bytes, media_type: str, name: str) -> RawResponse:
    return RawResponse(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


async def _read_form(request: Request) -> FormIn:
    try:
        raw = await request.json()
    except Exception as exc:  # Starlette may surface several decoder exceptions
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_json",
                "message": "The form data could not be read. Refresh and try again.",
            },
        ) from exc
    return _parse_form(raw)


def _parse_form(raw: Any) -> FormIn:
    try:
        return FormIn.model_validate(raw)
    except ValidationError as exc:
        errors = []
        for item in exc.errors(include_url=False, include_context=False):
            message = item["msg"].removeprefix("Value error, ")
            errors.append(
                {
                    "field": ".".join(str(part) for part in item["loc"]) or "form",
                    "message": message,
                }
            )
        raise HTTPException(
            status_code=422,
            detail={
                "code": "validation_error",
                "message": "Please fix the form before saving.",
                "errors": errors,
            },
        ) from exc


def _raise_form_write_error(exc: Exception, action: str) -> None:
    if isinstance(exc, repository.DuplicateFormTitleError):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_form_name",
                "message": (
                    "A form with this name already exists. Choose a different name."
                ),
                "field": "title",
            },
        ) from exc
    if isinstance(exc, repository.InvalidFormReferenceError):
        log.warning("rejected invalid form structure reference: %s", exc)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_structure",
                "message": (
                    "This form changed unexpectedly. Refresh it before saving again."
                ),
            },
        ) from exc
    if isinstance(exc, (psycopg.OperationalError, db.DatabaseUnavailable)):
        log.exception("database unavailable while form was being %s", action)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "database_unavailable",
                "message": (
                    "The database is temporarily unavailable, so the form was not "
                    f"{action}. "
                    "Wait a moment and try again."
                ),
            },
        ) from exc
    if isinstance(exc, psycopg.IntegrityError):
        log.exception("database rejected form while it was being %s", action)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "save_conflict",
                "message": "The form conflicts with saved data. Refresh and try again.",
            },
        ) from exc
    log.exception("unexpected error while form was being %s", action)
    raise HTTPException(
        status_code=500,
        detail={
            "code": "save_failed",
            "message": (
                f"The form could not be {action}. "
                "Your changes are still on this page."
            ),
        },
    ) from exc


def _editor_payload(form: dict[str, Any]) -> dict[str, Any]:
    """Only JSON-safe fields needed by builder.js.

    Database rows also contain timezone-aware datetimes and Sheet metadata.
    Passing the whole row through Jinja's ``tojson`` makes an otherwise
    successful form creation crash on the redirect to its editor.
    """
    return {
        "title": form["title"],
        "description": form["description"],
        "display_mode": form["display_mode"],
        "accent": form["accent"],
        "is_published": form["is_published"],
        "confirm_msg": form["confirm_msg"],
        "meeting_url": form["meeting_url"],
        "meeting_label": form["meeting_label"],
        "sections": [
            {
                "id": section["id"],
                "title": section["title"],
                "description": section["description"],
                "questions": [
                    {
                        "id": question["id"],
                        "type": question["type"],
                        "label": question["label"],
                        "help_text": question["help_text"],
                        "placeholder": question["placeholder"],
                        "required": question["required"],
                        "options": question["options"],
                        "config": question["config"],
                    }
                    for question in section["questions"]
                ],
            }
            for section in form["sections"]
        ],
    }


def _sheet_after_save(form_id: str, create: bool) -> dict[str, Any]:
    """A Sheet outage must never turn a successful form save into a 500."""
    try:
        return _attach_sheet(form_id) if create else _sync_sheet(form_id)
    except Exception:  # noqa: BLE001 - form durability takes priority
        log.exception("sheet follow-up failed after form %s was saved", form_id)
        key = "created" if create else "updated"
        return {
            key: False,
            "status": "error",
            "detail": (
                "The form is saved. Google Sheets could not be reached; "
                "retry sync from Responses."
            ),
        }


def _attach_sheet(
    form_id: str, force: bool = False, include_archived: bool = True
) -> dict[str, Any]:
    """Create the spreadsheet for a form. Never fatal — the form still works."""
    if not sheets.enabled():
        return {"created": False, "detail": "Google sync is off."}

    form = repository.get_form(form_id=form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    if form.get("sheet_id") and not force:
        return {"created": False, "url": form["sheet_url"], "detail": "Already linked."}

    form["sheet_questions"] = (
        repository.all_questions(form_id) if include_archived else form["questions"]
    )

    try:
        sheet_id, sheet_url = sheets.create_spreadsheet(form)
    except Exception as exc:  # noqa: BLE001
        technical_detail = f"{type(exc).__name__}: {exc}"
        detail = _sheet_failure_message(exc, "created")
        # A forced replacement may fail after a form already has a live Sheet.
        # Preserve that link; only record the latest error.
        repository.set_sheet_error(form_id, detail)
        log.warning("sheet creation failed for %s: %s", form_id, technical_detail)
        return {"created": False, "status": "error", "detail": detail}

    try:
        repository.set_sheet(form_id, sheet_id, sheet_url)
    except Exception:  # the Google file exists; never hide its URL
        log.exception("sheet %s was created but could not be linked", sheet_id)
        return {
            "created": True,
            "linked": False,
            "status": "error",
            "url": sheet_url,
            "detail": (
                "The Google Sheet was created, but the app could not save its link. "
                "Keep this Sheet URL and retry linking after the database recovers."
            ),
        }
    backfill = retry_pending(form_id=form_id)
    return {
        "created": True,
        "linked": True,
        "status": "ok",
        "url": sheet_url,
        "backfilled": backfill["synced"],
        "detail": "Spreadsheet created and existing responses synchronized.",
    }


def _sync_sheet(form_id: str) -> dict[str, Any]:
    """Keep a linked spreadsheet aligned with a saved form without blocking saves."""
    if not sheets.enabled():
        return {"updated": False, "detail": "Google sync is off."}

    form = repository.get_form(form_id=form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    if not form.get("sheet_id"):
        return {"updated": False, "detail": "No spreadsheet is linked."}

    form["sheet_questions"] = repository.all_questions(form_id)
    try:
        sheets.sync_spreadsheet(form)
    except Exception as exc:  # noqa: BLE001 - the form edit is already durable
        technical_detail = f"{type(exc).__name__}: {exc}"
        detail = _sheet_failure_message(exc, "updated")
        repository.set_sheet_error(form_id, detail)
        log.warning("sheet update failed for %s: %s", form_id, technical_detail)
        return {"updated": False, "status": "error", "detail": detail}

    repository.set_sheet_error(form_id)
    return {
        "updated": True,
        "status": "ok",
        "url": form["sheet_url"],
        "detail": "Sheet updated.",
    }


def _sheet_failure_message(exc: Exception, action: str) -> str:
    """Turn provider/network failures into safe, actionable admin copy."""
    detail = str(exc).casefold()
    saved = "The form is saved. "
    if "invalid_grant" in detail or "token has been expired" in detail:
        return saved + "Google authorization expired. Reconnect Google and retry sync."
    if "403" in detail or "permission" in detail or "forbidden" in detail:
        return saved + "Google denied access. Check the account permissions and retry."
    if "404" in detail or "not found" in detail:
        return (
            saved + "The linked Google Sheet was not found. It may have been deleted."
        )
    if "429" in detail or "quota" in detail or "rate limit" in detail:
        return (
            saved
            + "Google's request limit was reached. Wait briefly and retry sync."
        )
    if "timeout" in detail or "timed out" in detail or "connection" in detail:
        return (
            saved
            + "Google Sheets could not be reached. Check the connection and retry."
        )
    return saved + f"The Google Sheet could not be {action}. Retry sync from Responses."


def retry_pending(form_id: str = "") -> dict[str, Any]:
    """Push any responses that failed to reach their spreadsheet."""
    if not sheets.enabled():
        return {"attempted": 0, "synced": 0, "detail": "Google sync is off."}

    pending = repository.pending_sync(form_id=form_id)
    synced = 0
    last_error = ""
    for item in pending:
        form = repository.get_form(form_id=item["form_id"])
        if form is None:
            continue
        form["sheet_questions"] = repository.all_questions(item["form_id"])
        if _sync_response_to_sheet(form, item):
            synced += 1
        else:
            refreshed = repository.get_response(item["form_id"], item["id"])
            last_error = str((refreshed or {}).get("sync_error") or last_error)

    return {
        "attempted": len(pending),
        "synced": synced,
        "detail": last_error or "Done.",
    }


app = create_app()
