"""Safety boundaries and reviewed policy for the published subscriptions.

The historical seed intentionally retains original rules for reproducibility;
only the three generated subscription files are consumer-facing outputs.
"""

from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path

from audit_filters import cosmetics, read_filter


ROOT = Path(__file__).parent
CORE = "ubo-no-bullshit-supplement.txt"
PAYWALLS = "ubo-no-bullshit-paywalls.txt"
INTERFACE = "ubo-no-bullshit-interface.txt"
PUBLISHED = (CORE, PAYWALLS, INTERFACE)
DESTINATIONS = {"core": CORE, "paywalls": PAYWALLS, "interface": INTERFACE}
TUMBLR_RULE = (
    'tumblr.com#?#[style="background-color: rgb(124, 92, 255); '
    'color: rgb(255, 255, 255);"]:has-text(Join over 100 million people)'
)


class PublishedFilterSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.outputs = {name: read_filter(ROOT / name) for name in PUBLISHED}
        cls.rules = {name: set(contents[1]) for name, contents in cls.outputs.items()}
        cls.all_rules = set().union(*cls.rules.values())
        cls.policy = json.loads((ROOT / "filter-policy.json").read_text(encoding="utf-8"))

    def test_each_subscription_has_correct_count_and_no_duplicates(self) -> None:
        for name, (lines, rules) in self.outputs.items():
            with self.subTest(subscription=name):
                self.assertTrue(rules)
                counts = [
                    int(match.group(1)) for line in lines
                    if (match := re.fullmatch(r"! Active rules in this supplement: (\d+)", line))
                ]
                self.assertEqual([len(rules)], counts)
                self.assertEqual(len(rules), len(set(rules)))
        occurrences = Counter(rule for _, rules in self.outputs.values() for rule in rules)
        self.assertEqual([], sorted(rule for rule, count in occurrences.items() if count > 1))

    def test_disabled_rules_do_not_escape_into_optional_lists(self) -> None:
        for item in self.policy["disabled"]:
            with self.subTest(rule=item["rule"]):
                self.assertNotIn(item["rule"], self.all_rules)
                self.assertTrue(item["reason"].strip())

    def test_reviewed_replacements_are_applied(self) -> None:
        for item in self.policy["replacements"]:
            with self.subTest(rule=item["from"]):
                self.assertNotIn(item["from"], self.all_rules)
                self.assertIn(item["to"], self.all_rules)
        self.assertIn(TUMBLR_RULE, self.rules[CORE])
        self.assertIn("##follow-it-form-subscribe", self.rules[CORE])

    def test_reviewed_replacement_destinations_are_respected(self) -> None:
        for item in self.policy["replacements"] + self.policy.get("additions", []):
            destination = item.get("destination")
            if destination is None:
                continue
            rule = item.get("to", item.get("rule"))
            with self.subTest(rule=rule, destination=destination):
                target = DESTINATIONS[destination]
                self.assertIn(rule, self.rules[target])
                for other in PUBLISHED:
                    if other != target:
                        self.assertNotIn(rule, self.rules[other])

    def test_upstream_removed_seed_review_is_complete_and_applied(self) -> None:
        review = json.loads((ROOT / "upstream-review.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
        locked_commits = {source["name"]: source["commit"] for source in lock["upstreams"]}
        replacements = {item["from"]: item for item in self.policy["replacements"]}
        disabled = {item["rule"]: item for item in self.policy["disabled"]}
        resolved = []
        self.assertEqual(1, review["schema_version"])
        for source in review["sources"]:
            self.assertRegex(source["old_commit"], r"^[0-9a-f]{40}$")
            self.assertEqual(locked_commits[source["name"]], source["reviewed_commit"])
            for file in source["files"]:
                for item in file["removed_seed_rules"]:
                    rule = item["rule"]
                    resolved.append(rule)
                    with self.subTest(source=file["path"], rule=rule):
                        self.assertNotIn(rule, self.all_rules)
                        if item["action"] == "replacement":
                            replacement = replacements[rule]
                            self.assertEqual(item["replacement"], replacement["to"])
                            self.assertEqual(item["destination"], replacement["destination"])
                            self.assertIn(item["replacement"], self.rules[DESTINATIONS[item["destination"]]])
                        else:
                            self.assertEqual("quarantine", item["action"])
                            self.assertIn(rule, disabled)
                            self.assertNotIn(rule, replacements)
        # This pinned review identified 50 removed seed entries. Losing a record
        # must not silently turn a complete review into a smaller passing one.
        self.assertEqual(50, len(resolved))
        self.assertEqual(len(resolved), len(set(resolved)))

    def test_unreviewed_upstream_additions_are_not_silently_published(self) -> None:
        review = json.loads((ROOT / "upstream-review.json").read_text(encoding="utf-8"))
        replacement_rules = {item["to"] for item in self.policy["replacements"]}
        independent_additions = {item["rule"]: item for item in self.policy.get("additions", [])}
        for source in review["sources"]:
            for file in source["files"]:
                for item in file["added_rules"]:
                    rule = item["rule"]
                    with self.subTest(source=file["path"], rule=rule):
                        if item["status"] == "used_as_replacement":
                            self.assertIn(rule, replacement_rules)
                            self.assertIn(rule, self.all_rules)
                        else:
                            self.assertEqual("deferred", item["status"])
                            if rule in independent_additions:
                                self.assertTrue(independent_additions[rule]["reason"].strip())
                                self.assertTrue(independent_additions[rule]["source"].strip())
                            else:
                                self.assertNotIn(rule, self.all_rules)

    def test_known_fragments_and_mis_scoped_scriptlets_are_absent(self) -> None:
        self.assertNotIn("page_view_count", self.all_rules)
        self.assertNotIn("follow-it-form-subscribe", self.all_rules)
        for rule in self.all_rules:
            with self.subTest(rule=rule):
                self.assertFalse(rule.startswith("##+js("))
                parsed = cosmetics(rule)
                if parsed:
                    self.assertNotIn("newsnationnow", parsed[1])

    def test_state_reset_and_global_allow_rules_are_opt_in(self) -> None:
        for rule in self.rules[CORE]:
            with self.subTest(rule=rule):
                self.assertNotRegex(rule, r"##\+js\((?:cookie-remover(?:\.js)?|remove-cookie)(?:,|\))")
                if re.search(r"##\+js\(set-(?:local|session)-storage-item,", rule):
                    self.assertNotIn("$remove$", rule)
                if rule.startswith("@@"):
                    self.assertRegex(rule, r"\$(?:.*?,)?(?:domain|from)=")
        self.assertNotIn(
            "! PAYWALL / METER / REGISTRATION-WALL SUPPLEMENT", self.outputs[CORE][0]
        )
        self.assertIn("adweek.com##+js(cookie-remover, blaize_session)", self.rules[PAYWALLS])

    def test_optional_interface_policy_is_routed_out_of_core(self) -> None:
        self.assertTrue(self.policy["interface_rules"])
        for item in self.policy["interface_rules"]:
            rule = item["rule"]
            with self.subTest(rule=rule):
                self.assertNotIn(rule, self.rules[CORE])
                self.assertIn(rule, self.rules[INTERFACE])
        self.assertIn("##.gh-portal-triggerbtn-iframe", self.rules[INTERFACE])

    def test_explicit_access_rules_and_companions_remain_opt_in(self) -> None:
        self.assertTrue(self.policy["paywall_rules"])
        for item in self.policy["paywall_rules"]:
            rule = item["rule"]
            with self.subTest(rule=rule):
                self.assertIn(rule, self.rules[PAYWALLS])
                self.assertNotIn(rule, self.rules[CORE])
                self.assertNotIn(rule, self.rules[INTERFACE])
        # Meter resets and their overlay/scroll companions must move together.
        expected = {
            "theverge.com##.zephr-overlay",
            "theverge.com##.zephr-zone-footer",
            "theverge.com##body:style(position: static !important; overflow: auto !important; width: auto !important;)",
            "theverge.com##+js(aeld, scroll)",
            "theverge.com##+js(cookie-remover.js, blaize_session)",
            "theverge.com##+js(cookie-remover.js, blaize_tracking_id)",
        }
        self.assertLessEqual(expected, self.rules[PAYWALLS])
        self.assertTrue(expected.isdisjoint(self.rules[CORE]))

    def test_legitimate_newsletter_and_popup_filters_remain(self) -> None:
        expected = {
            'mashable.com##[aria-label="Newsletter Sign-Up"]',
            r"mashable.com#?#.md\:p-10:has-text(newsletter)",
            "mashable.com##.bx-impress",
            "mashable.com##body:style(overflow: auto !important; position: initial !important;)",
            "forbes.com###subscribeToNewsLetters",
            "forbes.com##+js(rc, zephr-modal-open, body, stay)",
            "forbes.com##.zephr-editorial-newsletter-backdrop",
            "forbes.com##.zephr-editorial-newsletter-modal",
            "forbes.com##html:style(position: static !important; overflow: auto !important; width: auto !important;)",
        }
        self.assertLessEqual(expected, self.rules[CORE])


if __name__ == "__main__":
    unittest.main()
