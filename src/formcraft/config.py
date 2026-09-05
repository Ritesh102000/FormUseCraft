# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Runtime settings, loaded once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: str) -> Path:
    raw = os.getenv(name, default)
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else ROOT / candidate


@dataclass(frozen=True)
class Settings:
    root: Path
    database_url: str
    db_pool_size: int
    web_dir: Path
    role: str
    admin_allow_remote: bool
    brand_name: str
    owner_name: str
    owner_role: str
    serverless: bool
    admin_username: str
    admin_password_hash: str
    secret_key: str
    base_url: str
    secure_cookies: bool
    google_enabled: bool
    google_client_secret_file: Path
    google_token_file: Path
    google_token_json: str
    google_booking_token_file: Path
    google_booking_token_json: str
    google_default_profile: str
    google_calendar_id: str
    booking_hmac_secret: str
    admin_password: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    openai_api_key: str = ""
    ai_model: str = "gpt-4.1-mini"
    ai_transcribe_model: str = "gpt-4o-mini-transcribe"
    ai_voice_daily_turns: int = 200

    @property
    def is_hosted_role(self) -> bool:
        return self.role == "hosted"

    @property
    def is_admin_role(self) -> bool:
        return self.role in {"admin", "hosted"}

    @property
    def is_configured(self) -> bool:
        """Public instances need no credentials — they only render forms."""
        if not self.database_url:
            return False
        if not self.is_admin_role:
            return True
        return bool(
            (self.admin_password_hash or self.admin_password) and self.secret_key
        )


def load_settings() -> Settings:
    role = os.getenv("FORMCRAFT_ROLE", "admin").strip().lower()
    if role not in {"admin", "public", "hosted"}:
        raise ValueError(
            f"FORMCRAFT_ROLE must be 'admin', 'public', or 'hosted', got {role!r}"
        )

    google_default_profile = (
        os.getenv(
            "FORMCRAFT_GOOGLE_DEFAULT_PROFILE",
            "booking" if role == "hosted" else "default",
        )
        .strip()
        .lower()
    )
    if google_default_profile not in {"default", "booking"}:
        raise ValueError(
            "FORMCRAFT_GOOGLE_DEFAULT_PROFILE must be 'default' or 'booking', "
            f"got {google_default_profile!r}"
        )

    return Settings(
        root=ROOT,
        # Vercel marketplace Postgres integrations expose DATABASE_URL. Keep
        # the Formcraft-specific name as the explicit override for local and
        # non-Vercel deployments.
        database_url=(
            os.getenv("FORMCRAFT_DATABASE_URL") or os.getenv("DATABASE_URL", "")
        ).strip(),
        db_pool_size=int(os.getenv("FORMCRAFT_DB_POOL_SIZE", "5")),
        web_dir=ROOT / "web",
        role=role,
        admin_allow_remote=_flag("FORMCRAFT_ADMIN_ALLOW_REMOTE"),
        brand_name=os.getenv("FORMCRAFT_BRAND_NAME", "FormUseCraft").strip(),
        owner_name=os.getenv("FORMCRAFT_OWNER_NAME", "").strip(),
        owner_role=os.getenv("FORMCRAFT_OWNER_ROLE", "").strip(),
        # Vercel and most FaaS hosts set VERCEL / AWS_LAMBDA_FUNCTION_NAME.
        serverless=_flag("FORMCRAFT_SERVERLESS")
        or bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")),
        admin_username=os.getenv("FORMCRAFT_ADMIN_USERNAME", "admin").strip(),
        admin_password_hash=os.getenv("FORMCRAFT_ADMIN_PASSWORD_HASH", "").strip(),
        secret_key=os.getenv("FORMCRAFT_SECRET_KEY", "").strip(),
        base_url=os.getenv(
            "FORMCRAFT_BASE_URL",
            "https://" + os.environ["VERCEL_PROJECT_PRODUCTION_URL"]
            if os.getenv("VERCEL_PROJECT_PRODUCTION_URL")
            else "http://127.0.0.1:8480",
        ).rstrip("/"),
        secure_cookies=_flag(
            "FORMCRAFT_SECURE_COOKIES", "1" if role == "hosted" else "0"
        ),
        google_enabled=_flag("FORMCRAFT_GOOGLE_ENABLED"),
        google_client_secret_file=_path(
            "FORMCRAFT_GOOGLE_CLIENT_SECRET_FILE", "data/google_client_secret.json"
        ),
        google_token_file=_path(
            "FORMCRAFT_GOOGLE_TOKEN_FILE", "data/google_token.json"
        ),
        google_token_json=os.getenv("FORMCRAFT_GOOGLE_TOKEN_JSON", "").strip(),
        google_booking_token_file=_path(
            "FORMCRAFT_GOOGLE_TOKEN_FILE_BOOKING",
            "data/google_token_booking.json",
        ),
        google_booking_token_json=os.getenv(
            "FORMCRAFT_GOOGLE_TOKEN_JSON_BOOKING", ""
        ).strip(),
        google_default_profile=google_default_profile,
        google_calendar_id=os.getenv("FORMCRAFT_GOOGLE_CALENDAR_ID", "primary").strip()
        or "primary",
        booking_hmac_secret=os.getenv("FORMCRAFT_BOOKING_HMAC_SECRET", "").strip(),
        admin_password=os.getenv("FORMCRAFT_ADMIN_PASSWORD", ""),
        openai_api_key=(
            os.getenv("FORMCRAFT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        ).strip(),
        ai_model=os.getenv("FORMCRAFT_AI_MODEL", "gpt-4.1-mini").strip(),
        ai_transcribe_model=os.getenv(
            "FORMCRAFT_AI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"
        ).strip(),
        ai_voice_daily_turns=max(
            0, min(5000, int(os.getenv("FORMCRAFT_AI_VOICE_DAILY_TURNS", "200")))
        ),
        google_client_id=os.getenv("FORMCRAFT_GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("FORMCRAFT_GOOGLE_CLIENT_SECRET", "").strip(),
    )


def validate_hosted_settings() -> None:
    from urllib.parse import urlsplit

    if not settings.is_hosted_role:
        return
    url = urlsplit(settings.base_url)
    if (
        not settings.is_configured
        or len(settings.secret_key) < 32
        or (not settings.admin_password_hash and len(settings.admin_password) < 12)
        or not settings.secure_cookies
        or url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise RuntimeError(
            "Hosted setup requires a database, HTTPS FORMCRAFT_BASE_URL, secure "
            "cookies, a unique FORMCRAFT_SECRET_KEY of at least 32 characters, "
            "and FORMCRAFT_ADMIN_PASSWORD of at least 12 characters (or its hash)."
        )


settings = load_settings()
