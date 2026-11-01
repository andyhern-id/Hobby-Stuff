"""Tests for lossless routing, explicit policy and deterministic generation."""

import unittest

from audit_filters import active_rules, check_preprocessor
from build_filters import Entry, partition, render, seed_entries


class BuildTests(unittest.TestCase):
    def test_split_rebuilds_conditional_context(self):
        text = """! PAYWALL / METER / TEST
!#if ext_ublock
a.example##.paywall
!#else
b.example##.paywall
!#endif
! PROMOTIONS / POPUPS / TEST
!#if env_firefox
!#if ext_ublock
c.example##.popup
!#else
d.example##.popup
!#endif
!#endif
! NEWSLETTER / SUBSCRIBE / TEST
e.example##.newsletter
"""
        entries = seed_entries(text)
        for name in ("core", "paywalls", "interface"):
            generated = render(name, entries, "a" * 40)
            self.assertEqual([], check_preprocessor(generated.splitlines()))
            self.assertEqual(entries, seed_entries(generated))

    def test_explicit_policy_preserves_accounting_and_optional_companions(self):
        entries = [Entry("a.example##.wall", "paywall"), Entry("##.backtop", "promotions"),
                   Entry("@@||a.example/backtop.js$script", "promotions"),
                   Entry("b.example##+js(cookie-remover, meter)", "newsletter"),
                   Entry("c.example##.newsletter", "newsletter"),
                   Entry("stray_fragment", "newsletter")]
        policy = {"disabled": [{"rule": "stray_fragment", "reason": "bad input"}],
                  "interface_rules": [{"rule": entry.rule, "reason": "optional navigation"} for entry in entries[1:3]]}
        groups, report = partition(entries, policy)
        self.assertEqual([entries[0], entries[3]], groups["paywalls"])
        self.assertEqual(entries[1:3], groups["interface"])
        self.assertEqual([entries[4]], groups["core"])
        self.assertEqual(6, report["published_rules"] + report["disabled_rules"])

    def test_stale_or_conflicting_policy_is_not_silently_ignored(self):
        entries = [Entry("##.newsletter", "newsletter")]
        for policy in ({"disabled": [{"rule": "missing", "reason": "stale"}]},
                       {"disabled": [{"rule": "##.newsletter", "reason": "unsafe"}],
                        "interface_rules": [{"rule": "##.newsletter", "reason": "conflict"}]}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                partition(entries, policy)

    def test_multiline_replacement_cannot_inject_rules(self):
        for target in ("##.newsletter\n##.content", "!#if ext_ublock\r##.content", "##.content\n", "##.content\x00"):
            policy = {"replacements": [{"from": "##.newsletter", "to": target, "reason": "bad"}]}
            with self.subTest(target=target), self.assertRaises(ValueError):
                partition([Entry("##.newsletter", "newsletter")], policy)

    def test_indented_and_tab_separated_conditions_are_preserved(self):
        entries = seed_entries("! NEWSLETTER / SUBSCRIBE / TEST\n  !#if\text_ublock\n##.newsletter\n  !#endif\n")
        self.assertEqual((("!#if ext_ublock", False),), entries[0].conditions)
        self.assertIn("!#if ext_ublock\n##.newsletter\n!#endif", render("core", entries, "a" * 40))

    def test_state_reset_replacement_is_routed_using_result(self):
        entries = [Entry("##.newsletter", "newsletter"), Entry("##.popup", "promotions"), Entry("##.backtop", "promotions")]
        reset = "example.com##+js(cookie-remover, /^/)"
        policy = {"replacements": [{"from": "##.popup", "to": reset, "reason": "test routing"}],
                  "interface_rules": [{"rule": "##.backtop", "reason": "navigation"}]}
        groups, _ = partition(entries, policy)
        self.assertEqual([reset], [e.rule for e in groups["paywalls"]])
        self.assertNotIn(reset, [e.rule for e in groups["core"]])
        policy["replacements"][0]["destination"] = "core"
        with self.assertRaises(ValueError):
            partition(entries, policy)

    def test_reviewed_upstream_additions_need_provenance_and_safe_routing(self):
        entries = [Entry("a.example##.wall", "paywall"), Entry("##.newsletter", "newsletter"), Entry("##.backtop", "promotions")]
        addition = {"rule": "b.example##.newsletter", "section": "newsletter", "destination": "core", "reason": "Reviewed upstream fix", "source": "https://github.com/example/filters/blob/" + "a" * 40 + "/newsletters.txt"}
        policy = {"interface_rules": [{"rule": "##.backtop", "reason": "navigation"}], "additions": [addition]}
        groups, report = partition(entries, policy)
        self.assertIn(addition["rule"], [e.rule for e in groups["core"]])
        self.assertEqual(1, report["added_rules"])
        for override in ({"source": "https://github.com/example/filters/blob/main/newsletters.txt"},
                         {"rule": "b.example##+js(remove-cookie, /^/)"},
                         {"rule": "##.newsletter"}):
            policy["additions"] = [dict(addition, **override)]
            with self.subTest(override=override), self.assertRaises(ValueError):
                partition(entries, policy)


if __name__ == "__main__":
    unittest.main()
