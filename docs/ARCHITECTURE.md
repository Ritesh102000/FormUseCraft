<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Current Architecture

## Runtime topology

The default Vercel `hosted` mode serves one installation owner and respondents:

```text
Owner browser -> login -> dashboard / integrations / exports
Respondents   -> /f/<unique-reference> -> published form / booking
                           |
                    PostgreSQL storage
                           |
             optional owner's Google Sheets / Calendar
```

Each deployment owns its database and Google connection. Hosted owner writes
require the configured canonical origin and a valid signed session, except login
which checks the configured credentials. Owner pages are not cached. The legacy
local-only bearer feed is unavailable over hosted mode.

OAuth Web-client settings come from environment variables. One-time, expiring
state in PostgreSQL binds consent to the owner's session; PKCE and verified
Google identity protect the callback. Tokens are encrypted in PostgreSQL using
the installation secret. Existing Sheets/bookings cannot silently move accounts.

Optional `admin` mode keeps its loopback boundary. `public` mode omits owner
routes and can share a database with a local admin. It uses local/env Google
profiles rather than the hosted encrypted connection. These are separate modes.

## Layers

| Layer | Files | Responsibility |
|---|---|---|
| Application | `src/formcraft/app.py` | HTTP routes and orchestration |
| Validation | `src/formcraft/models.py` | Forms, fields, and answers |
| Persistence | `src/formcraft/db.py`, `repository.py` | Schema and SQL |
| Authentication | `src/formcraft/auth.py` | Single-admin session |
| Sheets | `src/formcraft/sheets.py` | Spreadsheet lifecycle and sync |
| Booking | `src/formcraft/calendar_booking.py` | Availability, events, Meet |
| Export | `src/formcraft/export.py` | CSV and XLSX |
| Presentation | `web/templates`, `web/static` | Admin and visitor UI |

## Data model

- `google_connection`: one encrypted grant and verified account identity.
- `google_oauth_states`: expiring one-use session-bound authorization requests.
- `admin_login_limits`: shared sign-in attempt budget.
- `forms`: display, publication, public reference, meeting and Sheet settings.
- `sections`: ordered form groups.
- `questions`: ordered field definitions with JSON configuration and archival.
- `responses`: answer JSON plus Sheet and booking state.
- `bookings`: reservations and Google event/invitation state.
- `booking_attempts`: keyed digests for abuse controls.
- `sheet_columns`: permanent question-to-column mapping.

## Core flows

Submission:

```text
validate published form and answers
-> save response in PostgreSQL
-> attempt Google Sheets delivery
-> return confirmation and optional booking handoff
```

Native booking:

```text
saved response and scoped token
-> Calendar FreeBusy check
-> database reservation
-> deterministic Calendar event
-> Meet recovery and attendee invitation
-> booking and response update
-> Sheet row update
```

Database advisory locks, unique slot constraints, leases, deterministic event
IDs, and transition timestamps make booking retryable after partial failures.

## Main scale boundary

The current authorization model is appropriate only for one administrator.
Workspace ownership, scoped queries, versioned migrations, and tenant-isolation
tests must land before exposing multi-user signup. External provider calls are
synchronous and should move behind durable jobs/outbox processing as the system
grows.
