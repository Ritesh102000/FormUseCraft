# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Vercel entrypoint: hosted owner dashboard by default; public-only is optional."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

os.environ.setdefault("FORMCRAFT_ROLE", "hosted")
os.environ.setdefault("FORMCRAFT_SERVERLESS", "1")

from formcraft.config import settings  # noqa: E402

if settings.role == "admin":
    raise RuntimeError(
        "Refusing to start: FORMCRAFT_ROLE is 'admin' on a serverless host. "
        "Use hosted for an online dashboard or public for forms only."
    )

from formcraft.app import app  # noqa: E402

__all__ = ["app"]
