"""Configuration regressions for Mashable's October 2026 site-break correction.

Upstream disabled two rules (six selector arms) in:
https://github.com/yokoffing/filterlists/commit/4e17e52627486f7e2e96fa43cd78b26bd173c260

These checks cover the published subscriptions, including optional lists. They do
not replace live-page testing or prove arbitrary CSS/hostname-regex equivalence.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from audit_filters import active_rules, cosmetics, domain_applies, read_filter


ROOT = Path(__file__).parent
SUPPLEMENT = ROOT / "ubo-no-bullshit-supplement.txt"
PUBLISHED = (
    SUPPLEMENT,
    ROOT / "ubo-no-bullshit-paywalls.txt",
    ROOT / "ubo-no-bullshit-interface.txt",
)
DISABLED_UPSTREAM_SELECTORS = {
    r".bg-warmgray-100.items-end.md\:flex-row.flex-col.flex.overflow-hidden.relative.px-4.mx-auto.mt-12.max-w-9xl",
    r".md\:mb-16.md\:mt-12.mb-12.mt-8.font-sans.text-primary-400.max-w-3xl.mx-auto.w-full",
    "section.max-w-8xl.mx-auto:nth-of-type(1)",
    r"div.lg\:flex.justify-between.items-stretch.mx-auto.px-4.max-w-8xl",
    ".related-stories",
    r".md\:leading-7.md\:text-xl.leading-loose.text-lg.mt-8.font-sans.max-w-3xl.mx-auto.w-full",
}
PRESERVED_TARGETS = {
    ("##", ".border-secondary-300"),
    ("##", ".border-warmgray-100"),
    ("##", '[aria-label="Newsletter Sign-Up"]'),
    ("#?#", r".md\:p-10:has-text(newsletter)"),
    ("##", ".bx-impress"),
    ("##", "body:style(overflow: auto !important; position: initial !important;)"),
}


def mashable_hiding_targets(lines: list[str]) -> set[tuple[str, str]]:
    """Return hiding targets that apply to Mashable or explicit subdomains."""
    targets: set[tuple[str, str]] = set()
    for rule in active_rules(lines):
        parsed = cosmetics(rule)
        if parsed is None:
            continue
        marker, domains, selectors = parsed
        if marker not in ("##", "#?#"):
            continue
        hostnames = {"mashable.com", "www.mashable.com"}
        hostnames.update(
            domain for domain in domains
            if domain.endswith(".mashable.com") and not domain.startswith("~")
        )
        if any(domain_applies(host, domains, entity="mashable") for host in hostnames):
            targets.update((marker, selector) for selector in selectors)
    return targets


def unsafe_mashable_selectors(lines: list[str]) -> set[str]:
    return {
        selector
        for _, selector in mashable_hiding_targets(lines)
        if selector in DISABLED_UPSTREAM_SELECTORS
        or re.search(r"(?<!\\)\.max-w-9xl(?![\w-])", selector)
    }


class MashableFilterRegressionTests(unittest.TestCase):
    def test_unsafe_selectors_absent_from_every_subscription(self) -> None:
        for path in PUBLISHED:
            with self.subTest(subscription=path.name):
                lines, _ = read_filter(path)
                self.assertEqual(set(), unsafe_mashable_selectors(lines))

    def test_targeted_filters_remain_in_core(self) -> None:
        lines, _ = read_filter(SUPPLEMENT)
        self.assertLessEqual(PRESERVED_TARGETS, mashable_hiding_targets(lines))

    def test_mutations_detect_host_entity_regex_and_grouped_rules(self) -> None:
        domains = (
            "mashable.com", "www.mashable.com", "news.mashable.com", "com", "",
            "other.example,mashable.com", "mashable.*", "other.example,mashable.*",
            r"/^mashable\.com$/", "~other.example",
        )
        for domain in domains:
            for selector in DISABLED_UPSTREAM_SELECTORS | {".max-w-9xl"}:
                with self.subTest(domain=domain, selector=selector):
                    rule = f"{domain}##.unrelated, {selector}"
                    self.assertIn(selector, unsafe_mashable_selectors([rule]))

    def test_comments_exclusions_and_unrelated_domains_are_not_false_positives(self) -> None:
        lines = [
            "! mashable.com##.max-w-9xl",
            "other.example##.max-w-9xl",
            "~mashable.com##.max-w-9xl",
            "com,~mashable.*##.max-w-9xl",
            r"/^other\.example$/##.max-w-9xl",
            "mashable.com#@#.max-w-9xl",
            "mashable.com##.max-w-9xl-card",
        ]
        self.assertEqual(set(), unsafe_mashable_selectors(lines))


if __name__ == "__main__":
    unittest.main()
