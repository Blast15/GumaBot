"""Verified off-site generations using a preconfigured rclone remote."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gumabot.database.migrations import backup, check

GENERATION = re.compile(r"gumabot-\d{8}T\d{12}Z")


def upload(database: Path, remote: str, keep: int = 14) -> str:
    executable = shutil.which("rclone")
    if not executable:
        raise ValueError("Install rclone and configure an off-site remote first")
    if not re.fullmatch(
        r"[A-Za-z0-9_][A-Za-z0-9_-]*:[A-Za-z0-9_./-]+", remote
    ) or ".." in remote.split(":", 1)[1].split("/"):
        raise ValueError("Use a named rclone remote and dedicated path, e.g. archive:gumabot")
    if keep < 2:
        raise ValueError("Keep at least two verified generations")
    destination = remote.rstrip("/")
    generation = datetime.now(UTC).strftime("gumabot-%Y%m%dT%H%M%S%fZ")

    def command(*arguments):
        # Fixed executable and argument vector, no shell or credentials in argv.
        return subprocess.run(  # noqa: S603 - fixed executable and argument vector
            [executable, *arguments], check=True, capture_output=True, text=True, timeout=600
        ).stdout

    with tempfile.TemporaryDirectory(prefix="gumabot-backup-") as folder:
        snapshot = backup(database, Path(folder) / "gumabot.db")
        check(snapshot)
        target = destination + "/" + generation
        command("copy", folder, target)
        # Download verification also works for remotes without a compatible checksum API.
        command("check", folder, target, "--one-way", "--download")
        marker = Path(folder) / "verified.json"
        marker.write_text(
            json.dumps({"verified_at": generation, "database": "gumabot.db"}), encoding="utf-8"
        )
        command("copyto", str(marker), target + "/verified.json")
        listing = json.loads(
            command(
                "lsjson", destination, "--recursive", "--files-only", "--include", "*/verified.json"
            )
        )
        generations = sorted(
            {
                entry["Path"].split("/")[0]
                for entry in listing
                if len(entry["Path"].split("/")) == 2
                and entry["Path"].endswith("/verified.json")
                and GENERATION.fullmatch(entry["Path"].split("/")[0])
            }
        )
        for old in generations[:-keep]:
            if old != generation:
                command("purge", destination + "/" + old)
        return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/gumabot.db"))
    parser.add_argument("--remote", required=True)
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    print(upload(args.database, args.remote, args.keep))
