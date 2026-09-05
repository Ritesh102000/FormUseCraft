# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Run Formcraft against a throwaway embedded Postgres.

For trying things out with no database setup at all. Data lives under
data/devdb and survives restarts, but this is not for production — use a real
FORMCRAFT_DATABASE_URL for that.

    uv run python scripts/dev.py
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    try:
        import pgserver
    except ImportError:
        print("pgserver is a dev dependency. Install it with: uv sync")
        return 1

    # `--public` runs the visitor-facing instance against the same dev database,
    # so you can see exactly what someone with a form link gets.
    role = "public" if "--public" in sys.argv else "admin"

    pgdata = ROOT / "data" / "devdb"
    pgdata.mkdir(parents=True, exist_ok=True)
    print(f"Starting embedded Postgres in {pgdata} …")
    server = pgserver.get_server(pgdata)

    # Every env var must be set before any formcraft module is imported —
    # config.settings is a frozen dataclass built at import time.
    os.environ["FORMCRAFT_DATABASE_URL"] = server.get_uri(database="postgres")
    # Keep encrypted Google grants readable across local server restarts.
    secret_file = ROOT / "data" / "dev_secret.key"
    if not os.getenv("FORMCRAFT_SECRET_KEY"):
        try:
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as handle:
                handle.write(secrets.token_urlsafe(48))
        os.environ["FORMCRAFT_SECRET_KEY"] = secret_file.read_text().strip()
    os.environ.setdefault("FORMCRAFT_LOCAL_BROWSER_GOOGLE", "1")
    os.environ.setdefault("FORMCRAFT_GOOGLE_DEFAULT_PROFILE", "booking")
    os.environ["FORMCRAFT_ROLE"] = role

    if role == "admin" and not os.getenv("FORMCRAFT_ADMIN_PASSWORD_HASH"):
        # argon2 directly, not formcraft.auth, to avoid importing config early.
        from argon2 import PasswordHasher

        password = os.getenv("FORMCRAFT_DEV_PASSWORD", "devpassword")
        os.environ["FORMCRAFT_ADMIN_PASSWORD_HASH"] = PasswordHasher().hash(password)
        print(f"\n  Dev login → admin / {password}")
        print("  (set FORMCRAFT_DEV_PASSWORD to change it)\n")

    import uvicorn

    host = os.getenv("FORMCRAFT_HOST", "127.0.0.1")
    port = int(os.getenv("FORMCRAFT_PORT", "8480"))
    print(f"Formcraft [dev] → http://{host}:{port}")
    uvicorn.run("formcraft.app:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
