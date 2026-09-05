<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# FormUseCraft

Your own form builder, hosted on your own domain. Create forms, collect responses
in Google Sheets, and let people book meetings on your Google Calendar.
Provided by [catapultaiwork](https://catapultaiwork.com).

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FRitesh102000%2FFormUseCraft&project-name=formusecraft&repository-name=FormUseCraft&env=FORMCRAFT_DATABASE_URL%2CFORMCRAFT_ADMIN_PASSWORD%2CFORMCRAFT_SECRET_KEY&envDescription=Use+your+own+pooled+PostgreSQL+URL%2C+an+owner+password+of+at+least+12+characters%2C+and+a+unique+random+installation+secret+of+at+least+32+characters.+Google+is+connected+after+deployment.&envLink=https%3A%2F%2Fgithub.com%2FRitesh102000%2FFormUseCraft%2Fblob%2Fmain%2FDEPLOY.md)

**One deployment, two access levels:** a private owner dashboard and a unique
public link for every published form. Manage everything in your browser; the
hosted setup does not require a local builder or a token-upload script.

## Start using it

**Setting up with an AI assistant?** Give it [setup_llm.md](setup_llm.md) for the
complete deployment workflow, account setup, verification, and troubleshooting.

1. **Deploy your copy.** Click the button above. Supply your own pooled PostgreSQL
   URL, owner password, and unique installation secret. See [DEPLOY.md](DEPLOY.md).
2. **Sign in.** Open your deployed URL and sign in as `admin` with the password
   you configured. Only this installation's owner can manage forms.
3. **Connect Google, optionally.** Open **Google integrations**. Its checklist
   explains how to configure your own Google Web OAuth client once. Then click
   **Connect Google Sheets** or **Connect Sheets + Calendar** and authorize your
   account. [Google setup details](docs/GOOGLE_SHEETS.md).
4. **Create and share.** Create a form, add questions, save, and publish. Copy its
   `/f/…` link. Use **New meeting form** for a schedule backed by Google Calendar.

Each person deploys an independent copy with their own owner login, database,
and Google account. Respondents do not sign in or connect Google. No provider
account or shared database is bundled with the source.

## Owner dashboard and public links

| Owner dashboard | Public form links |
| --- | --- |
| Owner login required | No dashboard access |
| Create/edit/publish several forms | One opaque URL per form |
| View responses and CSV/XLSX exports | Submit answers to published forms |
| Connect the owner's Google account | Google authorization is not required |
| Configure meeting schedules | Pick an available time after submitting |
| Preview drafts | Draft links return 404 |

Both parts run in the same Vercel deployment. The dashboard is at `/`, login at
`/login`, and published forms at `/f/<unique-reference>`. You can add your own
custom domain. Possession of a form link allows submission; links can be forwarded.

## Features

- An owner AI builder using your own OpenAI key: describe a form or attach a PDF/image, refine its draft, and edit it in the dashboard.
- Optional per-form voice assistance: a globe invites visitors to answer questions aloud, confirm values, and review before submitting. Scheduling remains manual.
- A visual builder with sections, drafts, publishing, theme accent, and custom
  confirmation messages.
- Three layouts: one page, section by section, or one question at a time.
- Text, paragraph, email, number, date, time, dropdown, radio, checkbox, scale,
  and star-rating questions.
- PostgreSQL storage before any provider call; CSV and XLSX downloads.
- Optional app-created Google Sheet per form, historical columns, backfill,
  and a **Retry pending** action when delivery needs recovery.
- A Google meeting-form wizard with timezone, weekdays, first/last start time,
  duration, advance notice, and booking-window controls.
- Live calendar availability, slot reservations, Google Meet creation, and
  invitation recovery. The configured owner's primary calendar is the default.
- Mandatory small “Powered by catapultaiwork” link on public forms.

Google tokens are stored encrypted in your database using your installation
secret. OAuth callbacks are bound to the owner's login session and used once.
Hosted owner writes require the correct origin; owner pages are not cached.
Login attempts have a database-backed shared limit. The old local-only CSV feed
is unavailable in hosted mode; use authenticated downloads or Google Sheets.

