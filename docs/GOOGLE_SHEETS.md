<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Connect Google Sheets and Calendar

In the hosted dashboard, open **Google integrations**. Each installation uses
its owner's Google account and OAuth client. Respondents never authorize Google.
Regular forms work without Google: PostgreSQL stores the responses.

## One-time client setup

1. Create/select your project in [Google Cloud Console](https://console.cloud.google.com).
2. Enable the **Google Drive API** and **Google Sheets API**. For meeting forms,
   also enable the **Google Calendar API**.
3. Configure OAuth branding/audience/contact details. If an External app stays
   in Testing, its refresh token expires after seven days for these scopes under
   [Google's OAuth rules](https://developers.google.com/identity/protocols/oauth2).
   Add yourself as a test user while testing; choose the appropriate Production
   configuration for ongoing use. Meet consent/verification rules for your audience.
4. Create an OAuth client of type **Web application**, not Desktop app.
5. Add the exact authorized redirect URI shown in FormUseCraft's integrations
   page: `https://YOUR-DOMAIN/oauth/google/callback`.
6. Set `FORMCRAFT_GOOGLE_CLIENT_ID` and `FORMCRAFT_GOOGLE_CLIENT_SECRET` in the
   Vercel Production environment and redeploy. No credential belongs in Git.

## Browser connection

Click **Connect Google Sheets** for data collection, or **Connect Sheets +
Calendar** for meetings too. Choose your account and approve the permissions.
The app verifies your account identity and stores the grant encrypted in your
own PostgreSQL database. Authorization state is short-lived, bound to the owner
session, and accepted only once; PKCE also protects the code exchange.

The Sheets option requests `drive.file` plus OpenID/email identity scopes.
It accesses app-created/authorized files rather than all of Drive, following
[Google's Drive scope guidance](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
The Calendar option adds `calendar.events.owned` and `calendar.freebusy`.
Google may require additional consent or verification for Calendar access.

The connected account owns the created Sheets and calendar events. The default
booking calendar is `primary`; set `FORMCRAFT_GOOGLE_CALENDAR_ID` to another
calendar owned by that account before using meeting forms. Meet must be supported
by the selected account/calendar. There is no per-form calendar picker yet.

## Use and recovery

- Regular forms created while Google is connected get an app-created spreadsheet.
  For pre-existing forms or failed attachments, open **Responses → Create Sheet**.
- Each form's Sheet is separate. This version does not offer an existing-Sheet
  URL picker. Do not change the hidden response-ID column used for reconciliation.
- Responses are saved before provider delivery. Failed syncs remain pending;
  use **Retry pending** after resolving connectivity or permissions.
- Native booking responses stay in PostgreSQL and are sent to Sheets after
  booking is confirmed. Browser redirects alone do not confirm provider bookings.
- To recover an expired or revoked grant, reconnect from **Google integrations**.
  Existing Sheets/meeting forms require reconnecting the same Google account;
  the app rejects silent retargeting to a different account.
- Disconnect removes the stored grant and cancels pending authorization attempts.
  It does not delete responses, Sheets, or Calendar events. To revoke provider
  access entirely, also remove the app in [Google account permissions](https://myaccount.google.com/permissions).
- Keep the installation secret backed up. Changing it makes existing encrypted
  tokens unreadable; disconnect and reconnect Google using the new secret.

Never paste secrets or live responses into public issues. The owner interface
shows connection state, not refresh tokens or client secrets.

## Local browser setup

`uv run python scripts/dev.py` now enables the browser connection page locally,
as well as the meeting wizard. Open **Google integrations**, set your Web OAuth
client ID and secret in the ignored `.env`, and restart the app. Register the
exact displayed callback, normally
`http://127.0.0.1:8480/oauth/google/callback`. Google permits HTTP loopback redirect
URIs for local testing; hosted deployments still require HTTPS. Use Chrome or
Safari for the actual Google sign-in because Google can reject embedded browsers.

The dev launcher stores a stable secret in ignored `data/dev_secret.key`, so
encrypted Google grants remain readable across restarts. Preserve that file
alongside the local database. Browser credentials are stored in PostgreSQL; do
not mix them with Desktop OAuth token files. This local mode rejects remote
admin access and non-loopback origins. The launcher sets
`FORMCRAFT_LOCAL_BROWSER_GOOGLE=1` automatically.

The form builder shows a connection panel. A first save without Google prompts
you to connect or choose **Use app database only**; PostgreSQL stores forms and
responses either way. Setup
opens in another tab to preserve edits. For existing forms, return after
connection and choose **Create this form's Sheet**, or **Responses → Create Sheet**.

## Advanced local-only split setup

The advanced local-admin/public split still supports
`uv run python scripts/google_setup.py` with a Desktop OAuth client and
`--profile booking` for the Calendar grant. Those local token files are ignored
by Git. That script is not part of the normal hosted setup; do not upload its
tokens to a hosted-role installation, which uses its encrypted database grant.
