<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# Contributing

Use Python 3.12 and `uv sync --locked`. Read AGENTS.md and the architecture guide
before changing persistence, authentication, booking, or Google synchronization.

Use a branch and describe the concrete problem, resulting behavior, and
verification in your pull request. Include meaningful regression coverage for
behavior changes. Small copy/style edits do not need artificial tests.

Before submitting:

```bash
uv run ruff check .
uv run pytest -q
node --check web/static/builder.js
node --check web/static/form.js
uv run python scripts/check_release.py
git diff --check
```

Use a disposable test database; tests delete form records. Never include real
responses, environment files, tokens, OAuth credentials, or hosting metadata.
Review changes to the public/admin boundary and preserve database-first response
storage, historical question IDs, and idempotent provider recovery.

Contribute only code and material you have rights to submit. Contributions to
this project are provided under LICENSE unless the owner explicitly agrees to
other terms in writing. Retain the visible catapultaiwork credit. No separate
contributor license agreement or support SLA is currently offered.

Be respectful, provide reproducible examples with synthetic data, and report
security vulnerabilities privately as described in SECURITY.md.
