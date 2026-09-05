# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Generate the admin password hash and secret key, and write them into .env."""

from __future__ import annotations

import getpass
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from formcraft.auth import hash_password  # noqa: E402

ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def upsert(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip("\n") + f"\n{line}\n"


def main() -> int:
    if not ENV.exists():
        if not EXAMPLE.exists():
            print("No .env.example found.")
            return 1
        ENV.write_text(EXAMPLE.read_text())
        print("Created .env from .env.example")

    text = ENV.read_text()

    username = input("Admin username [admin]: ").strip() or "admin"
    password = getpass.getpass("Admin password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return 1
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.")
        return 1

    text = upsert(text, "FORMCRAFT_ADMIN_USERNAME", username)
    text = upsert(text, "FORMCRAFT_ADMIN_PASSWORD_HASH", hash_password(password))

    if not re.search(r"^FORMCRAFT_SECRET_KEY=.+$", text, re.MULTILINE):
        text = upsert(text, "FORMCRAFT_SECRET_KEY", secrets.token_urlsafe(48))
        print("Generated a new FORMCRAFT_SECRET_KEY.")

    ENV.write_text(text)
    ENV.chmod(0o600)
    print(f"\nSaved. Admin user is '{username}'.")
    print("Start the server with: uv run python scripts/run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
