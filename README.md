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
in your PostgreSQL database, optionally sync them to Google Sheets, and let
people book meetings on your Google Calendar.
Provided by [catapultaiwork](https://catapultaiwork.com).

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FRitesh102000%2FFormUseCraft&project-name=formusecraft&repository-name=FormUseCraft&env=FORMCRAFT_DATABASE_URL%2CFORMCRAFT_ADMIN_PASSWORD%2CFORMCRAFT_SECRET_KEY&envDescription=Use+your+own+pooled+PostgreSQL+URL%2C+an+owner+password+of+at+least+12+characters%2C+and+a+unique+random+installation+secret+of+at+least+32+characters.+Google+is+connected+after+deployment.&envLink=https%3A%2F%2Fgithub.com%2FRitesh102000%2FFormUseCraft%2Fblob%2Fmain%2FDEPLOY.md)

**One deployment, two access levels:** a private owner dashboard and a unique
public link for every published form. Manage everything in your browser; the
hosted setup does not require a local builder or a token-upload script.

[Watch the feature demos](#feature-demos) · [Deployment guide](DEPLOY.md) · [AI setup guide](setup_llm.md)

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
- A response browser with answer search, UTC date and Sheets-sync filters, numeric/text sorting, table/card views, pagination, and full answers including removed fields.
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

## Feature demos

Watch 17 short walkthroughs, each about 20–56 seconds. Every clip includes
voiceover and subtitles. Expand **Watch clip** under a feature to play it here.

The narration is AI-generated and the forms use synthetic data. Google setup,
meeting scheduling, voice flow, and deployment include explanations without a
live Google connection, booking, microphone session, or cloud deployment.

### 01. Overview and owner dashboard

See how one owner manages drafts, published forms, and response counts while visitors only receive a public form link.

<details>
<summary>Watch clip · 45 seconds</summary>

https://github.com/user-attachments/assets/daec197b-850b-42ae-bc29-69a08a64d3d4

</details>

### 02. Visual form builder

Add questions and sections, choose answer types, mark required fields, and adjust the form layout and confirmation message.

<details>
<summary>Watch clip · 26 seconds</summary>

https://github.com/user-attachments/assets/fecadd14-7c83-40b0-923a-b74192ecb394

</details>

### 03. Filling and submitting a form

Follow a visitor through a section-based project form, required-field checks, project details, and submission.

<details>
<summary>Watch clip · 49 seconds</summary>

https://github.com/user-attachments/assets/94fddf5a-7447-4302-b437-b97e18d23c34

</details>

### 04. PostgreSQL response storage

See why every response is saved in PostgreSQL first and how Google Sheets can be added as an optional copy.

<details>
<summary>Watch clip · 22 seconds</summary>

https://github.com/user-attachments/assets/e39eef58-a890-4274-b80c-bf54e332beb4

</details>

### 05. Form layouts and surveys

Compare one-page, section-based, and one-question-at-a-time layouts using signup and feedback forms.

<details>
<summary>Watch clip · 23 seconds</summary>

https://github.com/user-attachments/assets/73dc0446-898c-492f-9bb6-8a01f99294f7

</details>

### 06. AI form creation and draft review

Turn a description into an editable AI preview, review its questions, and save a private draft. PDF/image references and owner OpenAI keys are also explained.

<details>
<summary>Watch clip · 52 seconds</summary>

https://github.com/user-attachments/assets/f9452857-763b-47f3-995b-cb8b1a15f3ca

</details>

### 07. Publishing and sharing form links

Review your form, publish it, copy its unique link, and test the experience before sharing it.

<details>
<summary>Watch clip · 20 seconds</summary>

https://github.com/user-attachments/assets/bf9edf8f-ae06-40de-83b6-6d5c9dfa5574

</details>

### 08. Voice assistance and visitor controls

See per-form voice controls, visitor consent, and answer confirmation. Voice helps fill fields; visitors submit and choose meeting times themselves. The spoken workflow is explained without a live microphone session.

<details>
<summary>Watch clip · 56 seconds</summary>

https://github.com/user-attachments/assets/e5b67195-bd5e-4b34-9464-87b03861cf7c

</details>

### 09. Response search, filters and sorting

Find answers using text search, UTC date filters, numeric or text sorting, and adjustable page sizes.

<details>
<summary>Watch clip · 24 seconds</summary>

https://github.com/user-attachments/assets/33be5fd4-84ea-4b5a-92f0-b36143e5abc6

</details>

### 10. Table and card response views

Switch between tables and cards, open full answers, and keep the same filters as you browse.

<details>
<summary>Watch clip · 22 seconds</summary>

https://github.com/user-attachments/assets/a067f123-463c-4e49-9fd3-e390bfc0ed62

</details>

### 11. Full response details and exports

Read historical answers, including removed questions, and export CSV or Excel. Exports include up to the latest 10,000 responses independently of view filters.

<details>
<summary>Watch clip · 23 seconds</summary>

https://github.com/user-attachments/assets/cab200c7-1997-4072-96b3-ef6af6eff76e

</details>

### 12. Google Sheets and Calendar setup

Walk through the Google connection checklist, OAuth client setup, Sheets synchronization, and Calendar access. No live Google account is connected in this demo.

<details>
<summary>Watch clip · 24 seconds</summary>

https://github.com/user-attachments/assets/75ca3be9-78d2-4b5e-9619-4f2265ae3dc8

</details>

### 13. Meeting scheduling controls

Learn the timezone, weekdays, meeting duration, notice, and booking-window controls, plus how visitors select and confirm a time. This clip explains the flow without performing a booking.

<details>
<summary>Watch clip · 25 seconds</summary>

https://github.com/user-attachments/assets/62040c77-53fe-41d9-8d70-00eb873b7daa

</details>

### 14. Vercel deployment and environment setup

Follow the repository Deploy button and learn which PostgreSQL connection, owner password, and installation secret belong in Vercel. Deployment is explained without creating cloud resources.

<details>
<summary>Watch clip · 46 seconds</summary>

https://github.com/user-attachments/assets/b8f40522-a6a6-4b27-95b1-c47afc4b7931

</details>

### 15. Connecting your own domain

Learn where to configure your domain, DNS records, HTTPS base URL, and matching Google callback address.

<details>
<summary>Watch clip · 20 seconds</summary>

https://github.com/user-attachments/assets/6ddf8d12-cb62-4b1e-9348-c05c866ca515

</details>

### 16. Installation with setup_llm.md

Use setup_llm.md to guide a coding assistant through installation while keeping account sign-in, credentials, and Google consent under your control.

<details>
<summary>Watch clip · 21 seconds</summary>

https://github.com/user-attachments/assets/da123663-df5c-40aa-a1c9-6333704338fd

</details>

### 17. Optional features, costs and attribution

Understand optional Google and AI features, current product limits, provider costs, and the required catapultaiwork credit for personal or commercial software use.

<details>
<summary>Watch clip · 51 seconds</summary>

https://github.com/user-attachments/assets/07a4731c-6ee3-4988-b8ef-3e4e21952ae6

</details>

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

An environment OpenAI key makes voice available automatically after deployment.
Enable **AI voice assistance** on each intended form. Visitors explicitly
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
uses local-admin mode with the same browser Google setup and meeting wizard.
Open **Google integrations** and configure a Web OAuth client with the displayed
localhost callback. Its encrypted grant uses a stable ignored `data/dev_secret.key`.

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