## What you need

A Vercel account, a PostgreSQL database, and a strong owner password and installation
secret. Google integration additionally needs a Google account and your own Web
application OAuth client. The in-app checklist guides that one-time setup;
it cannot bypass Google's consent and client-configuration requirements.

Vercel [supports FastAPI](https://vercel.com/docs/frameworks/backend/fastapi).
Its [free Hobby plan](https://vercel.com/docs/limits/fair-use-guidelines) is for
personal, non-commercial use. Commercial software use is allowed by this project's
license, but choose a hosting plan that permits it. Hosting, databases, and domain
registration have separate usage limits and possible costs.

## Optional AI setup

Choose **Build with AI** in the owner dashboard. Supply a key for that request,
or configure `OPENAI_API_KEY` on the server. PDFs and images are accepted as
owner reference inputs. Generated forms start as private drafts.

For public voice, set `FORMCRAFT_AI_VOICE_ENABLED=1` with your environment key,
redeploy, then enable **AI voice assistance** on each form. Visitors explicitly
start it; it confirms field values and never submits, books meetings, or pays.
API usage is billed to the key owner and capped by shared app usage limits.
See [AI setup, privacy, limits, and troubleshooting](docs/AI.md). Payment
processing is not implemented.

## License and provider credit

Free personal and commercial use is allowed under [LICENSE](LICENSE), a **custom
source-available attribution license**. Every hosted form must retain the visible
“Powered by catapultaiwork” link to https://catapultaiwork.com. There is no builder
setting to remove it. People controlling the source can technically change it;
the license requires retention. This is not MIT or an OSI-approved license.

Your organization's name is configurable via `FORMCRAFT_BRAND_NAME`; it does
not replace the provider credit. Original art with unclear redistribution rights
is not bundled. See [IMAGES.md](IMAGES.md) for optional images you own.

## Limits

One owner per installation; no multi-tenant signup, shared workspaces, payments,
respondent file uploads, or arbitrary existing-spreadsheet picker. Sheets are created by
this app. Google connectivity is optional for regular data collection.

Native meeting responses are saved in PostgreSQL immediately; their Sheet rows
are deferred until booking is confirmed. Existing responses can be inspected
before booking. A redirect to an external booking provider alone does not prove
that a meeting was booked.

Provider calls run during requests. Failed Sheets delivery requires **Retry
pending**; there is no background worker. General form spam prevention/CAPTCHA,
versioned database migrations, cancellation/rescheduling UI, and per-form calendar
selection are not implemented. Back up your database before upgrades.

## Local development / optional split setup

Python 3.12 is required. Install [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
git clone https://github.com/Ritesh102000/FormUseCraft.git
cd FormUseCraft
uv sync --locked
uv run python scripts/dev.py
```

Open [the local app](http://127.0.0.1:8480), using `admin` / `devpassword` only
for this development instance. Embedded PostgreSQL lives in ignored `data/devdb`
on supported macOS/Linux platforms. It is not a Vercel database. The local demo
uses local-admin mode; hosted Google OAuth is verified using HTTPS/test fixtures.

For your own local PostgreSQL setup, copy `.env.example`, set the database URL,
run `scripts/set_password.py`, then `scripts/run.py`. Advanced split installations
may keep a local admin and deploy with `FORMCRAFT_ROLE=public`; that optional mode
continues to omit all admin routes. The default Vercel mode is now `hosted`.

## Contributing and verification

```bash
uv run ruff check .
uv run pytest -q
node --check web/static/builder.js
node --check web/static/form.js
node --check web/static/ai-builder.js
node --check web/static/voice.js
uv run python scripts/check_release.py
git diff --check
```

Tests use disposable PostgreSQL and mocked Google services. A custom
`FORMCRAFT_TEST_DATABASE_URL` must point to a disposable test database: tests
delete records. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[architecture](docs/ARCHITECTURE.md), and [release notes](OPEN_SOURCE_READINESS.md).
