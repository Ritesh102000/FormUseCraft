<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Security

FormUseCraft provides one owner account per independent installation. Hosted
mode places the owner dashboard and public forms in one app; protected routes
require the owner session. Public form URLs are opaque but may be forwarded.
They do not authenticate respondents.

Hosted mode requires HTTPS, secure/HttpOnly/SameSite cookies, an installation
secret of at least 32 characters, and an owner password of at least 12 characters
(or an Argon2 hash). Owner mutations require the exact configured origin. Owner
pages are not cached. Password changes invalidate sessions. Database-backed
login limits apply across instances; sustained attempts can temporarily prevent
the owner from signing in too. Host traffic controls can mitigate this.

Google OAuth uses a configured callback URL, one-time expiring state bound to the
owner session, PKCE, and verified account identity. Tokens are encrypted using
a key derived from the installation secret. That secret must be stored separately
from DB backups. A database read alone does not reveal tokens; compromising both
the application secret and database compromises the grant. Account changes are
rejected when existing forms depend on the previous account's services.

Disconnect clears local credentials; revoke Google access through the Google
account permissions page if needed. Never post tokens, environment values,
OAuth codes, actual responses, or client secrets in GitHub issues or logs.
Keep Production and Preview databases, credentials, and URLs separate.

Public submissions need appropriate traffic/abuse controls for your use case.
Native booking adds database-backed invitation limits. There is no general
CAPTCHA, multi-user tenant isolation, background retry worker, versioned migration
framework, or long-term support guarantee. Back up PostgreSQL before updates.

The optional `admin` role remains loopback-only by default; its remote override
is intended for an authenticated proxy/VPN. The `public` role omits admin routes.
The localhost-only CSV bearer feed is blocked in `hosted` mode.

## Vulnerability reporting

Use GitHub's private “Report a vulnerability” feature if enabled on the published
repository. Otherwise contact the maintainer through https://catapultaiwork.com
to arrange a private channel before sending details. No security email address
or response-time SLA is declared. Supply a reproduction with synthetic data,
affected version, impact, and suggested mitigation. Do not publish exploit
credentials or private response data.


## Optional AI processing

OpenAI keys belong to the installation owner. Dashboard request keys are held
only for the request; environment keys remain server-side. Owner generation is
authenticated and requires the canonical origin. Public voice is off by default,
requires per-form opt-in and visitor consent in the UI, and has shared PostgreSQL
usage limits. Public endpoints can still be called by automated clients; the caps
limit usage but are not bot detection or a dollar budget.

Voice has no booking, payment, submission, or arbitrary tool action. Hidden
provider fields are filtered server-side; only validated visible field candidates
are returned. Sessions are signed and form/revision-bound. Browser confirmation
applies candidates locally. Stop/close/navigation releases microphone tracks.
Uploaded references, short recordings, transcripts, and field context are sent
to OpenAI as described in [AI privacy and limits](docs/AI.md). Do not post live
keys, recordings, or respondent data in issues.
