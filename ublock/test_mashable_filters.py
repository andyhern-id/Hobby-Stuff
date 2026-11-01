"""Static regressions for Mashable's October 2026 site-break correction.

Upstream disabled two rules (six selector arms) in:
https://github.com/yokoffing/filterlists/commit/4e17e52627486f7e2e96fa43cd78b26bd173c260

These checks protect the supplement's filter configuration. They do not replace
live-page testing with uBlock Origin or prove arbitrary CSS equivalence.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from audit_filters import cosmetics, read_filter


SUPPLEMENT = Path(__file__).with_name("ubo-no-bullshit-supplement.txt")
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


def mashable_hiding_targets(rules: list[str]) -> set[tuple[str, str]]:
    """Read active hiding rules applicable to mashable.com, including grouped rules."""
    targets: set[tuple[str, str]] = set()
    for rule in rules:
        parsed = cosmetics(rule)
        if parsed is None:
            continue
        marker, domains, selectors = parsed
        if marker not in ("##", "#?#"):
            continue
        if "~mashable.com" in domains or "~com" in domains:
            continue
        included = [domain for domain in domains if not domain.startswith("~")]
        if included and not {"*", "com", "mashable.com"}.intersection(included):
            continue
        targets.update((marker, selector) for selector in selectors)
    return targets


class MashableFilterRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lines, cls.rules = read_filter(SUPPLEMENT)
        cls.targets = mashable_hiding_targets(cls.rules)

    def test_no_max_w_9xl_hiding_on_mashable(self) -> None:
        # Also rejects the class within compound or comma-separated selectors.
        # Replacing the broad rule with upstream's disabled compound is unsafe.
        offenders = sorted(
            selector
            for _, selector in self.targets
            if re.search(r"(?<!\\)\.max-w-9xl(?![\w-])", selector)
        )
        self.assertEqual([], offenders, "Mashable layout class must not be hidden")

    def test_upstream_disabled_selectors_stay_disabled(self) -> None:
        selectors = {selector for _, selector in self.targets}
        self.assertEqual(set(), selectors & DISABLED_UPSTREAM_SELECTORS)

    def test_existing_targeted_filters_are_preserved(self) -> None:
        for target in sorted(PRESERVED_TARGETS):
            with self.subTest(target=target):
                self.assertIn(target, self.targets)

    def test_active_rule_count_matches_header(self) -> None:
        counts = [
            int(match.group(1))
            for line in self.lines
            if (match := re.fullmatch(r"! Active rules in this supplement: (\d+)", line))
        ]
        self.assertEqual([len(self.rules)], counts)


if __name__ == "__main__":
    unittest.main()
