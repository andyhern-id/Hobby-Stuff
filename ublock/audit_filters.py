#!/usr/bin/env python3
"""Audit a uBlock Origin supplement against a baseline filter-list directory.

Checks:
- internal exact duplicates
- exact overlaps with the baseline
- normalized network-filter overlaps (option aliases/order)
- cosmetic same-selector scope coverage (plain parent domains and identical entities)
- generic scriptlets that uBlock Origin ignores
- declared active-rule counts, when present
- preprocessor !#if/!#else/!#endif balance

This is deliberately conservative. Arbitrary network-filter subsumption with
wildcards, regexes, redirects, transforms, and exceptions is not claimed.
"""

from __future__ import annotations

import argparse
import json
import os
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


def domain_applies(
    hostname: str, domains: Iterable[str], *, entity: str | None = None
) -> bool:
    """Match a known hostname against an extended-filter domain list.

    Plain hostname expressions include subdomains; exclusions take precedence.
    Supply the known uBO entity (for example ``mashable`` for mashable.com) to
    evaluate entity expressions. We deliberately do not guess registrable domains
    without a Public Suffix List. Regex expressions use Python's regex dialect;
    unsupported expressions fail closed and are not a uBO-equivalence proof.
    """
    hostname = hostname.lower().rstrip(".")
    values = list(domains)

    def matches(expression: str) -> bool:
        if expression == "*":
            return True
        if expression.startswith("/") and expression.endswith("/"):
            try:
                return re.search(expression[1:-1], hostname) is not None
            except re.error:
                return False
        expression = expression.lower().rstrip(".")
        if expression.endswith(".*"):
            if entity is None:
                return False
            stem = expression[:-2]
            return entity.lower() == stem or entity.lower().endswith("." + stem)
        return hostname == expression or hostname.endswith("." + expression)

    if any(matches(value[1:]) for value in values if value.startswith("~")):
        return False
    positive = [value for value in values if not value.startswith("~")]
    return not positive or any(matches(value) for value in positive)


def _plain_domain(value: str) -> bool:
    return re.fullmatch(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)*", value, re.I) is not None


def _expression_covers(container: str, subject: str) -> bool:
    """Prove domain-set inclusion only for cases understood without a PSL."""
    if container == "*" or container == subject:
        return True
    if _plain_domain(container) and _plain_domain(subject):
        return subject.endswith("." + container)
    return False


def _expressions_may_intersect(left: str, right: str) -> bool:
    if left == "*" or right == "*" or left == right:
        return True
    if _plain_domain(left) and _plain_domain(right):
        return left.endswith("." + right) or right.endswith("." + left)
    # Unknown entity/regex intersections must prevent a false coverage claim.
    return True


def _scope_covers_target(
    baseline_domains: list[str], domain: str, supplement_exclusions: list[str]
) -> bool:
    positive = [value for value in baseline_domains if not value.startswith("~")]
    excluded = [value[1:] for value in baseline_domains if value.startswith("~")]
    if not any(_expression_covers(value, domain) for value in (positive or ["*"])):
        return False
    for exclusion in excluded:
        if not _expressions_may_intersect(domain, exclusion):
            continue
        if not any(_expression_covers(value, exclusion) for value in supplement_exclusions):
            return False
    return True


def covered_cosmetic_targets(
    supplement_rules: Iterable[str], baseline_rules: Iterable[str]
) -> list[str]:
    """Find identical selectors whose supplement domain scope is covered.

    This proves only the supported domain cases, honors exclusions, and does not
    compare different CSS selectors or infer regex/entity intersections.
    """
    baseline_by_selector: dict[tuple[str, str], list[list[str]]] = {}
    for rule in baseline_rules:
        parsed = cosmetics(rule)
        if parsed is None:
            continue
        marker, domains, selectors = parsed
        for selector in selectors:
            baseline_by_selector.setdefault((marker, selector), []).append(domains)
    overlaps: set[str] = set()
    for rule in supplement_rules:
        parsed = cosmetics(rule)
        if parsed is None:
            continue
        marker, domains, selectors = parsed
        positive = [value for value in domains if not value.startswith("~")]
        excluded = [value[1:] for value in domains if value.startswith("~")]
        for domain in positive or ["*"]:
            for selector in selectors:
                candidates = baseline_by_selector.get((marker, selector), [])
                if any(_scope_covers_target(candidate, domain, excluded) for candidate in candidates):
                    overlaps.add(f"C:{marker}:{domain}:{selector}")
    return sorted(overlaps)


