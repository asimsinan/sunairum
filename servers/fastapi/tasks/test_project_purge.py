"""Hard-delete purge: storage trees + helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tasks.project_purge import (
    find_project_storage_dirs,
    purge_project_files,
    purge_user_storage,
    revoke_project_celery_tasks,
)


class TestProjectPurge(unittest.TestCase):
    def test_finds_canonical_and_orphan_buckets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "user-a" / "proj_abc").mkdir(parents=True)
            (root / "orphan-bucket" / "proj_abc").mkdir(parents=True)
            (root / "user-a" / "other").mkdir(parents=True)
            found = find_project_storage_dirs(str(root), "proj_abc")
            self.assertEqual(len(found), 2)
            self.assertTrue(all("proj_abc" in p for p in found))

    def test_purge_removes_all_matching_dirs_and_revokes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "user-a" / "proj_xyz"
            b = root / "legacy" / "proj_xyz"
            a.mkdir(parents=True)
            b.mkdir(parents=True)
            (a / "status.json").write_text(
                json.dumps({"task_id": "task-111"}), encoding="utf-8"
            )
            revoked: list[str] = []
            result = purge_project_files(
                str(root),
                "proj_xyz",
                preferred_user_id="user-a",
                revoke=revoked.append,
            )
            self.assertTrue(result["ok"], result)
            self.assertFalse(a.exists())
            self.assertFalse(b.exists())
            self.assertIn("task-111", result["revoked_tasks"])
            self.assertEqual(revoked, ["task-111"])
            # Empty user bucket cleaned up.
            self.assertFalse((root / "user-a").exists())

    def test_purge_user_storage_wipes_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = root / "uid-1"
            (user / "proj_1" / "svg_output").mkdir(parents=True)
            (user / "proj_2").mkdir(parents=True)
            out = purge_user_storage(str(root), "uid-1")
            self.assertTrue(out["removed"])
            self.assertFalse(user.exists())

    def test_rejects_path_traversal_project_id(self):
        with self.assertRaises(ValueError):
            find_project_storage_dirs("/tmp", "../etc")


if __name__ == "__main__":
    unittest.main()
