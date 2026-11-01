#!/usr/bin/env python3
"""Deterministically build subscriptions from the published seed and reviewed policy.

The seed preserves historical manual scope edits. It is not a reconstruction of
the original August upstream merge. Refresh candidates require separate review.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

from audit_filters import active_rules, check_preprocessor
from refresh_sources import load_lock, verify_seed

ROOT = Path(__file__).resolve().parent
VERSION = "2026.11.01.2"
MODIFIED = "1 November 2026"
OUTPUTS = {
    "core": ("ubo-no-bullshit-supplement.txt", "No-Bullshit Supplement — Newsletters and Popups"),
    "paywalls": ("ubo-no-bullshit-paywalls.txt", "No-Bullshit Supplement — Optional Paywalls and State Resets"),
    "interface": ("ubo-no-bullshit-interface.txt", "No-Bullshit Supplement — Optional Interface Cleanup"),
}
DESCRIPTIONS = {
    "core": "Newsletter, promotional popup, survey and house-promo filtering. Paywalls and navigation cleanup are separate opt-ins.",
    "paywalls": "Optional paywall, meter and state-reset filters. May erase preferences, log you out or affect site functionality.",
    "interface": "Optional navigation, back-to-top, RSS and membership-trigger cleanup. May hide useful controls.",
}
SECTION_NAMES = {
    "paywall": "PAYWALL / METER / REGISTRATION-WALL SOURCE",
    "promotions": "PROMOTIONS / POPUPS / SURVEYS / HOSTILE UI SOURCE",
    "newsletter": "NEWSLETTER / SUBSCRIBE / EMAIL-CAPTURE SOURCE",
}


@dataclass(frozen=True)
class Entry:
    rule: str
    section: str
    conditions: tuple[tuple[str, bool], ...] = ()


def seed_entries(text: str) -> list[Entry]:
    lines = text.splitlines()
    errors = check_preprocessor(lines)
    if errors:
        raise ValueError("Invalid seed preprocessor: " + "; ".join(errors))
    section: str | None = None
    conditions: list[tuple[str, bool]] = []
    entries = []
    for line in lines:
        line = line.strip()
        if line.startswith("! PAYWALL / METER /"):
            section = "paywall"
        elif line.startswith("! PROMOTIONS / POPUPS /"):
            section = "promotions"
        elif line.startswith("! NEWSLETTER / SUBSCRIBE /"):
            section = "newsletter"
        elif re.match(r"!#if\s+", line):
            conditions.append(("!#if " + re.sub(r"^!#if\s+", "", line), False))
        elif line.startswith("!#else"):
            conditions[-1] = (conditions[-1][0], True)
        elif line.startswith("!#endif"):
            conditions.pop()
        elif active_rules([line]):
            if section is None:
                raise ValueError("Seed rule outside a known source section")
            entries.append(Entry(line.strip(), section, tuple(conditions)))
    duplicates = [rule for rule, n in Counter(e.rule for e in entries).items() if n > 1]
    if not entries or duplicates:
        raise ValueError("Empty or duplicate seed rules: " + repr(duplicates[:3]))
    return entries


def policy_maps(policy: dict, entries: list[Entry]) -> tuple[dict, dict, dict, dict]:
    keys = {"replacements": "from", "disabled": "rule", "interface_rules": "rule", "paywall_rules": "rule"}
    result = []
    seed = {e.rule for e in entries}
    assigned = set()
    for kind, key in keys.items():
        mapped = {}
        for item in policy.get(kind, []):
            rule = item[key]
            if rule not in seed:
                raise ValueError(f"Stale {kind} policy rule: {rule}")
            if rule in mapped or rule in assigned:
                raise ValueError(f"Conflicting/duplicate policy for: {rule}")
            if not item.get("reason", "").strip():
                raise ValueError(f"Missing policy reason: {rule}")
            if kind == "replacements":
                target = item.get("to", "")
                if len(target.splitlines()) != 1 or len(active_rules([target])) != 1 or any(ord(c) < 32 and c != "\t" for c in target):
                    raise ValueError(f"Replacement must contain exactly one active rule: {rule}")
                if "destination" in item and item["destination"] not in OUTPUTS:
                    raise ValueError(f"Unknown replacement destination: {rule}")
            mapped[rule] = item
        assigned.update(mapped)
        result.append(mapped)
    return tuple(result)


def is_state_reset(rule: str) -> bool:
    match = re.search(r"##\+js\(\s*([^,\s)]+)", rule)
    if not match:
        return False
    token = match.group(1).removesuffix(".js")
    return token in {"cookie-remover", "remove-cookie"} or (
        token in {"set-local-storage-item", "set-session-storage-item"}
        and "$remove$" in rule
    )


def route(entry: Entry, interface: dict, paywall: dict | None = None) -> str:
    if entry.section == "paywall" or entry.rule in (paywall or {}):
        return "paywalls"
    if entry.rule in interface:
        return "interface"
    if is_state_reset(entry.rule) or entry.rule.startswith("@@"):
        return "paywalls"
    return "core"


def partition(entries: list[Entry], policy: dict) -> tuple[dict[str, list[Entry]], dict]:
    replacements, disabled, interface, paywall = policy_maps(policy, entries)
    groups: dict[str, list[Entry]] = {name: [] for name in OUTPUTS}
    seen: set[str] = set()
    for entry in entries:
        if entry.rule in disabled:
            continue
        rule = replacements.get(entry.rule, {}).get("to", entry.rule)
        destination = replacements.get(entry.rule, {}).get("destination", route(Entry(rule, entry.section, entry.conditions), interface, paywall))
        if destination == "core" and (entry.section == "paywall" or is_state_reset(rule) or rule.startswith("@@")):
            raise ValueError("Paywall, state-reset and exception replacements must be optional")
        if rule in seen:
            raise ValueError(f"Duplicate generated rule after policy: {rule}")
        seen.add(rule)
        groups[destination].append(Entry(rule, entry.section, entry.conditions))
    additions = policy.get("additions", [])
    for item in additions:
        rule = item["rule"]
        destination = item["destination"]
        section = item["section"]
        if len(rule.splitlines()) != 1 or len(active_rules([rule])) != 1 or any(ord(c) < 32 and c != "\t" for c in rule):
            raise ValueError("Addition must contain one active rule")
        if not item.get("reason", "").strip() or not re.match(r"^https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]{40}/.+", item.get("source", "")):
            raise ValueError("Addition requires a reason and immutable GitHub source URL")
        if destination not in OUTPUTS or section not in SECTION_NAMES:
            raise ValueError("Addition requires a known destination and source section")
        if rule in seen or rule in disabled:
            raise ValueError(f"Duplicate or quarantined addition: {rule}")
        if destination == "core" and (section == "paywall" or is_state_reset(rule) or rule.startswith("@@")):
            raise ValueError("Paywall, state-reset and exception additions must be optional")
        seen.add(rule)
        groups[destination].append(Entry(rule, section))
    if any(not value for value in groups.values()):
        raise ValueError("Every published subscription must be nonempty")
    report = {
        "version": VERSION,
        "seed_rules": len(entries),
        "disabled_rules": len(disabled),
        "replaced_rules": len(replacements),
        "added_rules": len(additions),
        "published_rules": len(seen),
        "lists": {name: len(values) for name, values in groups.items()},
    }
    if report["seed_rules"] + report["added_rules"] != report["published_rules"] + report["disabled_rules"]:
        raise ValueError("Rule accounting mismatch")
    return groups, report


def render(name: str, entries: list[Entry], seed_commit: str) -> str:
    _, title = OUTPUTS[name]
    lines = [
        "[Adblock Plus 2.0]",
        f"! Title: {title}",
        f"! Description: {DESCRIPTIONS[name]}",
        f"! Version: {VERSION}",
        f"! Last modified: {MODIFIED}",
        "! Expires: 1 day (update frequency)",
        "! Homepage: https://github.com/andyhern-id/Hobby-Stuff/tree/main/ublock",
        "! Syntax: uBlock Origin static filters",
        "! License: GPL-3.0-or-later; https://www.gnu.org/licenses/gpl-3.0.html",
        "! Upstream attribution: The EasyList authors (https://easylist.to/) and magnolia1234/BPC.",
        f"! Maintained seed: andyhern-id/Hobby-Stuff @ {seed_commit}",
        "! Generated by build_filters.py from sources/seed.txt and filter-policy.json. Do not edit directly.",
        f"! Active rules in this supplement: {len(entries)}",
        "! Keep uBlock's default lists and uBlock filters – Quick fixes enabled.",
        "! Refreshes retrieve this maintained snapshot; they do not automatically import upstream changes.",
        "! See README.md for optional subscriptions, migration notes and known limitations.",
    ]
    previous: tuple[tuple[str, bool], ...] = ()
    section = None
    for entry in entries:
        common = 0
        if section == entry.section:
            while common < min(len(previous), len(entry.conditions)) and previous[common] == entry.conditions[common]:
                common += 1
        lines.extend("!#endif" for _ in previous[common:])
        if section != entry.section:
            section = entry.section
            lines.extend(["", "! ============================================================================", f"! {SECTION_NAMES[section]}", "! ============================================================================"])
        for condition, otherwise in entry.conditions[common:]:
            lines.append(condition)
            if otherwise:
                lines.append("!#else")
        lines.append(entry.rule)
        previous = entry.conditions
    lines.extend("!#endif" for _ in previous)
    return "\n".join(lines) + "\n"


def build(root: Path = ROOT, *, check: bool = False) -> dict:
    lock = load_lock(root / "sources.lock.json")
    seed_info = lock["seed"]
    raw = verify_seed(lock, root).read_bytes()
    policy = json.loads((root / "filter-policy.json").read_text(encoding="utf-8"))
    groups, report = partition(seed_entries(raw.decode("utf-8")), policy)
    stale = []
    for name, entries in groups.items():
        content = render(name, entries, seed_info["commit"])
        path = root / OUTPUTS[name][0]
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                stale.append(path.name)
        else:
            path.write_text(content, encoding="utf-8")
    if stale:
        raise ValueError("Generated files are stale: " + ", ".join(stale))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify outputs without writing")
    args = parser.parse_args()
    try:
        report = build(check=args.check)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
