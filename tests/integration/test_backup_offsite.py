import json
import subprocess
from types import SimpleNamespace

import pytest

from gumabot.database.migrations import migrate
from scripts.backup_offsite import upload


def test_offsite_checks_before_pruning_and_keeps_unrelated_paths(tmp_path, monkeypatch):
    database = tmp_path / "source.db"
    migrate(database)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "lsjson":
            entries = [
                {"Path": f"gumabot-2026010{i}T000000000000Z/verified.json"} for i in range(1, 4)
            ]
            entries.append({"Path": "unrelated/verified.json"})
            return SimpleNamespace(stdout=json.dumps(entries))
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("scripts.backup_offsite.shutil.which", lambda name: "/tools/rclone")
    monkeypatch.setattr("scripts.backup_offsite.subprocess.run", run)
    target = upload(database, "archive:gumabot", keep=2)
    assert target.startswith("archive:gumabot/gumabot-")
    assert [c[1] for c in calls] == ["copy", "check", "copyto", "lsjson", "purge"]
    assert calls[-1][-1].endswith("gumabot-20260101T000000000000Z")


def test_failed_offsite_verification_never_prunes(tmp_path, monkeypatch):
    database = tmp_path / "source.db"
    migrate(database)
    calls = []

    def run(args, **kwargs):
        calls.append(args[1])
        if args[1] == "check":
            raise subprocess.CalledProcessError(1, args)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("scripts.backup_offsite.shutil.which", lambda name: "/tools/rclone")
    monkeypatch.setattr("scripts.backup_offsite.subprocess.run", run)
    with pytest.raises(subprocess.CalledProcessError):
        upload(database, "archive:gumabot")
    assert calls == ["copy", "check"]
