# Maintaining the subscriptions

## Inputs and policy

`sources/seed.txt` is the exact published supplement at commit
`c3bbd28465392e410ec3c77a7f9595ebc5e1b550`, including historical scope edits and the
first Mashable correction. It is an immutable maintenance seed, not a subscription.
`sources.lock.json` pins it by SHA256, Git blob SHA and commit, along with eleven
yokoffing baseline files and two EasyList source references.

The original August generator and its 24 manual edits cannot be reconstructed
from retained files. No immutable raw BPC input was retained. Its version and
attribution are recorded, but BPC is not automatically refreshed. This workflow
preserves the published result and records subsequent changes explicitly.

`filter-policy.json` contains exact, reviewed decisions:

- `disabled`: quarantine a seed rule with a reason; absent from every output.
- `replacements`: correct a seed rule; optional `destination` keeps corrected
  interface/paywall companions in the appropriate subscription.
- `interface_rules`: move navigation/RSS/interface rules and their exceptions.
- `paywall_rules`: keep reviewed content-gate and repair companions together.
- `additions`: add a reviewed rule with `rule`, `section` (`paywall`, `promotions`
  or `newsletter`), `destination` (`core`, `paywalls` or `interface`), `reason`, and
  an immutable GitHub `source` URL containing a full commit SHA.

The original paywall section, cookie/storage deletion and network compatibility
exceptions are optional. Explicit policy keeps genuine newsletter components
such as Forbes' newsletter modal in core; names alone do not determine routing.
Generic consent exceptions and ignored generic scriptlets remain quarantined
until their required hostname scope is verified. Restore broad selectors only
after checking actual matched elements/requests and adding focused regressions.

## Rebuild and validate

Run from the repository root:

```bash
python3 ublock/build_filters.py
python3 ublock/build_filters.py --check
python3 -m unittest discover -s ublock -p 'test_*.py' -v
node --test ublock/test_validate_filters.mjs
node ublock/validate_filters.mjs --env firefox
node ublock/validate_filters.mjs --env chromium
```

The builder checks seed integrity, stale/conflicting policy, conditional scopes
and rule accounting. It writes version/count metadata. Update `VERSION` and
`MODIFIED` in `build_filters.py` for a release. Edit policy rather than generated
files; `--check` writes nothing and fails for stale/missing outputs.

The parser downloads the exact official modules in `parser-lock.json` and verifies
all four checksums before import. After the cache is populated, use
`node ublock/validate_filters.mjs --offline`. `--cache DIR` selects a separate cache;
parser tests accept `UBO_PARSER_CACHE=DIR` and `UBO_PARSER_OFFLINE=1`. A checksum
mismatch is an error; verify the source/lock before deleting a corrupt cache.

The repository is private. The seed is verified from its included local copy;
`--download` never requests a private raw seed URL. It verifies 13 public upstream
files plus that local seed (14 pins total). Automatic uBlock subscriptions require
publicly reachable hosting; manual installation is documented in README.md.

Counts describe non-comment entries. The parser separately reports enabled rules
and conditional skips. Neither establishes effective engine counts or live-site
behavior, and syntax checks do not validate scriptlet names/arguments at runtime.

## Baseline audit

```bash
python3 ublock/refresh_sources.py --verify-seed --download
python3 ublock/audit_filters.py ublock/ubo-no-bullshit-supplement.txt /path/to/filterlists
```

Repeat for the optional lists. An ordinary Git checkout is supported: hidden
metadata is excluded. Missing/empty/unreadable inputs fail with a clear error.
Add `--json` for machine-readable output. The locked baseline cache is
`ublock/.cache/sources/locked/yokoffing/<commit-from-sources.lock.json>/`.
Commit-addressed caches prevent lock updates from reusing a different revision.

The checker detects exact/internal duplicates, normalized network duplicates,
identical-selector scope coverage for understood parent/global/entity cases,
ignored generic scriptlets, count errors and unbalanced conditions. It cannot
prove arbitrary CSS subsumption, network equivalence or regex/entity intersections.
Mashable tests supply the known entity explicitly rather than guessing registrable
domains without a Public Suffix List.

## Review upstream changes

Choose a new or empty candidate directory:

```bash
python3 ublock/refresh_sources.py --check --candidate /tmp/ubo-refresh-review --json
```

Exit codes: 0 means no content drift; 1 means drift needs review; 2 means input or
fetch failure. Reports include additions/removals, removed rules still in the
seed, and new/deleted baseline files. Candidates contain source diffs/downloads
and a proposed lock. They are review proposals rather than standalone builds;
the maintained seed is not copied into the candidate directory.

The command never overwrites active lock/policy/seed/outputs and refuses nonempty
candidate destinations. Review changes against current policy and the baseline;
record corrections, quarantines or additions with provenance. Keep related hide
and repair rules together. Review pins separately before promoting a lock, and
retain unresolved changes in the review record. A newer pin does not prove its
rules were incorporated. Rebuild and run all checks before committing.

The 1 November review is retained in `upstream-review.json`: all 50 removed seed
rules received replacement/quarantine decisions. Forty upstream changes were
adopted as replacements; 125 independent new upstream entries were deferred.
The EasyList reference pin records the checked revision, while the original input
pins remain in `legacy_provenance`. This is a targeted safety refresh, not adoption
of every new upstream filter.

The weekly GitHub workflow has read-only repository access and uploads reports
and diffs even when future drift makes it fail. It creates no commits. Previously
deferred entries stay in the review record; a clean drift check does not mark
them implemented. The validation workflow independently verifies current outputs.

## Browser verification

For a quarantined rule, inspect representative article, newsletter, login and
contact pages using uBlock's logger/DOM inspector. Confirm both unwanted targets
and nearby content/controls, test user-opened dialogs, and capture a small fixture
before restoring a narrow selector. No live-site validation is claimed here.
