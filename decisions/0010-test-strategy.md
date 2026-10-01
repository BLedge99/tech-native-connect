# 0010 — Comprehensive tests, E2E on the demo path

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** every spec; [`roadmap.md`](../roadmap.md) §Definition of done

## Context

The weekly goals say the project should be **"designed, implemented, tested (we
do together on Thursday)"**. So testing is part of the brief, not an extra.

We also raised this openly with the team, because the honest numbers are
uncomfortable. Comprehensive unit + integration + E2E across nine features in
fourteen days, with five people who are also building the features, is not
achievable at full strength. E2E alone is typically one to two days per feature
once it is reliable — that is roughly twelve days of pure test work across the
whole team, which is the entire budget.

The team chose the comprehensive bar anyway. That is their call to make, and this
ADR records both the choice and what it costs, so nobody is surprised in week
two.

## Decision

**Comprehensive testing on every required feature: unit, integration, component
and E2E. Where the budget runs short, cut a feature — not the tests.**

Concretely:

| Suite | Tool | Target | Bar |
|---|---|---|---|
| Unit | pytest | `services/`, no I/O | **Every business rule.** Scoring, permissions, state machines, validation |
| Integration | pytest + httpx | Real Postgres, test client | **Every endpoint and every `AGENTS.md` §5 rule** |
| Component | Vitest + RTL | jsdom | Loading, empty and error states |
| E2E | Playwright | Full stack in Docker | **Each feature's demo path** |

**`AGENTS.md` §5 rules 2, 3 and 4 are treated as a test requirement, not a code
review habit.** Each has a named integration test.

**If a feature is late, it comes out of the roadmap** —
[`roadmap.md`](../roadmap.md) §Cut line. Tests are never the thing we trim.

## Rejected

| Option | Why it lost |
|---|---|
| **Unit tests on business logic only** | The cheapest option, and genuinely tempting. Rejected because the bugs that break demos live at the HTTP layer — a missing auth guard, a wrong status code, a shape mismatch between what the service returns and what the frontend expects. None of those are reachable by calling a service function directly. |
| **Comprehensive unit + integration, E2E only for the demo path** | **The option we nearly took, and it is probably the pragmatic one.** Rejected by team decision, not by argument — see the honesty note below. |
| **Comprehensive everything, E2E across all nine features** | What was actually chosen. Rejected only in the sense that it is the most expensive option available and we are aware of that. |
| **Playwright for everything, no component tests** | Fewer tools, but slow. Every component test becomes a full browser test, so the feedback loop for pure-rendering bugs gets much worse. RTL tests are a second for that work; Playwright is thirty. |
| **Cypress instead of Playwright** | Playwright's auto-waiting removed most of the flakiness we would otherwise spend a day fixing. Multi-browser support is irrelevant here. |
| **Coverage percentage as the target** | A number to hit rather than behaviour to prove. 100% coverage of untested trivial getters tells you nothing and costs hours. This ADR has no coverage threshold. |
| **Manual QA checklists instead of E2E** | Loses the regression protection. The demo path gets re-tested by hand every time a feature lands, and by week two that is most of a day per round. |

## What "comprehensive" means here, precisely

So this does not get read as "write whatever feels like enough", the bar is:

1. **Every business rule in `services/` has a unit test.** Not every function —
   every *rule*. Permission checks, state transitions, scoring, validation
   boundaries.
2. **Every endpoint has an integration test** covering its success path and its
   documented error cases, using the error shapes in
   [`00_conventions.md`](../specs/00_conventions.md) §2.
3. **Every `AGENTS.md` §5 rule has at least one integration test.** These are
   the six rules a marker is most likely to probe.
4. **Every feature has at least one E2E test on its demo path**, defined in its
   spec's §Tests.
5. **Every list screen has loading, empty and error state tests.**

Each spec lists its specific tests by name. That is what makes this bar
checkable by someone who did not write the feature.

## Consequences

**Cost, stated plainly: some features will not be finished.** The
comprehensive bar across nine features in fourteen days means the cut line in
[`roadmap.md`](../roadmap.md) will probably be used. Admin screens and the
project ideas board are the likely casualties.

**Cost:** roughly 40% of total project capacity goes to testing rather than
feature work. That is the price of the choice and it is visible in the roadmap
schedule.

**Cost:** E2E tests are the most likely thing to become flaky, and flakiness is
worse than no test — people start ignoring red. Mitigations: Playwright's
auto-waiting, explicit waits only where the UI is genuinely async, no arbitrary
`sleep`, and no network mocking in E2E tests, because a test that mocks the
network is not testing the demo.

**Cost:** real Postgres in integration tests ([0002](0002-postgres-not-sqlite.md))
is slower than an in-memory database. Accepted deliberately — tests that pass
against a different engine than production are not worth having.

**Gained:** the security-relevant behaviour is proven rather than asserted.
Rule 2 in particular — that a thread opens only when both people accept — is the
kind of thing that looks fine in a demo and is a data leak in production. Having
an integration test named
`test_sender_cannot_accept` makes that a fact rather than a hope.

**Gained:** the specs carry their own test cases. An AI agent implementing
feature 07 can read §7 and know exactly what to write, and a reviewer can check
completeness against a list instead of judging it.

**Risk to watch: the deadline.** If the choice turns out to be wrong, the fix is
to cut features, not to delete tests. The first thing to cut is admin screens
([09](../specs/09_admin.md)) — nothing depends on it, and `seed.py` keeps the admin
logins working without it.

### The honesty note

This is the one decision in the set where the team knowingly chose a bar it may
not hit. That is legitimate — testing is explicitly in the brief, and shipping
six well-tested features is a better project than shipping nine half-tested
ones. But it should be said out loud rather than discovered in week two.

If the comprehensive bar proves unsustainable, the response is a **new ADR**
recording the change to the tiered approach, not a quiet drift where E2E tests
stop being written. That is why
[`00_conventions.md`](../specs/00_conventions.md) §10 exists.

## Related

- [0011](0011-scope-tiers-and-cut-line.md) — how features get cut instead
- [0002](0002-postgres-not-sqlite.md) — real Postgres in integration tests
- [0005](0005-websocket-in-process.md) — the two-window E2E test that justifies it