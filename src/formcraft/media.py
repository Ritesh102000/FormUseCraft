# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Image slots.

Every image the UI can show is declared here once. If the file exists under
`web/static/img/` it is rendered; otherwise the optional illustration is omitted.
The admin media page lists available slots and suggested dimensions.

Drop a file named `<slot>.<ext>` into web/static/img to fill a slot.
See IMAGES.md for customization instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import settings

EXTENSIONS = (".webp", ".png", ".jpg", ".jpeg", ".svg", ".avif")


@dataclass(frozen=True)
class Slot:
    name: str
    label: str
    size: str
    ratio: str
    description: str
    round: bool = False


SLOTS: dict[str, Slot] = {
    "login-panel": Slot(
        "login-panel", "Sign-in illustration", "1200×1600", "3 / 4",
        "Optional workspace illustration. Use an image you own or can redistribute.",
    ),
    "responses-empty": Slot(
        "responses-empty", "Empty responses", "800×600", "4 / 3",
        "Optional illustration shown before the first response arrives.",
    ),
    "form-success": Slot(
        "form-success", "Submission received", "600×600", "1 / 1",
        "Optional thank-you illustration, without text embedded in the image.",
    ),
    "og-default": Slot(
        "og-default", "Link preview", "1200×630", "40 / 21",
        "Optional generic link preview. Do not include private response data.",
    ),
}


def resolve(slot_name: str, variant: str = "") -> str | None:
    """Return the public URL for a slot, or None when no asset exists yet.

    `variant` allows a per-form override, e.g. form-cover-creator-intake.
    """
    img_dir = settings.web_dir / "static" / "img"
    candidates = [f"{slot_name}-{variant}"] if variant else []
    candidates.append(slot_name)

    for stem in candidates:
        for ext in EXTENSIONS:
            if (img_dir / f"{stem}{ext}").is_file():
                return f"/static/img/{stem}{ext}"
    return None


_ASSET_HASHES: dict[str, str] = {}


def static_url(path: str) -> str:
    """/static/<path> with a content fingerprint appended.

    Without this, a deploy can leave visitors running cached JS against new
    templates — and the Vercel config marks /static immutable, so the stale
    copy would stick. The fingerprint changes only when the file changes.
    """
    if path not in _ASSET_HASHES:
        target = settings.web_dir / "static" / path
        try:
            stat = target.stat()
            _ASSET_HASHES[path] = f"{int(stat.st_mtime):x}{stat.st_size:x}"
        except OSError:
            _ASSET_HASHES[path] = "0"
    return f"/static/{path}?v={_ASSET_HASHES[path]}"


def briefs() -> str:
    """Every outstanding brief as plain text, ready to paste into a model."""
    lines = [
        "FORMCRAFT IMAGE BRIEFS",
        "Save each file to web/static/img/<slot>.webp",
        "Never render text inside an image — all copy is live HTML on top.",
        "",
    ]
    for name, slot in SLOTS.items():
        status = "FILLED" if resolve(name) else "MISSING"
        lines += [
            f"[{status}] {name}.webp — {slot.size}, ratio {slot.ratio}",
            f"  {slot.label}",
            f"  {' '.join(slot.description.split())}",
            "",
        ]
    return "\n".join(lines)


def context() -> dict[str, Any]:
    """Injected into every template render."""
    return {"slots": SLOTS, "media_url": resolve, "static_url": static_url}
