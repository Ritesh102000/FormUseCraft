<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Set up FormUseCraft with an LLM assistant

Give this file to your AI coding assistant to deploy your own FormUseCraft.
The normal setup is **one Vercel website with a private owner dashboard and
separate public links for each form**. You manage forms in your browser.
Respondents do not need an account. Google Sheets and Calendar are optional.

## Copy this prompt to your assistant

```text
Help me set up my own FormUseCraft using setup_llm.md in this repository:
https://github.com/Ritesh102000/FormUseCraft

Read the repository instructions and setup guides first. Inspect what is already
configured, ask only for missing decisions, and carry out the setup steps I have
authorized. Default to a hosted owner dashboard and public forms in one Vercel
deployment. Guide me through account login and Google consent when needed.

Keep credentials out of chat, Git, and logs. Preserve the catapultaiwork credit.
Verify each stage and finish with the URLs, checks that passed, and any steps I
still need to complete. Do not claim a live integration works based on mocks.
```

## 1. Establish the installation details

**Assistant:** read [AGENTS.md](AGENTS.md), [CURRENT_CONTEXT.md](CURRENT_CONTEXT.md),
[OPEN_SOURCE_READINESS.md](OPEN_SOURCE_READINESS.md), [DEPLOY.md](DEPLOY.md),
[the Google guide](docs/GOOGLE_SHEETS.md), and [LICENSE](LICENSE) before changing
anything. Check the actual configuration in `src/formcraft/config.py` and
`index.py` if documentation and runtime behavior differ.

Resolve these details from the conversation or ask for the missing ones together:

| Decision | What to establish |
| --- | --- |
| Setup type | Hosted website, or only a local demo? Use hosted for normal use. |
| GitHub and Vercel destination | The user's repository/fork and Vercel account/team/project; existing or new? |
| Database | Existing dedicated PostgreSQL database, or a provider the user authorizes setting up? |
| Domain | Start with a Vercel domain, or use a domain the user owns? |
| Integrations | Data collection only, Google Sheets, or Sheets plus Calendar/Meet? |
| Owner settings | Desired username and display name; enter the password privately. |
| Google account | Which account should own the Sheets and calendar, if enabled? |

Inspect existing resources before creating replacements. Do not reset a database,
overwrite another deployment, or alter unrelated repositories. The repository's
original publication authorization does not authorize a new user's cloud accounts.
Get an identified destination and authorization before creating cloud resources,
publishing a fork, connecting accounts, or changing DNS. Continue already authorized
work without repeated confirmation. The user completes account login, MFA, and
Google consent in their own browser.

Never ask for passwords, database URLs, client secrets, or refresh tokens in chat.
Have the user enter them directly into the provider's environment settings or an
ignored local environment file. Do not print environment values, put secrets in
shell arguments, or include them in screenshots, commits, or the final report.

## 2. Get an independent copy

For a local checkout, use an unused directory:

```bash
git clone https://github.com/Ritesh102000/FormUseCraft.git
cd FormUseCraft
git status --short
```

