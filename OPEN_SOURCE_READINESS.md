<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Public Release Readiness

## Owner decisions

Publish the independent project to
[Ritesh102000/FormUseCraft](https://github.com/Ritesh102000/FormUseCraft).
Personal/commercial use is allowed under the custom LICENSE with mandatory
visible catapultaiwork attribution. This is source-available, not MIT or an
OSI-approved license. All project files retain the explanatory notice.

## Release contents

A hosted owner dashboard and public form links, browser Google OAuth, encrypted
connection storage, meeting setup UI, optional public-only/local modes, Vercel
Deploy button, setup guides, CI, and release checks. No live credentials,
production responses, hosting metadata, or unverified bundled raster art belong
in the release. Hosting and provider setup remain the deployer's responsibility.

## Publishing procedure

1. Run all checks in AGENTS.md and `uv run python scripts/check_release.py`.
2. Review current source and license. The heuristic scan is not a guarantee
   against every possible secret. Recheck any new assets' redistribution rights.
3. Export current reviewed files with `scripts/export_release.py` to a new ZIP
   outside this checkout. Initialize a fresh repository from that export.
4. Push only that clean initial history to the owner-selected GitHub destination.
   The original local baseline includes removed assets and must not be pushed.
5. Verify the remote branch and CI, then follow DEPLOY.md with an independently
   selected Vercel project, PostgreSQL database, and Google OAuth client.

No live Vercel deployment, Google grant, Sheet, or Calendar event is created by
source publication. Local tests mock Google; each real installation must complete
the acceptance checks in DEPLOY.md. The user-selected repository permits source
publication, not blanket authorization for unrelated cloud resources.

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


## AI builder and voice addition (2026-09-05)

The owner requested an AI builder using their own OpenAI key, description/PDF/image
inputs, and optional per-form public voice assistance funded by an environment
key. The owner explicitly excludes voice booking actions. Payments remain
unimplemented; a payment handoff prompt is not a payment integration.

- `/admin/ai` generates/refines a validated preview and creates an editable,
  unpublished draft. Request-only keys are never persisted; environment keys
  are also supported. Native meeting drafts require connected Google Calendar
  and receive server-generated attendee bindings and hidden booking metadata.
- Public voice requires the environment key, per-form flag, and
  visitor opt-in. It maps short recordings to one visible field, validates and
  confirms the value, and leaves submission and scheduling to the visitor.
- No voice action can save a response, book, pay, or write provider metadata.
  Sessions are signed, expire in 30 minutes, and bind to a form/revision.
  PostgreSQL usage counters span serverless instances; requests and uploads
  are bounded. Recordings/transcripts and owner request keys are not persisted.
- `docs/AI.md`, `.env.example`, README, deployment, and LLM setup guides document
  keys, switches, cost/usage boundaries, privacy, and live verification steps.

Verification: 154 Python tests passed with disposable PostgreSQL and mocked
OpenAI/Google, plus Ruff and four JavaScript syntax checks. Local Chrome smoke
checks passed owner generation/save, voice opt-in persistence, consent, answer
confirmation, stopping microphone tracks, manual submission, and scheduling
handoff in all three form layouts, including mobile. Browser speech/microphone
and OpenAI responses were synthetic. No live OpenAI request or deployment was
made; live speech quality and account access remain unverified.


### Simplified voice activation

An environment OpenAI key now makes voice available automatically, with no global
voice-enable variable. The owner still opts in each form; visitor consent and
usage caps remain required. The legacy FORMCRAFT_AI_VOICE_ENABLED variable is
ignored, including when old deployments still set it to 0. Provider access is
checked during actual requests, and errors leave manual filling available.

Activation-change verification: 157 tests, Ruff, JavaScript syntax, release notice
scan, and whitespace checks passed. Live key access remains checked on use.


## Google onboarding correction

The local dev launcher now enables browser Google connection and meeting setup,
using a loopback-only owner boundary and a stable ignored encryption secret.
Hosted HTTPS requirements are unchanged. Manual/AI first saves without Google
surface a connection prompt; the builder always shows the connection state and
an existing form's Sheet attachment action. Setup opens in another tab to preserve
unsaved edits. Actual connection still needs the owner's Web OAuth client and
consent; no provider accounts or credentials are bundled.


## Response browser and native browser login correction

Responses now use database queries with search across answers/IDs, inclusive UTC
date filters, optional Sheets sync filters, numeric/text sorts, stable tie-breaking,
and 25/50/100-row pages across the whole form. Table/card previews open a protected
full response, including archived answers and expandable hidden metadata. Mobile
filters collapse, filter state survives view/detail navigation, and timestamps are
converted to UTC. Exports keep their existing 10,000-response scope.

Local and hosted owner pages now use `Referrer-Policy: same-origin`. The previous
`no-referrer` policy caused native HTML login POSTs to send `Origin: null`, which
correctly failed the canonical-origin check. Browser login now succeeds without
weakening that check; null and foreign origins remain rejected. The Google prompt
explicitly offers **Use app database only** and explains PostgreSQL persistence.

Verification: 168 tests passed against disposable PostgreSQL with mocked providers,
including 561-response browsing, history, isolation, escaping, and the Google local
boundary. Native browser login, search/filter submission, no-results recovery,
card/detail navigation, and desktop/390px mobile layout were exercised locally.
The existing one form and one response survived restarts. No live Google grant or
Vercel deployment was performed. Google still requires the owner's Web OAuth client.
