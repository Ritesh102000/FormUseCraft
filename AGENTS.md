<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Formcraft Open-Source Agent Guide

Read `CURRENT_CONTEXT.md` and `OPEN_SOURCE_READINESS.md` before changing this
repository.

## Repository boundary

- This repository is independent. It must not inherit Git
  history, remotes, deployment metadata, credentials, tokens, databases, or
  virtual environments from another Formcraft checkout.
- Do not modify the separate sibling `formcraft-next` repository.
- Do not add a remote, publish a repository, connect hosting, authorize an
  account, or create cloud resources unless the user explicitly identifies the
  action and destination.
- Never commit `.env`, OAuth credentials, provider tokens, client secrets,
  local databases, hosting metadata, caches, or generated runtime state.
- A repository name containing “opensource” is not a license. Do not add or
  change a software/content license without an explicit owner decision.

## Current baseline

Formcraft is a FastAPI application with Jinja templates, vanilla JavaScript,
PostgreSQL, optional Google Sheets synchronization, and optional meeting
booking. Hosted mode supports one environment-defined owner, a protected
browser dashboard, and an encrypted owner Google connection. Public-only and
local-admin modes remain available. Multi-user workspaces and payments are not
implemented. Publication to Ritesh102000/FormUseCraft is authorized by the owner.

## Code map

- `src/formcraft/app.py`: routes, rendering, submission and booking orchestration.
- `src/formcraft/models.py`: form schemas, field types, validation.
- `src/formcraft/db.py`: idempotent PostgreSQL schema initialization.
- `src/formcraft/repository.py`: persistence operations.
- `src/formcraft/auth.py`: single-owner authentication.
- `src/formcraft/hosted.py`: hosted boundary, integrations and meeting setup routes.
- `src/formcraft/google_connection.py`: encrypted OAuth storage and state.
- `src/formcraft/sheets.py`: Google Sheets lifecycle and retries.
- `src/formcraft/calendar_booking.py`: Google availability, events, and Meet.
- `src/formcraft/export.py`: CSV/XLSX exports.
- `src/formcraft/media.py`: static media registry.
- `web/templates`, `web/static`: admin and public interfaces.
- `tests`: unit, integration, booking, and reliability coverage.

## Commands

```bash
uv sync
cp .env.example .env
uv run python scripts/set_password.py
uv run python scripts/run.py
```

Disposable development mode:

```bash
uv run python scripts/dev.py
```

Required broad-change verification:

```bash
uv run ruff check .
uv run pytest -q
node --check web/static/builder.js
node --check web/static/form.js
git diff --check
```

## Invariants

- Persist responses before calling Google or any other provider.
- Preserve stable question IDs and archive removed questions so historical
  answers remain exportable.
- Keep public references opaque and keep admin routes absent in public mode.
- Enforce authorization at both route and data-access boundaries.
- Never trust browser-supplied workspace ownership, provider account IDs,
  prices, booking ownership, or payment success.
- Make callbacks, jobs, and webhooks authenticated and idempotent.
- Keep response, payment, and booking states separate.

## Public release requirements

- Preserve LICENSE's required visible “Powered by catapultaiwork” link to
  https://catapultaiwork.com on all public form and confirmation/booking views.
- Keep the provider/licensing notice in every project file. Use format-valid
  comments or metadata; do not break JSON, dependency files, or executable code.
- Software use is free for personal and commercial purposes subject to the
  custom attribution license. Do not relabel this as MIT or OSI-approved.
- Run `uv run python scripts/check_release.py` before release exports.
- Publish only a fresh current-file export; baseline Git history still contains
  removed assets. Do not rewrite history or select a remote without instruction.

## Product direction

The target hierarchy is:

```text
user -> workspace membership -> workspace -> form -> response
```

Google and payment connections belong to workspaces. Forms select their
connection and calendar. Form capabilities are independent: collect data,
optionally schedule a meeting, and optionally require payment.

Google profiles are now named `default` and `booking`; the customer-specific
lead-ingestion adapter was removed. This remains a single-owner application,
not a multi-tenant platform. Hosted mode requires HTTPS, canonical-origin
checks for owner writes, secure cookies, and a unique installation secret.
