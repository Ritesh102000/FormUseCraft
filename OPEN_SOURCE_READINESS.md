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
