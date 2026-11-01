# No-Bullshit uBlock Origin Supplement — audit

Generated on 22 August 2026 as an additive list for
[yokoffing/filterlists](https://github.com/yokoffing/filterlists), baseline commit
[`80d1341d220a773424a4644a2b52eb62a94b1b8f`](https://github.com/yokoffing/filterlists/commit/80d1341d220a773424a4644a2b52eb62a94b1b8f).

## Maintenance correction — 1 November 2026

The current list contains **10,062 active rules**. Removed only
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

This correction is based on selector overlap. Live-browser breakage has not been
reproduced, and the complete overlap audit below has not been rerun against a newer
upstream baseline.

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
