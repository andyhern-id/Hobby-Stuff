"""Regression coverage for audit input handling and conservative scope checks."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audit_filters import (
    active_rules,
    check_count_header,
    check_preprocessor,
    covered_cosmetic_targets,
    domain_applies,
    generic_scriptlets,
    summarize,
)


class BaselineInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.supplement = self.root / "supplement.txt"
        self.supplement.write_text("example.org##.newsletter\n", encoding="utf-8")
        self.baseline = self.root / "baseline"
        self.baseline.mkdir()

    def test_checkout_metadata_and_hidden_directories_are_not_filter_inputs(self) -> None:
        (self.baseline / "filters.txt").write_text("example.net##.newsletter\n")
        for relative in (".git/index", ".git/objects/ab/object", ".cache/snapshot"):
            path = self.baseline / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x80binary git metadata\x00")
        report = summarize(self.supplement, self.baseline)
        self.assertEqual(1, report["baseline_files"])
        self.assertEqual(1, report["baseline_active_rules"])

    def test_missing_empty_and_comment_only_baselines_fail(self) -> None:
        for path in (self.root / "missing", self.baseline):
            with self.subTest(path=path), self.assertRaises(ValueError):
                summarize(self.supplement, path)
        (self.baseline / "filters.txt").write_text("! only a comment\n")
        with self.assertRaisesRegex(ValueError, "no active rules"):
            summarize(self.supplement, self.baseline)

    def test_invalid_baseline_has_nonzero_machine_readable_cli_error(self) -> None:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("audit_filters.py")),
             str(self.supplement), str(self.root / "missing"), "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("baseline does not exist", json.loads(result.stdout)["error"])
        self.assertNotIn("Traceback", result.stderr)


class DomainScopeTests(unittest.TestCase):
    def test_hostname_matching_honors_parent_domains_and_exclusions(self) -> None:
        self.assertTrue(domain_applies("www.mashable.com", ["mashable.com"]))
        self.assertTrue(domain_applies("mashable.com", ["com"]))
        self.assertFalse(domain_applies("notmashable.com", ["mashable.com"]))
        self.assertFalse(domain_applies("mashable.com", ["*", "~mashable.com"]))
        self.assertTrue(domain_applies("mashable.com", ["~other.example"]))

    def test_known_entities_and_regex_domains(self) -> None:
        self.assertTrue(domain_applies("mashable.com", ["mashable.*"], entity="mashable"))
        self.assertFalse(domain_applies("mashable.com", ["*", "~mashable.*"], entity="mashable"))
        self.assertFalse(domain_applies("mashable.evil.biz", ["mashable.*"], entity="evil"))
        self.assertTrue(domain_applies("mashable.com", [r"/^mashable\.com$/"]))
        self.assertFalse(domain_applies("mashable.com", ["*", r"~/^mashable\.com$/"]))

    def test_parent_and_generic_rules_cover_identical_selectors(self) -> None:
        supplement = ["sub.example.com##.newsletter", "another.example##.popup"]
        baseline = ["example.com##.newsletter", "##.popup"]
        self.assertEqual(
            ["C:##:another.example:.popup", "C:##:sub.example.com:.newsletter"],
            covered_cosmetic_targets(supplement, baseline),
        )

    def test_baseline_exclusion_prevents_false_coverage(self) -> None:
        baseline = ["example.com,~premium.example.com##.newsletter"]
        self.assertEqual([], covered_cosmetic_targets(["example.com##.newsletter"], baseline))
        self.assertEqual([], covered_cosmetic_targets(["premium.example.com##.newsletter"], baseline))
        self.assertEqual(
            ["C:##:example.com:.newsletter"],
            covered_cosmetic_targets(["example.com,~premium.example.com##.newsletter"], baseline),
        )

    def test_negated_scopes_and_identical_entities_are_compared_conservatively(self) -> None:
        self.assertEqual(
            ["C:##:*:.newsletter"],
            covered_cosmetic_targets(["~example.com##.newsletter"], ["##.newsletter"]),
        )
        self.assertEqual(
            ["C:##:mashable.*:.newsletter"],
            covered_cosmetic_targets(["mashable.*##.newsletter"], ["mashable.*##.newsletter"]),
        )
        self.assertEqual([], covered_cosmetic_targets(
            ["example.com##.newsletter"], ["example.*,~premium.example.com##.newsletter"]
        ))

    def test_different_selectors_are_not_claimed_equivalent(self) -> None:
        self.assertEqual([], covered_cosmetic_targets(
            ["example.com##.newsletter.large"], ["example.com##.newsletter"]
        ))


class StructuralAuditTests(unittest.TestCase):
    def test_generic_scriptlets_are_reported_but_comments_and_specific_rules_are_not(self) -> None:
        rules = active_rules([
            "! ##+js(rc, popup)", "##+js(rc, popup)",
            "~example.com##+js(rc, popup)", "example.com##+js(rc, popup)",
        ])
        self.assertEqual(["##+js(rc, popup)", "~example.com##+js(rc, popup)"], generic_scriptlets(rules))

    def test_duplicate_else_is_invalid_and_nested_conditionals_are_valid(self) -> None:
        self.assertEqual(["line 3: duplicate !#else"], check_preprocessor(
            ["!#if ext_ublock", "!#else", "!#else", "!#endif"]
        ))
        self.assertEqual([], check_preprocessor([
            "!#if ext_ublock", "!#if env_firefox", "!#else", "!#endif", "!#else", "!#endif",
        ]))

    def test_count_headers_must_be_unique_and_accurate_when_present(self) -> None:
        valid = "! Active rules in this supplement: 2"
        self.assertEqual([], check_count_header([valid], 2))
        self.assertTrue(check_count_header([valid], 1))
        self.assertTrue(check_count_header([valid, valid], 2))
        self.assertEqual([], check_count_header([], 2))


if __name__ == "__main__":
    unittest.main()