def generic_scriptlets(rules: Iterable[str]) -> list[str]:
    ignored: list[str] = []
    for rule in rules:
        parsed = cosmetics(rule)
        if parsed is None:
            continue
        marker, domains, selectors = parsed
        if marker != "##" or not any(value.startswith("+js(") for value in selectors):
            continue
        if not any(value != "*" and not value.startswith("~") for value in domains):
            ignored.append(rule)
    return sorted(ignored)


def check_count_header(lines: list[str], count: int) -> list[str]:
    headers = [line for line in lines if line.startswith("! Active rules in this supplement:")]
    if not headers:
        return []
    expected = f"! Active rules in this supplement: {count}"
    return [] if headers == [expected] else [f"expected exactly one {expected!r} header"]


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
    if not path.exists():
        raise ValueError(f"baseline does not exist: {path}")
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ValueError(f"baseline is not a file or directory: {path}")
    files: list[Path] = []
    for directory, subdirectories, names in os.walk(path):
        subdirectories[:] = sorted(name for name in subdirectories if not name.startswith("."))
        for name in sorted(names):
            candidate = Path(directory) / name
            if name.startswith(".") or not candidate.is_file():
                continue
            if candidate.suffix.lower() in ("", ".txt"):
                files.append(candidate)
    if not files:
        raise ValueError(f"baseline contains no filter files: {path}")
    return sorted(files)


def check_preprocessor(lines: list[str]) -> list[str]:
    errors: list[str] = []
    stack: list[tuple[int, bool]] = []
    for line_number, raw in enumerate(lines, 1):
        line = raw.strip()
        if re.match(r"^!#if(?:\s|$)", line):
            if line == "!#if":
                errors.append(f"line {line_number}: !#if without condition")
            stack.append((line_number, False))
        elif re.match(r"^!#else(?:\s|$)", line):
            if not stack:
                errors.append(f"line {line_number}: !#else without !#if")
            elif stack[-1][1]:
                errors.append(f"line {line_number}: duplicate !#else")
            else:
                stack[-1] = (stack[-1][0], True)
        elif re.match(r"^!#endif(?:\s|$)", line):
            if not stack:
                errors.append(f"line {line_number}: !#endif without !#if")
            else:
                stack.pop()
    errors.extend(f"line {line_number}: unclosed !#if" for line_number, _ in stack)
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
        "generic_scriptlets": generic_scriptlets(supplement_rules),
        "header_errors": check_count_header(supplement_lines, len(supplement_rules)),
    }

    if baseline is None:
        return result

    files = baseline_files(baseline)
    baseline_rules: list[str] = []
    for file in files:
        _, rules = read_filter(file)
        baseline_rules.extend(rules)
    if not baseline_rules:
        raise ValueError(f"baseline contains no active rules: {baseline}")

    baseline_exact = set(baseline_rules)
    baseline_canonical = {canonical(rule) for rule in baseline_rules}

    exact_overlap = sorted(set(supplement_rules) & baseline_exact)
    normalized_overlap = sorted(
        rule for rule in set(supplement_rules)
        if canonical(rule) in baseline_canonical and rule not in baseline_exact
    )
    cosmetic_overlap = covered_cosmetic_targets(supplement_rules, baseline_rules)

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

    try:
        report = summarize(args.supplement, args.baseline)
    except (OSError, UnicodeError, ValueError) as error:
        message = f"Audit input error: {error}"
        if args.as_json:
            print(json.dumps({"error": message}))
        else:
            print(message, file=sys.stderr)
        return 2
    failures = (
        report["internal_exact_duplicates"]
        or report["preprocessor_errors"]
        or report["generic_scriptlets"]
        or report["header_errors"]
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
            "generic_scriptlets",
            "header_errors",
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

