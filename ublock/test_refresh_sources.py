"""Refresh inputs must be reproducible; upstream drift must remain review-only."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import refresh_sources as refresh


OLD = b"example.com##.removed\n"
NEW = b"example.com##.replacement\n"
ADDED = b"example.org##.newsletter\n"


def sample_lock() -> dict:
    return {
        "schema_version": 1,
        "seed": dict(repository="owner/repo", commit="1" * 40, path="seed.txt",
                     local_path="sources/seed.txt", **refresh.digest(OLD)),
        "upstreams": [{
            "name": "baseline", "repository": "owner/baseline", "tracking_ref": "main",
            "commit": "2" * 40, "discover_root_filters": True,
            "files": [dict(path="filters.txt", **refresh.digest(OLD))],
        }],
    }


class RefreshSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.lock = sample_lock()
        self.lock_path = self.root / "sources.lock.json"
        self.lock_path.write_text(json.dumps(self.lock))
        seed = self.root / "sources/seed.txt"
        seed.parent.mkdir()
        seed.write_bytes(OLD)
        cached = self.cache / "locked/baseline" / ("2" * 40) / "filters.txt"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(OLD)

    def test_local_seed_is_verified_without_network(self) -> None:
        with patch.object(refresh, "fetch_bytes", side_effect=AssertionError("network")):
            loaded = refresh.load_lock(self.lock_path)
            self.assertEqual(OLD, refresh.verify_seed(loaded, self.root).read_bytes())
        (self.root / "sources/seed.txt").write_bytes(NEW)
        with self.assertRaisesRegex(ValueError, "Digest mismatch"):
            refresh.verify_seed(loaded, self.root)

    def test_corrupt_cache_is_not_silently_accepted_or_overwritten(self) -> None:
        source = self.lock["upstreams"][0]
        cache_file = self.cache / "locked/baseline" / ("2" * 40) / "filters.txt"
        cache_file.write_bytes(NEW)
        with patch.object(refresh, "fetch_bytes", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(ValueError, "Digest mismatch"):
                refresh.locked_bytes(source, source["files"][0], self.cache)
        self.assertEqual(NEW, cache_file.read_bytes())

    def test_promoted_lock_can_share_cache_with_previous_commit(self) -> None:
        source = self.lock["upstreams"][0]
        promoted = copy.deepcopy(source)
        promoted["commit"] = "3" * 40
        promoted["files"] = [dict(path="filters.txt", **refresh.digest(NEW))]
        with patch.object(refresh, "fetch_bytes", return_value=NEW) as fetch:
            result = refresh.locked_bytes(promoted, promoted["files"][0], self.cache)
        self.assertEqual(NEW, result)
        self.assertIn("/" + "3" * 40 + "/filters.txt", fetch.call_args.args[0])
        self.assertEqual(OLD, (self.cache / "locked/baseline" / ("2" * 40) / "filters.txt").read_bytes())
        self.assertEqual(NEW, (self.cache / "locked/baseline" / ("3" * 40) / "filters.txt").read_bytes())
        with patch.object(refresh, "fetch_bytes", side_effect=AssertionError("network")):
            self.assertEqual(OLD, refresh.locked_bytes(source, source["files"][0], self.cache))
            self.assertEqual(NEW, refresh.locked_bytes(promoted, promoted["files"][0], self.cache))

    def test_download_uses_full_locked_commit_and_checks_digest(self) -> None:
        source = self.lock["upstreams"][0]
        with patch.object(refresh, "fetch_bytes", return_value=OLD) as fetch:
            empty_cache = self.root / "fresh-cache"
            result = refresh.locked_bytes(source, source["files"][0], empty_cache)
        self.assertEqual(OLD, result)
        self.assertIn("/" + "2" * 40 + "/filters.txt", fetch.call_args.args[0])
        with patch.object(refresh, "fetch_bytes", return_value=NEW):
            with self.assertRaisesRegex(ValueError, "Digest mismatch"):
                refresh.locked_bytes(source, source["files"][0], self.root / "bad-download")
        self.assertFalse((self.root / "bad-download").exists())

    def test_http_failures_and_non_source_responses_fail_closed(self) -> None:
        for body in (b"", b"   \n", b"<html>Error</html>", b"\xff"):
            with self.subTest(body=body):
                with patch.object(refresh, "urlopen", return_value=io.BytesIO(body)):
                    with self.assertRaises(ValueError):
                        refresh.fetch_bytes("https://raw.githubusercontent.com/owner/repo/commit/file")
        with patch.object(refresh, "urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(ValueError, "Fetch failed"):
                refresh.fetch_bytes("https://raw.githubusercontent.com/owner/repo/commit/file")

    def test_drift_and_new_files_make_a_separate_review_candidate(self) -> None:
        before = copy.deepcopy(self.lock)
        def api(url: str) -> dict:
            if "/branches/" in url:
                return {"commit": {"sha": "3" * 40}}
            return {"tree": [{"type": "blob", "path": "filters.txt"},
                             {"type": "blob", "path": "new.txt"},
                             {"type": "blob", "path": "README.md"}], "truncated": False}
        def download(url: str) -> bytes:
            self.assertIn("/" + "3" * 40 + "/", url)
            return NEW if url.endswith("filters.txt") else ADDED
        with patch.object(refresh, "fetch_json", side_effect=api), patch.object(refresh, "fetch_bytes", side_effect=download):
            report, candidate, contents = refresh.check_upstreams(self.lock, self.cache, OLD)
        self.assertTrue(report["changed"])
        self.assertEqual(before, self.lock)
        changes = report["sources"][0]["files"]
        self.assertEqual(["modified", "added"], [entry["status"] for entry in changes])
        self.assertEqual(["example.com##.removed"], changes[0]["removed_rules_still_in_seed"])
        self.assertEqual(self.lock["seed"], candidate["seed"])
        self.assertEqual("3" * 40, candidate["upstreams"][0]["commit"])
        destination = self.root / "candidate"
        refresh.write_candidate(destination, report, candidate, contents, self.lock_path)
        self.assertEqual(OLD, (self.root / "sources/seed.txt").read_bytes())
        self.assertEqual(before, json.loads(self.lock_path.read_text()))
        self.assertEqual(NEW, (destination / "upstreams/baseline/filters.txt").read_bytes())
        self.assertTrue((destination / "changes.json").exists())

    def test_removed_source_is_reported_and_not_carried_into_candidate(self) -> None:
        api = [{"commit": {"sha": "3" * 40}},
               {"tree": [{"type": "blob", "path": "new.txt"}], "truncated": False}]
        with patch.object(refresh, "fetch_json", side_effect=api), patch.object(refresh, "fetch_bytes", return_value=ADDED):
            report, candidate, contents = refresh.check_upstreams(self.lock, self.cache, OLD)
        self.assertEqual(["removed", "added"], [item["status"] for item in report["sources"][0]["files"]])
        self.assertEqual(["new.txt"], [item["path"] for item in candidate["upstreams"][0]["files"]])
        self.assertNotIn(("baseline", "filters.txt"), contents)

    def test_unchanged_commit_uses_verified_cache(self) -> None:
        with patch.object(refresh, "fetch_json", return_value={"commit": {"sha": "2" * 40}}), patch.object(refresh, "fetch_bytes", side_effect=AssertionError("network")):
            report, candidate, contents = refresh.check_upstreams(self.lock, self.cache, OLD)
        self.assertFalse(report["changed"])
        self.assertEqual(OLD, contents[("baseline", "filters.txt")])
        self.assertEqual(self.lock, candidate)

    def test_candidate_refuses_to_overwrite_active_lock_or_existing_files(self) -> None:
        with self.assertRaisesRegex(ValueError, "active lock"):
            refresh.write_candidate(self.root, {}, self.lock, {}, self.lock_path)
        existing = self.root / "existing"
        existing.mkdir()
        (existing / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            refresh.write_candidate(existing, {}, self.lock, {}, self.lock_path)
        self.assertEqual("keep", (existing / "keep.txt").read_text())

    def test_manifest_rejects_path_traversal_and_unpinned_commits(self) -> None:
        for field, value in (("commit", "main"), ("local_path", "../seed.txt")):
            modified = copy.deepcopy(self.lock)
            modified["seed"][field] = value
            self.lock_path.write_text(json.dumps(modified))
            with self.subTest(field=field), self.assertRaises(ValueError):
                refresh.load_lock(self.lock_path)

    def test_truncated_or_empty_inventory_cannot_look_clean(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncated"):
            refresh.filter_paths({"tree": [], "truncated": True})
        api = [{"commit": {"sha": "3" * 40}}, {"tree": [], "truncated": False}]
        with patch.object(refresh, "fetch_json", side_effect=api):
            with self.assertRaisesRegex(ValueError, "No filter files"):
                refresh.check_upstreams(self.lock, self.cache, OLD)

    def test_cli_returns_error_for_invalid_seed(self) -> None:
        (self.root / "sources/seed.txt").write_bytes(NEW)
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = refresh.main(["--lock", str(self.lock_path), "--verify-seed"])
        self.assertEqual(2, result)
        self.assertIn("Digest mismatch", stderr.getvalue())

    def test_cli_download_verifies_local_seed_before_network(self) -> None:
        (self.root / "sources/seed.txt").write_bytes(NEW)
        with patch.object(refresh, "fetch_bytes", side_effect=AssertionError("network")) as fetch:
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                result = refresh.main(["--lock", str(self.lock_path), "--cache", str(self.root / "fresh"), "--download"])
        self.assertEqual(2, result)
        self.assertIn("Digest mismatch", stderr.getvalue())
        fetch.assert_not_called()

    def test_cli_download_fetches_only_upstreams_and_counts_local_seed(self) -> None:
        lock_before = self.lock_path.read_bytes()
        def download(url: str) -> bytes:
            self.assertIn("/owner/baseline/", url)
            self.assertNotIn("/owner/repo/", url)
            return OLD
        with patch.object(refresh, "fetch_bytes", side_effect=download) as fetch:
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                result = refresh.main(["--lock", str(self.lock_path), "--cache", str(self.root / "fresh"), "--download", "--json"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(1, report["locked_files_verified"])
        self.assertEqual(2, report["verified_pins"])
        self.assertIn("seed_verified", report)
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(lock_before, self.lock_path.read_bytes())
        self.assertEqual(OLD, (self.root / "sources/seed.txt").read_bytes())


if __name__ == "__main__":
    unittest.main()
