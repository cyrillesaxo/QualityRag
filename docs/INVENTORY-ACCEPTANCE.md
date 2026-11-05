# US-001: objective source-inventory acceptance

US-001 is an administrative software story. Its four criteria concern the source
inventory, PR #69's honest state, passing-test receipt enforcement, and explicit
unavailable decoder/admission boundaries. They do not require a merged PR #70 or
an independent semantic-review signature. Earlier implementation metadata added
those universal prerequisites and prevented objective inventory work from closing.

The corrected rule is narrow: only US-001 can use
GITHUB_VERIFIED_SOURCE_INVENTORY/v1 completion evidence. US-002 has a separate versioned-catalog acceptance path. Every remaining DONE entry
retains the existing independent signed completion check. No research criterion,
source license, physical-device measurement, explicit merge prerequisite, domain
admission or production approval is waived by completing the inventory.

## What acceptance verifies

1. Every inventory row contains implementation locations, branch/base revision,
   status, runnable evidence and remaining limitations. US-001's own implementation
   is pinned to a tested immutable commit and module SHA-256 inventory.
2. Live GitHub metadata determines whether PR #69 remains IN_REVIEW or is MERGED.
   An open PR cannot satisfy US-022's merge prerequisite. Closing US-001 does not
   close US-022, merge either PR, or represent submitted independent review.
3. The recorded CI URL/run must actually belong to cyrillesaxo/QualityRag, run the
   activation workflow on the pinned push commit, complete successfully, and run
   the required SDK, finite, runtime, compiler, ledger and audit steps without
   skipped/failed steps. The immutable Git tree must match the inventory verifier,
   audit implementation and workflow bytes in the current repository.
4. The inventory explicitly states canonical FF-RCT decoder UNAVAILABLE,
   independent domain admission NOT_ESTABLISHED, and reference scene decoder
   AVAILABLE_RESEARCH_REFERENCE. Availability is scoped to this implementation,
   not an assertion that no decoder exists elsewhere.

Missing source, stale implementation, forged links, failed/skipped tests, wrong
repository/workflow or unavailable GitHub evidence refuses acceptance. A locally
edited DONE status alone still fails. The existing signed research path cannot
be replaced by assigning this evidence kind to another story.

## Trust and replay boundary

The normal auditor retrieves metadata directly over HTTPS from fixed GitHub REST
paths and refuses redirects. It uses GITHUB_TOKEN only from the host environment,
with read-only contents/actions/pull-request permissions in CI; no client-supplied
URL, token or truth label supplies authority. No token is included in receipts.
Local replay of a private repository needs an authorized read token. An unavailable
service or missing authorization is an error, never fabricated acceptance.

The narrow verifier's unit tests use isolated metadata fixtures. Those fixtures
are not acceptance evidence. Actual closure requires a passing real CI run, then
a follow-up inventory commit binding that observed run. That follow-up CI executes
the live verifier. Unrelated later research changes do not retroactively become
accepted under this inventory-software receipt. Changing the accepted inventory
implementation itself requires renewed evidence or reopening its acceptance.

The resulting status means SOURCE_INVENTORY_SOFTWARE_ONLY. Independent domain
validation stays NOT_ESTABLISHED; no independent signature is manufactured and no
semantic, scientific or production claim becomes accepted through this path.
