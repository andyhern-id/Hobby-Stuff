#!/usr/bin/env python3
"""Verify pinned inputs and prepare review-only upstream refresh candidates.

This does not reconstruct the historical generator or publish new filters. The
vendored seed preserves its manual edits; build_filters.py applies current policy.
Exit codes: 0 success/no content drift, 1 upstream content drift, 2 input/fetch error.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
MAX_BYTES = 10 * 1024 * 1024


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"Unsafe source path: {value!r}")
    return path


def load_lock(path: Path) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1 or not lock.get("upstreams"):
        raise ValueError("Expected source lock schema 1 with nonempty upstreams")
    names = set()
    for source in [dict(lock["seed"], name="seed", files=[lock["seed"]]), *lock["upstreams"]]:
        name = source["name"]
        if not re.fullmatch(r"[a-z0-9_-]+", name) or name in names:
            raise ValueError(f"Invalid or duplicate source name: {name!r}")
        names.add(name)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source["repository"]):
            raise ValueError("Invalid GitHub repository name")
        if not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
            raise ValueError(f"Source {name} must pin a full commit SHA")
        if not source["files"]:
            raise ValueError(f"Source {name} has no locked files")
        seen = set()
        for entry in source["files"]:
            relative_path(entry["path"])
            if entry["path"] in seen:
                raise ValueError(f"Duplicate path in source {name}")
            seen.add(entry["path"])
            if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                raise ValueError("Expected a SHA256 for every locked file")
            if not re.fullmatch(r"[0-9a-f]{40}", entry["git_blob_sha"]):
                raise ValueError("Expected a Git blob SHA for every locked file")
    relative_path(lock["seed"]["local_path"])
    return lock


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Hobby-Stuff-filter-maintenance", "Accept": "application/vnd.github+json" if "api.github.com" in url else "text/plain"})
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read(MAX_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError(f"Fetch failed for {url}: {error}") from error
    if not data.strip() or len(data) > MAX_BYTES:
        raise ValueError(f"Empty or oversized response from {url}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Non-UTF-8 response from {url}") from error
    if re.match(r"\s*(?:<!doctype\s+html|<html\b)", text, re.I):
        raise ValueError(f"HTML response instead of source data from {url}")
    return data


def digest(data: bytes) -> dict[str, str]:
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob_sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
    }


def verify_bytes(data: bytes, entry: dict) -> None:
    if not data.strip():
        raise ValueError(f"Empty locked source: {entry['path']}")
    data.decode("utf-8")
    actual = digest(data)
    if any(actual[key] != entry[key] for key in actual):
        raise ValueError(f"Digest mismatch for {entry['path']}; locked input was not used")


def raw_url(source: dict, path: str, commit: str | None = None) -> str:
    return f"https://raw.githubusercontent.com/{source['repository']}/{commit or source['commit']}/{quote(path, safe='/')}"


def locked_bytes(source: dict, entry: dict, cache: Path) -> bytes:
    # Different reviewed locks can share a cache without mistaking the previous
    # commit's bytes for corruption of the newly promoted input.
    path = cache / "locked" / source["name"] / source["commit"] / relative_path(entry["path"])
    if path.exists():
        data = path.read_bytes()
        verify_bytes(data, entry)
        return data
    data = fetch_bytes(raw_url(source, entry["path"]))
    verify_bytes(data, entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def verify_seed(lock: dict, root: Path) -> Path:
    path = root / relative_path(lock["seed"]["local_path"])
    verify_bytes(path.read_bytes(), lock["seed"])
    return path


def download_locked(lock: dict, cache: Path) -> int:
    """Download external upstreams; the seed is verified locally by the CLI."""
    count = 0
    for source in lock["upstreams"]:
        for entry in source["files"]:
            locked_bytes(source, entry, cache)
            count += 1
    return count


def fetch_json(url: str) -> dict:
    try:
        return json.loads(fetch_bytes(url))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON response from {url}") from error


def filter_paths(tree: dict) -> list[str]:
    if tree.get("truncated"):
        raise ValueError("GitHub tree was truncated; cannot check source inventory")
    return sorted(item["path"] for item in tree["tree"] if item["type"] == "blob"
                  and "/" not in item["path"] and not item["path"].startswith(".")
                  and (item["path"].endswith(".txt") or "." not in item["path"]))


def active_entries(data: bytes) -> set[str]:
    return {line.strip() for line in data.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith(("!", "["))}


def check_upstreams(lock: dict, cache: Path, seed_data: bytes) -> tuple[dict, dict, dict]:
    """Return report, candidate lock, and candidate source bytes; mutate nothing."""
    candidate = copy.deepcopy(lock)
    report = {"changed": False, "sources": [], "limitations": lock.get("legacy_provenance", {}).get("limitations", [])}
    contents = {}
    seed_rules = active_entries(seed_data)
    for source, proposed in zip(lock["upstreams"], candidate["upstreams"]):
        repository = source["repository"]
        branch = quote(source["tracking_ref"], safe="")
        latest = fetch_json(f"https://api.github.com/repos/{repository}/branches/{branch}")["commit"]["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", latest):
            raise ValueError(f"Invalid latest commit for {repository}")
        old_entries = {entry["path"]: entry for entry in source["files"]}
        paths = sorted(old_entries)
        if source.get("discover_root_filters") and latest != source["commit"]:
            paths = filter_paths(fetch_json(f"https://api.github.com/repos/{repository}/git/trees/{latest}?recursive=1"))
            if not paths:
                raise ValueError(f"No filter files found in {repository}")
        summary = {"name": source["name"], "locked_commit": source["commit"], "latest_commit": latest, "files": []}
        new_entries = []
        for path in sorted(set(old_entries) | set(paths)):
            old = locked_bytes(source, old_entries[path], cache) if path in old_entries else b""
            new = (old if latest == source["commit"] else fetch_bytes(raw_url(source, path, latest))) if path in paths else b""
            if path in paths:
                new_entries.append(dict(path=path, **digest(new)))
                contents[(source["name"], path)] = new
            if old == new:
                continue
            removed = active_entries(old) - active_entries(new)
            added = active_entries(new) - active_entries(old)
            summary["files"].append({
                "path": path,
                "status": "added" if not old else "removed" if not new else "modified",
                "added_rules": sorted(added), "removed_rules": sorted(removed),
                "removed_rules_still_in_seed": sorted(removed & seed_rules),
                "diff": "".join(difflib.unified_diff(old.decode("utf-8").splitlines(keepends=True), new.decode("utf-8").splitlines(keepends=True), fromfile=f"locked/{path}", tofile=f"candidate/{path}")),
            })
            report["changed"] = True
        proposed["commit"] = latest
        proposed["files"] = new_entries
        report["sources"].append(summary)
    return report, candidate, contents


def write_candidate(directory: Path, report: dict, lock: dict, contents: dict, active_lock: Path) -> None:
    if (directory / "sources.lock.json").resolve() == active_lock.resolve():
        raise ValueError("Candidate directory would overwrite the active lock")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Candidate directory must be new or empty; refusing to overwrite files")
    directory.mkdir(parents=True, exist_ok=True)
    for (source, path), data in contents.items():
        destination = directory / "upstreams" / source / relative_path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    for name, value in (("sources.lock.json", lock), ("changes.json", report)):
        (directory / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=HERE / "sources.lock.json")
    parser.add_argument("--cache", type=Path, default=HERE / ".cache" / "sources")
    parser.add_argument("--verify-seed", action="store_true", help="Verify vendored seed offline")
    parser.add_argument("--download", action="store_true", help="Download and verify immutable locked inputs")
    parser.add_argument("--check", action="store_true", help="Report upstream file changes without publishing")
    parser.add_argument("--candidate", type=Path, help="Write a separate candidate lock/sources/report; requires --check")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    if args.candidate and not args.check:
        parser.error("--candidate requires --check")
    if not any((args.verify_seed, args.download, args.check)):
        parser.error("Choose --verify-seed, --download, or --check")
    try:
        lock = load_lock(args.lock)
        result = {}
        if args.verify_seed or args.download or args.check:
            seed_path = verify_seed(lock, args.lock.parent)
            result["seed_verified"] = str(seed_path)
        if args.download:
            result["locked_files_verified"] = download_locked(lock, args.cache)
            result["verified_pins"] = result["locked_files_verified"] + 1
        if args.check:
            report, candidate, contents = check_upstreams(lock, args.cache, seed_path.read_bytes())
            result["upstream_check"] = report
            if args.candidate:
                write_candidate(args.candidate, report, candidate, contents, args.lock)
                result["candidate_directory"] = str(args.candidate)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Source verification failed: {error}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if "seed_verified" in result:
            print("Vendored seed verified")
        if "locked_files_verified" in result:
            print(f"Verified {result['locked_files_verified']} locked upstream files in {args.cache / 'locked'} ({result['verified_pins']} pins including vendored seed)")
        if args.check:
            for source in report["sources"]:
                print(f"{source['name']}: {len(source['files'])} changed files ({source['locked_commit'][:12]} -> {source['latest_commit'][:12]})")
                for entry in source["files"]:
                    print(f"  {entry['status']}: {entry['path']} (+{len(entry['added_rules'])}/-{len(entry['removed_rules'])} rules)")
            print("Review required; seed, policy, subscriptions, and active lock were not changed.")
            if args.candidate:
                print(f"Candidate written to {args.candidate}")
    return 1 if args.check and report["changed"] else 0


if __name__ == "__main__":
    sys.exit(main())
