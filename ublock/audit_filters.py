#!/usr/bin/env python3
"""Audit a uBlock Origin supplement against a baseline filter-list directory.

Checks:
- internal exact duplicates
- exact overlaps with the baseline
- normalized network-filter overlaps (option aliases/order)
- cosmetic domain+selector target overlaps
- preprocessor !#if/!#else/!#endif balance

This is deliberately conservative. Arbitrary network-filter subsumption with
wildcards, regexes, redirects, transforms, and exceptions is not claimed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

MARKERS = ("#@#", "#?#", "#$#", "#%#", "#^#", "##")
UNSAFE_OPTION_MODIFIERS = re.compile(
    r"(?:replace|csp|header|permissions|urltransform|removeparam)=", re.I
)
ALIASES = {
    "third-party": "3p",
    "~third-party": "1p",
    "xmlhttprequest": "xhr",
    "stylesheet": "css",
    "subdocument": "frame",
    "document": "doc",
}


def split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    parens = brackets = braces = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == "[":
            brackets += 1
        elif char == "]" and brackets:
            brackets -= 1
        elif char == "(":
            parens += 1
        elif char == ")" and parens:
            parens -= 1
        elif char == "{":
            braces += 1
        elif char == "}" and braces:
            braces -= 1
        elif char == "," and not (parens or brackets or braces):
            item = value[start:index].strip()
            if item:
                parts.append(item)
            start = index + 1
    item = value[start:].strip()
    if item:
        parts.append(item)
    return parts


def marker_of(rule: str) -> tuple[str, int] | None:
    found: list[tuple[int, str]] = []
    for marker in MARKERS:
        index = rule.find(marker)
        if index >= 0:
            found.append((index, marker))
    if not found:
        return None
    index, marker = min(found)
    return marker, index


def cosmetics(rule: str) -> tuple[str, list[str], list[str]] | None:
    found = marker_of(rule)
    if not found:
        return None
    marker, index = found
    domain_text = rule[:index]
    body = rule[index + len(marker):]
    domains = [item.strip() for item in domain_text.split(",") if item.strip()]
    return marker, domains or ["*"], split_top_level(body)


def cosmetic_targets(rule: str) -> set[str]:
    parsed = cosmetics(rule)
    if not parsed:
        return set()
    marker, domains, selectors = parsed
    return {
        f"C:{marker}:{domain}:{selector}"
        for domain in domains
        for selector in selectors
    }


def canonical_network(rule: str) -> str:
    option_index = -1
    for index in range(len(rule) - 1, -1, -1):
        if rule[index] == "$" and (index == 0 or rule[index - 1] != "\\"):
            option_index = index
            break
    if option_index < 0:
        return "N:" + rule
    pattern = rule[:option_index]
    raw_options = rule[option_index + 1:]
    if not raw_options or UNSAFE_OPTION_MODIFIERS.search(raw_options):
        return "N:" + rule
    options: list[str] = []
    for option in split_top_level(raw_options):
        normalized = ALIASES.get(option.lower(), option)
        domain_match = re.fullmatch(r"(~?domain)=(.*)", normalized, re.I)
        if domain_match:
            values = "|".join(sorted(domain_match.group(2).split("|")))
            normalized = f"{domain_match.group(1).lower()}={values}"
        options.append(normalized)
    return "N:" + pattern + "$" + ",".join(sorted(options))


def canonical(rule: str) -> str:
    parsed = cosmetics(rule)
    if parsed:
        marker, domains, selectors = parsed
        return "C:" + marker + ":" + ",".join(sorted(domains)) + ":" + ",".join(selectors)
    return canonical_network(rule)


def active_rules(lines: Iterable[str]) -> list[str]:
    rules: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("!") or line.startswith("["):
            continue
        rules.append(line)
    return rules


def read_filter(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    return text.splitlines(), active_rules(text.splitlines())


def baseline_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files: list[Path] = []
    for candidate in sorted(path.rglob("*")):
        if not candidate.is_file():
            continue
        if candidate.name.lower() == "readme.md":
            continue
        if candidate.suffix.lower() in ("", ".txt"):
            files.append(candidate)
    return files


def check_preprocessor(lines: list[str]) -> list[str]:
    errors: list[str] = []
    stack: list[int] = []
    for line_number, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("!#if"):
            stack.append(line_number)
        elif line.startswith("!#else"):
            if not stack:
                errors.append(f"line {line_number}: !#else without !#if")
        elif line.startswith("!#endif"):
            if not stack:
                errors.append(f"line {line_number}: !#endif without !#if")
            else:
                stack.pop()
    errors.extend(f"line {line_number}: unclosed !#if" for line_number in stack)
    return errors


def summarize(supplement: Path, baseline: Path | None) -> dict[str, object]:
    supplement_lines, supplement_rules = read_filter(supplement)
    counts = Counter(supplement_rules)
    internal_duplicates = sorted(rule for rule, count in counts.items() if count > 1)

    result: dict[str, object] = {
        "supplement": str(supplement),
        "active_rules": len(supplement_rules),
        "unique_active_rules": len(counts),
        "internal_exact_duplicates": internal_duplicates,
        "preprocessor_errors": check_preprocessor(supplement_lines),
    }

    if baseline is None:
        return result

    files = baseline_files(baseline)
    baseline_rules: list[str] = []
    for file in files:
        _, rules = read_filter(file)
        baseline_rules.extend(rules)

    baseline_exact = set(baseline_rules)
    baseline_canonical = {canonical(rule) for rule in baseline_rules}
    baseline_cosmetic = set().union(*(cosmetic_targets(rule) for rule in baseline_rules))

    exact_overlap = sorted(set(supplement_rules) & baseline_exact)
    normalized_overlap = sorted(
        rule for rule in set(supplement_rules)
        if canonical(rule) in baseline_canonical and rule not in baseline_exact
    )
    cosmetic_overlap = sorted(
        target
        for rule in supplement_rules
        for target in cosmetic_targets(rule)
        if target in baseline_cosmetic
    )

    result.update({
        "baseline": str(baseline),
        "baseline_files": len(files),
        "baseline_active_rules": len(baseline_rules),
        "exact_baseline_overlaps": exact_overlap,
        "normalized_baseline_overlaps": normalized_overlap,
        "cosmetic_target_overlaps": cosmetic_overlap,
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("supplement", type=Path)
    parser.add_argument(
        "baseline",
        type=Path,
        nargs="?",
        help="Path to a yokoffing/filterlists checkout or one baseline file",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    report = summarize(args.supplement, args.baseline)
    failures = (
        report["internal_exact_duplicates"]
        or report["preprocessor_errors"]
        or report.get("exact_baseline_overlaps")
        or report.get("normalized_baseline_overlaps")
        or report.get("cosmetic_target_overlaps")
    )

    if args.as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Active rules: {report['active_rules']}")
        print(f"Unique active rules: {report['unique_active_rules']}")
        if args.baseline:
            print(f"Baseline active rules: {report['baseline_active_rules']}")
        for key in (
            "internal_exact_duplicates",
            "preprocessor_errors",
            "exact_baseline_overlaps",
            "normalized_baseline_overlaps",
            "cosmetic_target_overlaps",
        ):
            if key in report:
                print(f"{key.replace('_', ' ').title()}: {len(report[key])}")
                for item in report[key][:20]:
                    print(f"  {item}")
                if len(report[key]) > 20:
                    print(f"  ... {len(report[key]) - 20} more")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