If a checkout already exists, inspect its remote and changes before proceeding.
For Vercel's Git integration, use the **Deploy with Vercel** button in
[README.md](README.md), or import the user's authorized copy at
[Vercel New Project](https://vercel.com/new). Do not push user-specific settings
to the upstream provider repository.

The application uses Python 3.12, FastAPI, PostgreSQL, and plain JavaScript.
There is no Node frontend build. Do not copy credentials, `.env`, `.venv`, token
files, local databases, or hosting metadata from another installation.

Preserve the provider notice in every project file using format-valid comments
or metadata. Every public form and confirmation/booking view must retain the
visible **Powered by catapultaiwork** link to https://catapultaiwork.com.
The license permits personal and commercial use with required attribution;
it is source-available, not MIT or OSI-approved. Do not add a hide-credit setting.

## 3. Prepare PostgreSQL and private configuration

Use a dedicated PostgreSQL database reachable from Vercel, with a **pooled TLS
connection string**. The application initializes its tables on startup; there
is no separate migration command. Use a fresh database for a fresh installation.
Back up an existing database before upgrades. Local `data/devdb` is not suitable
as a Vercel database.

Have the user generate and securely save a strong owner password and a different,
random installation secret in their password manager. Configure these server-side
variables in the Vercel project's **Production** environment:

| Variable | Value / purpose |
| --- | --- |
| `FORMCRAFT_DATABASE_URL` | Required pooled PostgreSQL URL with TLS. |
| `FORMCRAFT_ADMIN_PASSWORD` | Required unique owner password, at least 12 characters. |
| `FORMCRAFT_SECRET_KEY` | Required unique random secret, at least 32 characters; prefer 48+. |
| `FORMCRAFT_ROLE` | `hosted`; may be omitted on Vercel because its entrypoint defaults to hosted. |
| `FORMCRAFT_BASE_URL` | Canonical HTTPS origin, e.g. `https://forms.example.com`, with no path/query. See step 4. |
| `FORMCRAFT_ADMIN_USERNAME` | Optional; defaults to `admin`. |
| `FORMCRAFT_BRAND_NAME` | Optional organization name; does not replace the provider credit. |
| `FORMCRAFT_GOOGLE_CLIENT_ID` | Optional until Google setup; Web application OAuth client ID. |
| `FORMCRAFT_GOOGLE_CLIENT_SECRET` | Optional until Google setup; that client's secret. |
| `FORMCRAFT_GOOGLE_CALENDAR_ID` | Optional; defaults to `primary`. Must be owned by the connected account. |

`DATABASE_URL` is a fallback when `FORMCRAFT_DATABASE_URL` is absent; avoid
conflicting values. An Argon2 `FORMCRAFT_ADMIN_PASSWORD_HASH` can replace the
plaintext password variable and takes precedence when set. Hosted secure cookies
default to enabled; do not disable them. Do not copy the local-admin `.env.example`
wholesale into production.

Mark credentials sensitive where supported. Preserve a protected backup of
`FORMCRAFT_SECRET_KEY`: it signs sessions and encrypts stored Google grants.
Changing it invalidates sessions and requires reconnecting Google.

## 4. Deploy and check the owner dashboard

1. Import the repository root into the selected Vercel project. Use FastAPI
   detection and Python 3.12; do not configure a frontend build/output directory.
2. Set the Production variables from step 3 and deploy.
3. The app derives its HTTPS origin from `VERCEL_PROJECT_PRODUCTION_URL` if
   available. If unavailable or different from the intended domain, explicitly
   set `FORMCRAFT_BASE_URL` to the correct HTTPS origin and redeploy.
4. Open that canonical origin. Signed out, `/` should redirect to `/login`.
   Sign in privately using the configured owner username and password.
5. Confirm the dashboard loads and `/healthz` returns `{"ok":true}`. Health alone
   does not verify database writes or Google connectivity; complete step 8.

Redeploy after changing environment variables. Use the canonical domain for
owner actions: the app checks the exact request origin. Do not weaken origin
checks or cookie settings to work around a configuration mistake.

Disable unneeded previews, or isolate previews with a disposable database,
separate secrets, canonical URL, and test Google client/account. Do not expose
Production data or Google grants to preview code.

The software license permits commercial use, but hosting has its own terms.
[Vercel Hobby](https://vercel.com/docs/limits/fair-use-guidelines) is for personal,
non-commercial use. Check current hosting/database limits and choose an
appropriate plan; do not promise unlimited free commercial hosting.

## 5. Connect the owner's Google account, if requested

Skip this step for PostgreSQL-only data collection. Regular forms still work.

1. Open **Google integrations** at `/admin/integrations` and note the exact
   callback URL displayed by the application.
2. In the user's [Google Cloud project](https://console.cloud.google.com), enable
   **Google Drive API** and **Google Sheets API**. Enable **Google Calendar API**
   as well when meetings are requested.
3. Configure OAuth branding, audience, and contact information. Add the owner
   as a test user if the External app is in Testing. For these scopes, External
   Testing refresh tokens expire after seven days. Follow Google's publishing
   and verification requirements for continuing use; do not bypass consent.
4. Create an OAuth client of type **Web application**, not Desktop app. Add the
   exact authorized redirect URI, including HTTPS and the full callback path:

   ```text
   https://YOUR-CANONICAL-DOMAIN/oauth/google/callback
   ```

5. Have the user enter the client ID and secret into the Vercel Production
   variables listed above, then redeploy.
6. Sign in on the canonical domain. Click **Connect Google Sheets** or
   **Connect Sheets + Calendar**. The user selects their intended Google account
   and approves access. Complete the redirect in the same browser session.
7. Verify the integrations page reports the connection and requested capability.

Hosted mode stores the grant encrypted in PostgreSQL. Do not run the local
Desktop OAuth script or upload local token files for this flow. The app creates
a separate Sheet per form; an arbitrary existing-Sheet URL picker is not available.
Meet creation depends on the connected account/calendar supporting it.

When reconnecting an installation with linked forms, use the same Google account.
Disconnecting does not delete responses, Sheets, or Calendar events. See
[Google setup and recovery](docs/GOOGLE_SHEETS.md) for scope and consent details.

## 6. Create forms and share public links

**Data collection:** choose **New form**, add a section and questions, save,
publish, and copy its `/f/<unique-reference>` link. Each form gets a separate
reference. Drafts remain private to the owner. Anyone holding a published link
can submit it; the link is not respondent authentication.

When Google is connected, creating a regular form attempts to attach a Sheet.
For existing forms or failed attachments, open **Responses → Create Sheet**.
Check responses in the dashboard and authenticated CSV/XLSX exports. If delivery
fails, resolve the Google issue and use **Retry pending**. Responses are saved
in PostgreSQL before Google delivery; retries do not run in a background worker.

**Meetings:** connect Sheets + Calendar, then choose **New meeting form**. Set
an IANA timezone, weekdays, first and last start times, duration, advance notice,
and booking window. Review the defaults instead of assuming the user's timezone.
The last start time is a meeting start, not its end. The wizard creates a draft
with required name/email fields; preserve their booking bindings. Edit questions,
publish, and share. Use **Meeting settings** to adjust the schedule later.

Native meeting answers appear in PostgreSQL immediately; the Sheet row is sent
after booking confirmation. Confirm the actual Calendar event and Meet link;
a redirect alone is not proof of booking. Calendar selection is installation-wide.

## 7. Add a custom domain, if requested

Add the user's domain in **Vercel Settings → Domains**. Apply only the exact DNS
records Vercel provides and wait for domain/HTTPS verification. Do not guess DNS
values or replace unrelated records. Follow [Vercel's domain guide](https://vercel.com/docs/domains/working-with-domains/add-a-domain).

Set `FORMCRAFT_BASE_URL` to the new HTTPS origin, add its exact
`/oauth/google/callback` URL to Google's authorized redirect URIs, and redeploy.
Sign in and reconnect Google from that canonical domain. Newly generated share
links should use it. Check any previously shared links before removing old domains.

## 8. Verify the installation before handing it over

Use synthetic answers and a separate signed-out browser session. Get the user's
agreement to any real booking test and use consenting test participants, because
it can create an event and send invitations. Never run the test suite against a
production database: its fixtures delete records.

| Check | Required observation |
| --- | --- |
| Owner boundary | Signed-out `/` redirects to login; protected exports return 401; no owner data is exposed. |
| Persistence | A submitted synthetic response appears in the owner dashboard and export, including after a page reload. |
| Public links | Two forms have different references; published links accept signed-out submissions; drafts return 404. |
| Attribution | The visible provider link works on forms and confirmation/booking views and opens `https://catapultaiwork.com`. |
| Sheets, if enabled | A real test response reaches the form's app-created Sheet; pending deliveries can be retried after fixing an actual failure. |
| Meetings, if enabled | Slots reflect the schedule; a consenting test booking produces a Calendar event, Meet link, invitation, and confirmed Sheet row. |
| Domain, if enabled | HTTPS works, owner writes succeed, share links use the domain, and Google returns to its exact callback. |

Do not deliberately break production credentials to simulate an outage. Use an
isolated test installation if failure testing is needed. Automated tests mock
Google and cannot certify the user's live OAuth, Sheet, Calendar, or Vercel setup.

Finish with the canonical website and login URLs, enabled capabilities, checks
actually performed, and any pending user actions. Never include credentials or
real respondent data. Mark untested integrations as unverified rather than done.
Explain how to back up the database and where to find **Retry pending**.

## Troubleshooting

| Symptom | Check / recovery |
| --- | --- |
| Startup refuses configuration | Database URL, HTTPS base URL, password length, secret length, secure cookies, and `hosted` role. Vercel rejects local `admin` mode. |
| Database connection fails | Correct Production variable, pooled TLS URL, provider availability, and connectivity from Vercel. Do not log the connection string. |
| Login or owner save returns 403 | Use the exact canonical HTTPS origin; correct `FORMCRAFT_BASE_URL` and redeploy. |
| Login returns 429 | Wait for the shared five-minute attempt window; stop automated retries. |
| Google `redirect_uri_mismatch` | Web OAuth client, exact scheme/host/path, callback registered with Google, and redeployment after configuration changes. |
| OAuth state expired or rejected | Start a new connection from the owner dashboard in the same logged-in browser on the canonical domain. Do not reuse callback URLs. |
| Google stops syncing | Check API enablement, granted scopes, consent status, and expired/revoked grant; reconnect the same owner account, then retry pending delivery. |
| Google tokens fail after secret change | Disconnect and reconnect Google; keep the replacement installation secret stable and backed up. |
| Response exists but no Sheet row | Check Sheet attachment and pending sync. Native meetings defer rows until confirmed booking. |
| No meeting slots or Meet link | Check timezone, schedule, notice/window, busy events, Calendar permissions, owned calendar ID, and account Meet support. |

## Optional: local demo instead of deployment

For a local demo only, install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/),
then run in the checkout:

```bash
uv sync --locked
uv run python scripts/dev.py
```

Open `http://127.0.0.1:8480` and use `admin` / `devpassword` only for this disposable
development instance. The embedded PostgreSQL database lives in ignored
`data/devdb` on supported macOS/Linux systems. Do not expose this demo publicly.
It uses local-admin mode, not hosted browser OAuth. For your own local PostgreSQL,
follow the alternate setup in [README.md](README.md).

For code changes, run the verification commands in [AGENTS.md](AGENTS.md), using
only disposable test databases. The optional local-admin/public split is an
advanced deployment choice; it is not required for the normal hosted dashboard.
