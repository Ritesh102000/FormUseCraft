<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Deploy your own FormUseCraft

Deploy one app containing your private owner dashboard and public form links.
The root Vercel entrypoint defaults to `FORMCRAFT_ROLE=hosted`. No local builder
is needed for normal hosted use. Each installation is independent.

## 1. Prepare your database and secrets

Create your own PostgreSQL database reachable from Vercel. Managed providers
such as [Neon](https://neon.tech) and [Supabase](https://supabase.com) offer options;
check their current terms and limits. Use a **pooled TLS connection string**.
Database tables are initialized on app startup, with a lock for concurrent boots.

Generate a unique owner password and a different random installation secret
using your password manager. The deployment button prompts for:

| Variable | Required value |
| --- | --- |
| `FORMCRAFT_DATABASE_URL` | Your pooled PostgreSQL URL with TLS |
| `FORMCRAFT_ADMIN_PASSWORD` | Unique owner password, at least 12 characters |
| `FORMCRAFT_SECRET_KEY` | Unique random installation secret, at least 32 characters; use 48+ |

Do not reuse example secrets, share them in issues, or commit them. Vercel
variables are server-side secrets. Mark credentials sensitive when supported.
Keep an offline protected backup of the installation secret: it signs sessions
and encrypts Google tokens. Changing it requires reconnecting Google.

## 2. Deploy your copy

Use the **Deploy with Vercel** button in README.md, or import
[Ritesh102000/FormUseCraft](https://github.com/Ritesh102000/FormUseCraft) from
[Vercel New Project](https://vercel.com/new). Use the repository root and automatic
FastAPI detection, without a frontend build/output directory.

The repository requires Python 3.12 and includes the lockfile and runtime
requirements. Do not upload `.env`, token files, `.venv`, or `data/`.

Deploy with the three variables above in **Production**. The app uses Vercel's
`VERCEL_PROJECT_PRODUCTION_URL` to derive its canonical HTTPS URL by default.
If that system variable is unavailable, set `FORMCRAFT_BASE_URL` to your exact
HTTPS deployment origin and redeploy. There must be no path after the hostname.

Open the deployed URL and sign in as `admin` with your configured password.
The dashboard is protected; visitors do not get a signup route. `FORMCRAFT_ROLE`
may be omitted on Vercel or explicitly set to `hosted`. Do not use `admin`,
which is reserved for a local builder and is rejected by the Vercel entrypoint.

Optional settings:

| Variable | Purpose |
| --- | --- |
| `FORMCRAFT_ADMIN_USERNAME` | Owner username; defaults to `admin` |
| `FORMCRAFT_ADMIN_PASSWORD_HASH` | Argon2 alternative to the plaintext password variable |
| `FORMCRAFT_BRAND_NAME` | Your organization's display name |
| `FORMCRAFT_BASE_URL` | Exact canonical HTTPS origin, especially for custom domains |
| `FORMCRAFT_GOOGLE_CLIENT_ID` | Your Google **Web application** OAuth client ID |
| `FORMCRAFT_GOOGLE_CLIENT_SECRET` | That client's secret |
| `FORMCRAFT_GOOGLE_CALENDAR_ID` | Owned calendar to book; defaults to `primary` |

Secure cookies are on by default in hosted mode. The app refuses weak/missing
owner credentials, short installation secrets, HTTP origins, or disabled secure
cookies. Password changes invalidate existing owner sessions. A shared budget
limits sign-in attempts to 20 per five minutes; wait before retrying if exceeded.

Do not copy Production database or Google credentials into Preview deployments.
Disable previews or give each preview a separate disposable database, secrets,
canonical URL, and test Google client/account. Redeploy after changing variables.

## 3. Connect Google from the dashboard

Open **Google integrations**. Follow its checklist to enable Drive/Sheets APIs
and create your own **Web application** OAuth client in Google Cloud. For native
meetings, also enable Calendar API.

Add the exact callback URL shown in the app, for example:

```text
https://YOUR-PROJECT.vercel.app/oauth/google/callback
```

Set the client ID and secret as Vercel Production variables and redeploy. Return
to the dashboard and click **Connect Google Sheets** or **Connect Sheets +
Calendar**. Sign in to the Google account that should own your data and approve
the scopes. Tokens are encrypted in PostgreSQL; no token file upload is needed.
See [the Google guide](docs/GOOGLE_SHEETS.md) for consent-screen and token limits.

## Optional AI configuration

The owner dashboard includes **Build with AI** using a per-request OpenAI key
or the server's `OPENAI_API_KEY`. An environment key makes voice available
automatically after deployment; opt in each published form in its settings.
Use `FORMCRAFT_AI_VOICE_DAILY_TURNS` to choose a shared turn cap (default 200).
See [AI setup](docs/AI.md) for models, privacy, usage limits, and acceptance checks.
Public voice fills answer fields; submission and booking remain manual.

## 4. Make and share forms

Click **New form**, add questions, save, and publish. Copy its public `/f/…` link
from the dashboard. When Google is connected, regular new forms get a Sheet;
for an existing form choose **Create Sheet** on its responses page.

For meetings, connect Sheets + Calendar and choose **New meeting form**. Set
your timezone, weekdays, start times, duration, notice, and booking window. The
wizard saves a draft with the required name/email booking fields. Edit its
questions, publish, and share the link. Open **Meeting settings** from its builder
to change the schedule. The wizard also attempts to attach its spreadsheet. If Google was unavailable,
use **Create Sheet** on its responses page. Native meeting rows sync after booking confirmation.

## 5. Add your domain

In Vercel **Settings → Domains**, add a domain you own and apply the exact DNS
records shown at your registrar. Follow [Vercel's domain guide](https://vercel.com/docs/domains/working-with-domains/add-a-domain).
Wait for HTTPS verification.

Set `FORMCRAFT_BASE_URL=https://forms.example.com` and redeploy. Add
`https://forms.example.com/oauth/google/callback` to the Google OAuth client's
authorized redirect URIs. Sign in and reconnect Google on that canonical domain.
Use the canonical domain for the owner dashboard: owner mutations from another
origin are rejected. Share links generated thereafter use the configured domain.

The local `scripts/dev.py` launcher also exposes the Google setup page using
a loopback callback and stable local encryption secret. See the
[local Google guide](docs/GOOGLE_SHEETS.md#local-browser-setup).

## Acceptance checks

1. Signed out, `/` redirects to login and protected exports return 401. Admin
   pages cannot show data without the owner's session.
2. `/healthz` returns only `{"ok":true}`. It is not proof of Google connectivity.
3. Create two forms. Their public references must differ. A signed-out visitor
   can submit published forms and gets 404 for drafts.
4. Submit a synthetic response; verify it in the owner dashboard, an export,
   and the connected Sheet. Retry a failed sync using **Retry pending**.
5. For a meeting form, verify live slots, a real Calendar event, Meet link,
   invitation, and the confirmed Sheet row using consenting test participants.
6. Confirm the visible provider link still opens https://catapultaiwork.com.

## Costs and operational limits

[Vercel Hobby](https://vercel.com/docs/limits/fair-use-guidelines) permits personal,
non-commercial use. The software permits commercial use under LICENSE, but
commercial hosting needs an appropriate provider plan. PostgreSQL and custom
domains have separate costs/limits. There is no promise of unlimited free hosting.

Back up PostgreSQL. Provider calls run in requests; a database write succeeds
before delivery to Google. Google failures leave responses pending; an owner
must retry them. General form spam/CAPTCHA and a background worker are not included.
The local-only CSV bearer feed is disabled in hosted mode.

Optional advanced split mode remains available: use a local `admin` instance and
set the Vercel deployment to `public`, using the same database and locally
configured Google profiles. That mode has no dashboard or browser OAuth routes.
Do not mix local token files with the hosted encrypted-connection flow.
