# ADR 0012 — T8 evidence composition and T9 planning boundary

**Status:** Accepted on 2026-08-27

## Context

The complete T8 runner passed quality, security, smoke, backup/restore, Guess
load, reconnect and dependency-recovery gates on a single-host Ubuntu stack.
The two remaining failures were corrected and passed in a selective retry:
production image scanning and 2,000 concurrent WebSockets. Repeating every
already-successful load profile would be expensive and would add no evidence
for documentation-only changes.

The local host is not the agreed production-like staging topology. Its results
therefore cannot establish a public SLO, production capacity envelope or final
deployment approval. T9 itself is a planning gate rather than one competitive
implementation task.

## Decision

- Compose the T8 local baseline from the complete run plus selective retry when
  both identify the same candidate and the retry changes only the failed or
  directly affected gates.
- Preserve a successful expensive gate unless code, configuration,
  dependencies, image contents, its harness or the target topology changes in
  a way that can affect the result.
- Mark T8 engineering and the single-host validation baseline complete.
- Keep Production Beta deployment blocked until the applicable gates pass on
  the agreed production-like staging topology with infrastructure evidence.
- Unblock T9 product/architecture planning only. Competitive implementation
  begins after T9 produces an accepted set of bounded tasks; production release
  remains independently gated by staging approval.

This supersedes ADR 0011 only where it made production-like staging evidence a
prerequisite for starting T9 planning. It does not weaken ADR 0011's production
deployment or capacity-approval requirements.

## Consequences

The team avoids repeated five-minute load tests when their inputs are
unaffected, while evidence provenance remains explicit. T9 can now define
Ranked and matchmaking safely without pretending that local measurements prove
production capacity. Any deployment candidate or topology change must run the
relevant staging gates again.
