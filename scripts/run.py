# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Start Formcraft.

Two roles share one database:

  admin   local only. Login, builder, responses, plus the public form routes.
  public  the internet-facing instance. Only renders and accepts forms —
          no login page, no builder, no API. Those routes are never registered.

    uv run python scripts/run.py                     # admin  → 127.0.0.1:8480
    FORMCRAFT_ROLE=public uv run python scripts/run.py  # public → 0.0.0.0:8481
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn  # noqa: E402

from formcraft.config import settings  # noqa: E402

DEFAULTS = {
    # Admin binds loopback only: the surface should not be reachable off-machine
    # even before the per-request local check runs.
    "admin": ("127.0.0.1", 8480),
    "hosted": ("0.0.0.0", 8480),
    "public": ("0.0.0.0", 8481),  # noqa: S104 - intentional, this one is shared
}


def main() -> int:
    if not settings.is_configured:
        print(f"Formcraft ({settings.role}) is not configured yet.\n")
        if not settings.database_url:
            print("  • FORMCRAFT_DATABASE_URL is empty")
        if settings.is_admin_role and not settings.secret_key:
            print("  • FORMCRAFT_SECRET_KEY is empty")
        if settings.is_admin_role and not (settings.admin_password_hash or settings.admin_password):
            print("  • FORMCRAFT_ADMIN_PASSWORD_HASH is empty")
        print("\nCopy .env.example to .env, set FORMCRAFT_DATABASE_URL, then run:")
        print("  uv run python scripts/set_password.py")
        return 1

    default_host, default_port = DEFAULTS[settings.role]
    host = os.getenv("FORMCRAFT_HOST", default_host)
    port = int(os.getenv("FORMCRAFT_PORT", str(default_port)))

    label = "admin (local only)" if settings.is_admin_role else "public forms"
    print(f"Formcraft [{label}] → http://{host}:{port}")
    if settings.is_admin_role and host not in {"127.0.0.1", "::1", "localhost"}:
        print(
            "  ! Admin role is bound to a non-loopback address. Requests from "
            "other machines are still refused unless FORMCRAFT_ADMIN_ALLOW_REMOTE=1."
        )

    uvicorn.run("formcraft.app:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
