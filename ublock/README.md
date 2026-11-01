# uBlock Origin filters

## No-Bullshit uBlock Origin Supplement

**Existing subscribers:** the original URL now supplies the core newsletter and
popup list. Paywall/state-reset filtering and navigation cleanup have moved to
separate optional subscriptions. Import those below if you want to keep those
features. They are not enabled automatically.

**This repository is private.** Its raw URLs return 404 to unauthenticated
clients, so the Subscribe links below require an accessible public mirror before
uBlock can update them automatically. For use now, open the chosen `.txt` file in
GitHub and copy its filter text into uBlock's dashboard → My filters → Apply
changes. Manual copies must be updated manually. Repository visibility has not
been changed by this maintenance work.

| Subscription | What it changes | Install |
| --- | --- | --- |
| **Core — newsletters and popups** | Newsletter prompts, email capture, surveys, promotional popups and house promos. Recommended starting point. | [Subscribe](https://subscribe.adblockplus.org/?location=https%3A%2F%2Fraw.githubusercontent.com%2Fandyhern-id%2FHobby-Stuff%2Fmain%2Fublock%2Fubo-no-bullshit-supplement.txt&title=No-Bullshit%20Supplement%20-%20Newsletters%20and%20Popups) · [Raw list](https://raw.githubusercontent.com/andyhern-id/Hobby-Stuff/main/ublock/ubo-no-bullshit-supplement.txt) |
| **Optional — paywalls and state resets** | Paywalls, meters, forced registration and companion repairs. Resets may erase preferences or log you out; script blocking can affect site functions. | [Subscribe](https://subscribe.adblockplus.org/?location=https%3A%2F%2Fraw.githubusercontent.com%2Fandyhern-id%2FHobby-Stuff%2Fmain%2Fublock%2Fubo-no-bullshit-paywalls.txt&title=No-Bullshit%20Supplement%20-%20Optional%20Paywalls) · [Raw list](https://raw.githubusercontent.com/andyhern-id/Hobby-Stuff/main/ublock/ubo-no-bullshit-paywalls.txt) |
| **Optional — interface cleanup** | Back-to-top/scroll controls, RSS widgets and selected membership triggers. Can hide useful navigation and account-access controls. | [Subscribe](https://subscribe.adblockplus.org/?location=https%3A%2F%2Fraw.githubusercontent.com%2Fandyhern-id%2FHobby-Stuff%2Fmain%2Fublock%2Fubo-no-bullshit-interface.txt&title=No-Bullshit%20Supplement%20-%20Optional%20Interface%20Cleanup) · [Raw list](https://raw.githubusercontent.com/andyhern-id/Hobby-Stuff/main/ublock/ubo-no-bullshit-interface.txt) |

When hosted at publicly reachable URLs, Subscribe links are the preferred Firefox
installation path. uBlock Origin recognizes subscription links clicked on GitHub
and asks you to confirm the list. For a public mirror, update the links' location
URLs, or import the mirror's raw URL in Filter lists → Custom → Import.

### Requirements and behavior

- Use **full uBlock Origin**, preferably Firefox. Other blockers and uBlock Origin
  Lite do not support every advanced rule in these lists.
- Keep uBlock's default filters and **uBlock filters – Quick fixes** enabled for
  maintained YouTube countermeasures.
- These lists supplement [yokoffing/filterlists](https://github.com/yokoffing/filterlists).
  Do not also enable the full BPC, EasyList Annoyances or EasyList Newsletter
  source lists; those include rules deliberately omitted here.
- Optional lists can be enabled independently. No generated rule is duplicated
  across these three subscriptions.
- Core is still opinionated: it hides newsletter forms and some social, chat and
  promotional UI, and can set site-specific popup-dismissal preferences.
- Filters cannot recover article text the publisher never sent to the browser.

### Maintenance and validation

The hardening release fixes confirmed syntax/scope mistakes, quarantines reviewed
broad selectors, and keeps related paywall repairs together in the optional list.
Reviewed editorial corrections/disclosures, whole-form wrappers and unverified
layout-container targets are no longer hidden by these lists. Reasons are recorded
in [filter-policy.json](./filter-policy.json).

- [Current and historical audit](./UBO_SUPPLEMENT_AUDIT.md)
- [Rebuild, validation and upstream review instructions](./MAINTENANCE.md)
- [Overlap checker](./audit_filters.py) and [uBlock syntax validator](./validate_filters.mjs)

From the repository root, with Python 3.10+ and Node 20+:

```bash
python3 ublock/build_filters.py --check
python3 -m unittest discover -s ublock -p 'test_*.py' -v
node --test ublock/test_validate_filters.mjs
node ublock/validate_filters.mjs
```

The first parser run downloads four pinned official modules and verifies their
checksums. CI runs validation on changes. A separate weekly workflow produces
upstream diffs for review; it never publishes changed filters itself.

Daily subscription refreshes retrieve the latest published snapshot. They do not
automatically import upstream changes. Passing checks do not guarantee live-site
behavior; historical BPC source and browser-testing limits are documented in
[MAINTENANCE.md](./MAINTENANCE.md).
