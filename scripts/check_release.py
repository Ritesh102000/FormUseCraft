# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Check current publishable files without displaying secret values."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTICE = "Source-available with required attribution"
PROVIDER_URL = "https://catapultaiwork.com"
FORBIDDEN_PARTS = {
    ".git", ".venv", ".vercel", "data", "tmp", "node_modules",
    "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".db", ".sqlite", ".sqlite3", ".dump", ".log"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "Google access token": re.compile(r"\bya29\.[A-Za-z0-9_-]{30,}"),
    "Google refresh token": re.compile(r"\b1//[A-Za-z0-9_-]{30,}"),
    "Google API key": re.compile(r"\bAIza[A-Za-z0-9_-]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
}


def release_files() -> list[Path]:
    """Current tracked and unignored files only; no old Git object contents."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, check=True,
    )
    names = sorted(set(result.stdout.decode().split("\0")) - {""})
    return [ROOT / name for name in names if (ROOT / name).exists()]


def check(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        relative = path.relative_to(ROOT)
        name = path.name.lower()
        if (
            path.is_symlink()
            or FORBIDDEN_PARTS.intersection(relative.parts)
            or path.suffix.lower() in FORBIDDEN_SUFFIXES
            or (name.startswith(".env") and name != ".env.example")
            or (name.endswith(".json") and any(
                word in name for word in ("client_secret", "google_token", "credentials")
            ))
        ):
            problems.append(f"{relative}: forbidden release path")
            continue
        try:
            text = path.read_text()
        except (UnicodeError, OSError):
            problems.append(f"{relative}: binary or unreadable file requires rights review")
            continue
        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError:
                problems.append(f"{relative}: invalid JSON")
        if NOTICE not in text or PROVIDER_URL not in text:
            problems.append(f"{relative}: missing provider/license notice")
        for label, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{relative}:{line}: possible {label}")
    return problems


def main() -> int:
    files = release_files()
    problems = check(files)
    if problems:
        print("Release checks failed (values are deliberately redacted):")
        print("\n".join(problems))
        return 1
    print(f"Checked {len(files)} current release files: notices, paths, known token patterns.")
    print("This heuristic scan is not a guarantee; review the diff and export before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
