# No-Bullshit uBlock Origin Supplement — audit

Generated on 22 August 2026 as an additive list for
[yokoffing/filterlists](https://github.com/yokoffing/filterlists), baseline commit
[`80d1341d220a773424a4644a2b52eb62a94b1b8f`](https://github.com/yokoffing/filterlists/commit/80d1341d220a773424a4644a2b52eb62a94b1b8f).

## Hardening release 2026.11.01.2 — 1 November 2026

The published rules are now split into independent subscriptions:

| Subscription | Active rule entries |
| --- | ---: |
| Core newsletters and popups, at the original URL | 8,131 |
| Optional paywalls and state resets | 787 |
| Optional interface cleanup | 1,080 |
| **Total across all three** | **9,998** |

The previous 10,062-entry list is preserved as the checksum-pinned maintenance
seed. Exact policy decisions replace 44 entries and quarantine 64, with no
independent additions. Every seed entry is accounted for, and outputs have no
internal or cross-list exact duplicates. Related content-gate, cookie-reset and
scroll-repair rules are routed together; newsletter-specific components remain
in core. The original subscription does not automatically enable optional lists.

Four initial corrections address the invalid Tumblr operator, the bare newsletter
custom-element token and two NewsNation hostname scopes. The generic scriptlets,
global consent allowances, broad layout/form/article selectors, disclosure-hiding
rules and other reviewed risks are quarantined in [filter-policy.json](./filter-policy.json).
Unverified narrower replacements were not invented.

A live upstream comparison reviewed EasyList commit
`6b074b97be83031cfdf9186165007e246a4a8a10`. All 50 removed seed rules have recorded
decisions: 40 replacements and 10 quarantines (three already present in policy).
The remaining 125 independent new source entries were deferred. The complete
decision inventory is in [upstream-review.json](./upstream-review.json).

All three outputs pass the conservative overlap audit against the eleven locked
yokoffing files at `4e17e52627486f7e2e96fa43cd78b26bd173c260`. Syntax validation uses
the official uBlock parser pinned at `b886738cfba506e55131ae694c4be56795a1f95f`, with
verified module checksums, in Firefox and Chromium profiles. The optional paywall
file has one iOS-only entry skipped by both profiles; counts above are textual
entries, not effective engine counts.

Regression coverage includes baseline input failures/hidden metadata, scope and
exclusion handling, generator policy/accounting/condition boundaries, Mashable
entity/regex/grouped variants, subscription routing, parser failures and verified
source refresh candidates. CI validates changes; a weekly read-only workflow
reports future upstream drift. See [MAINTENANCE.md](./MAINTENANCE.md) for commands.

This is a reproducible build of a maintained seed plus reviewed policy, not a
reconstruction of the missing August generator. Original BPC input and live-site
verification remain limitations. A clean parser or audit does not prove runtime
scriptlet behavior, arbitrary filter equivalence or absence of page breakage.
The repository is private, so anonymous raw subscription fetching returns 404;
manual installation is documented pending an accessible hosting destination.

## Earlier Mashable correction — 1 November 2026

After this first correction, the list contained **10,062 active rules**. Removed only
`mashable.com##.max-w-9xl` after reviewing upstream's
[`mashable site break` correction, 12 October 2026](https://github.com/yokoffing/filterlists/commit/4e17e52627486f7e2e96fa43cd78b26bd173c260).
That commit comments out two filter lines containing six selector branches. One
branch includes `.max-w-9xl` alongside other classes; our standalone width-class
selector also hides every element matching that branch, plus unrelated containers.
Removing it is safer than inventing a narrower replacement without a verified
newsletter-specific target. The newsletter section now has 5,892 active rules.

The other six Mashable rules are unchanged: the two border-class targets,
`[aria-label="Newsletter Sign-Up"]`, the newsletter-text procedural filter,
`.bx-impress`, and its body overflow/position repair. None uses a selector disabled
by that upstream commit. This preserves the existing newsletter and popup filtering;
it is not a claim that each retained rule has been validated on today's site.

Focused regression tests reject the broad width selector and all six disabled
upstream selectors, including grouped cosmetic rules, and check the six retained
targets and active-rule count metadata. Run from the repository root:

```bash
python3 -m unittest discover -s ublock -p 'test_*.py' -v
python3 ublock/audit_filters.py ublock/ubo-no-bullshit-supplement.txt
```

That correction was based on selector overlap and did not include live-browser
verification. Its historical generation audit is preserved below; the new audit
against the current locked baseline is reported in the hardening section above.

## Original generation result — 22 August 2026

The original list contained **10,063 active rules**:

| Section | Input | Output | Exact removed | Canonical removed | Cosmetic targets removed | Manual scope edits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Paywalls / meters / registration walls | 738 | 665 | 70 | 0 | 2 | 8 |
| Promotions / popups / surveys / hostile UI | 4,006 | 3,505 | 470 | 24 | 36 | 10 |
| Newsletter / subscribe / email capture | 5,987 | 5,893 | 43 | 47 | 107 | 6 |
| **Total** | **10,731** | **10,063** | **583** | **71** | **145** | **24** |

Validation passed for:

- zero exact active-rule duplicates against the linked repository;
- zero normalized-equivalent network duplicates (common aliases and option order);
- zero already-covered cosmetic domain/selector targets;
- zero internal exact duplicates;
- balanced uBlock preprocessor conditions.

The audit also reviewed same-pattern network variants. Clear supersets were removed,
and partially overlapping domain/resource scopes were narrowed where they could be
represented safely. Arbitrary logical equivalence between every regex, wildcard,
redirect, exception, and scriptlet is not generally provable, so the non-redundancy
claim is intentionally bounded to the checks above.

## Upstream inputs

- Bypass Paywalls Clean filter **4.4.2.1**, MIT license:
  [project](https://gitflic.ru/project/magnolia1234/bypass-paywalls-clean-filters)
- EasyList – Annoyances, blob `5d2218e5df8e544fad301a797bfc1aa226f8b734`
  at [uAssets commit `d84f64e`](https://github.com/uBlockOrigin/uAssets/blob/d84f64e9662509210f76c46d59eefb2a98c9f584/thirdparties/easylist/easylist-annoyances.txt)
- EasyList – Newsletter Notices, blob `5d9731a8418293ece4501f924aef0d2109d18e69`
  at [uAssets commit `d84f64e`](https://github.com/uBlockOrigin/uAssets/blob/d84f64e9662509210f76c46d59eefb2a98c9f584/thirdparties/easylist/easylist-newsletters.txt)
- EasyList material is used under GPL-3.0-or-later. BPC’s MIT-licensed rules are
  compatible with the combined GPL distribution.

## What the list does

- Adds current client-side paywall, meter, registration-wall, and cookie-reset rules
  absent from the yokoffing baseline.
- Aggressively removes newsletter forms, email-capture overlays, surveys, chat
  widgets, social clutter, house promos, and hostile UI.
- Adds stable YouTube cleanup for Premium/TV/playables promos, paid-content labels,
  surveys, feedback nags, pause overlays, and similar clutter.
- Adds current Bloomberg-side gaps such as the Fortress fence stylesheet, local
  storage cleanup, banner/newsletter cleanup, and visibility repair.

It does **not** freeze uBlock’s rapidly changing YouTube ad-defusing rules. Keep
**uBlock filters – Quick fixes** enabled; that maintained built-in list handles live
YouTube ad changes. A custom snapshot of those rules would become stale and can break
playback.

## Install

This is intended for **full uBlock Origin**, preferably on Firefox.

1. Open uBlock Origin’s dashboard.
2. Go to **Filter lists**.
3. Under **Custom**, import `ubo-no-bullshit-supplement.txt` from a URL you control,
   or paste the file’s rules into **My filters**.
4. Keep uBlock’s default lists and **uBlock filters – Quick fixes** enabled.
5. Do not also enable the full BPC, EasyList Annoyances, or EasyList Newsletter
   sources; this supplement already contains their baseline-differenced rules.
6. Apply changes and purge/update lists.

The list is intentionally aggressive. If a site breaks, use uBlock’s logger to find
the matching rule and add a narrow exception. Paywall cookie rules can log you out.
Filters can remove client-side walls but cannot recover text the publisher never
sent to the browser.

## Re-run the local audit

After cloning or downloading `yokoffing/filterlists`:

```bash
python3 audit_filters.py \
  ubo-no-bullshit-supplement.txt \
  /path/to/filterlists
```

Use `--json` for machine-readable output.
