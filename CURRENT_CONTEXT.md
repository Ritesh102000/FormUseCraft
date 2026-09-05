<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Current FormUseCraft Context

Updated: 2026-09-05

## Authorized scope

The owner approved a hosted owner dashboard plus independent public form links,
Google Sheets/Calendar connection in the browser, easy Vercel deployment, and
publication to https://github.com/Ritesh102000/FormUseCraft.git. This task does
not authorize connecting the owner's live Vercel or Google accounts or creating
a production database. Do not touch the separate sibling checkout.

The owner permits free personal/commercial use with a mandatory visible small
“Powered by catapultaiwork” link to https://catapultaiwork.com on every form.
Every project file must explain that requirement. LICENSE is a custom
source-available attribution license, not MIT or OSI-approved. Source owners
can technically modify the code; the license governs attribution retention.

## Current implementation

- `hosted` mode: one environment-configured owner account, browser dashboard,
  public forms, and Google integrations in the same Vercel app/domain.
- Vercel defaults to hosted mode and fails closed for incomplete/insecure owner
  setup. Optional `public` mode still omits admin routes. `admin` stays local.
- OAuth Web client per installation; verified identity, PKCE, one-time expiring
  state bound to the owner session, and encrypted database token storage.
- Regular forms create Google Sheets when connected. The meeting wizard saves
  a draft first, then attempts a Sheet attachment. Failed delivery is retryable.
- Meeting wizard: timezone, weekdays, start range, duration, notice, and window;
  schedule edits from the builder. The deployment selects one owned calendar.
- Database-first submissions, stable question IDs, historical exports, and the
  existing booking/event/invitation recovery flow are preserved.
- Owner writes require the canonical Origin, sessions use secure cookies, owner
  pages are not cached, login attempts have a shared database budget, and hosted
  mode blocks the old localhost-only CSV bearer feed.

One owner per installation, not multi-tenancy. No public signup, shared
workspaces, payments, file uploads, arbitrary existing-Sheet picker, per-form
calendar picker, cancellation UI, or background retry worker. General public
form CAPTCHA/spam limits and versioned database migrations remain future work.

## Release boundary

Current files have no inherited credentials or bundled art with unverified
redistribution rights. The original local baseline Git history still contains
removed assets and old customer-specific code. Do not publish that history.
Publish only a fresh export of current files into the named empty GitHub repo.
Keep the original working checkout and sibling repository intact.

## Verification

Run all checks in AGENTS.md plus scripts/check_release.py. Tests use disposable
PostgreSQL and mocked Google APIs. Hosted entrypoint tests exercise a fresh
interpreter and secure-cookie login. Local UI verification does not certify a
live Google OAuth grant, Google Meet capability, Vercel account, or domain.

## Local verification before initial publication

128 automated tests passed on disposable PostgreSQL, including hosted owner
login, Origin rejection, OAuth state/session binding and replay prevention,
encrypted grants, account-switch protection, meeting drafts, and public links.
Ruff, both JavaScript syntax checks, dependency consistency, JSON parsing,
whitespace, and the 78-file release scan passed. The local browser rendered
the owner login; its POST was blocked by the in-app browser. Direct HTTP and
automated HTTPS login checks succeeded. Live Google and Vercel setup was not run.

A fresh independent publishing checkout is prepared for the authorized GitHub
destination, keeping the original baseline history out of the public repository.
