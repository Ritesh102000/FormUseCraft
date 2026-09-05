# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Start an embedded Postgres before Formcraft is imported.

`formcraft.config.settings` is a frozen dataclass built at import time, so the
database URL has to be in the environment before any formcraft module loads —
which means this runs at conftest import, not in a fixture.

Set FORMCRAFT_TEST_DATABASE_URL to test against your own database instead.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_server = None
_url = os.getenv("FORMCRAFT_TEST_DATABASE_URL")

if not _url:
    import pgserver

    _pgdata = Path(tempfile.mkdtemp(prefix="formcraft-pg-"))
    _server = pgserver.get_server(_pgdata)
    _url = _server.get_uri(database="postgres")

os.environ["FORMCRAFT_DATABASE_URL"] = _url
os.environ.setdefault("FORMCRAFT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("FORMCRAFT_ROLE", "admin")
os.environ.setdefault("FORMCRAFT_GOOGLE_ENABLED", "0")


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return _url


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    from formcraft.db import close_pool

    close_pool()
    if _server is not None:
        _server.cleanup()
