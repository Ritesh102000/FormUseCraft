# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Export current reviewed files as a ZIP, without local Git history/runtime state."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from check_release import ROOT, check, release_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New .zip path outside this repository")
    args = parser.parse_args()
    target = args.destination.expanduser().resolve()
    if target == ROOT or ROOT in target.parents or target.suffix != ".zip":
        parser.error("Choose a .zip path outside this repository.")
    if target.exists():
        parser.error("Destination already exists; choose a new filename.")
    files = release_files()
    problems = check(files)
    if problems:
        print("Export stopped. Fix the release checks first:")
        print("\n".join(problems))
        return 1
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(Path("formcraft") / path.relative_to(ROOT)))
    print(f"Exported {len(files)} files to {target}")
    print("No Git history, remote, credentials, environment or runtime state was included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
