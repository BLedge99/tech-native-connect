# 0009 — Deterministic matching first, AI deferred

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [04](../specs/04_matching_and_search.md), [deferred_ai_icebreakers](../specs/deferred_ai_icebreakers.md)

## Context

The brief lists, under suggested additional features:

> AI-assisted matching or icebreaker suggestions

and separately, under stretch goals:

> AI-assisted matching or icebreaker suggestions.

The PDF's goals mention "Claude or Codex or open source models running and
implemented, tested". So this is a feature the project owner cares about, and
the brief asks for it twice.

The question was how much of it is required for the demo. The team discussed it
and reached a split decision, recorded here in full because the reasoning is the
valuable part.

## Decision

**Matching ships deterministic. AI ships as a fully specced, deferred feature.**

Specifically:

1. **Matching in the demo is weighted overlap** over four signals — complementary
   role (30), shared skills (10 each, capped at 30), shared interests (5 each,
   capped at 15), same course (20). One pure Python function.
   See [04](../specs/04_matching_and_search.md) §2.
2. **Every match carries a plain-English `reason`** built from the factors that
   actually contributed.
3. **AI icebreakers are deferred**, with a complete design at
   [`deferred_ai_icebreakers.md`](../specs/deferred_ai_icebreakers.md) — including a
   provider abstraction, prompt design, caching, cost controls, and an honest
   section on the "open source models" question.
4. **AI is never used for ranking or matching.** If AI is ever added, it is
   icebreakers only.

## Rejected

| Option | Why it lost |
|---|---|
| **LLM-powered matching in the demo** | Rejected on four concrete grounds, not on taste. **It is non-deterministic**, so you cannot write a unit test asserting that the right person comes first — and `AGENTS.md` §7 requires unit tests for matching scoring. **It is unauditable**: "why is this person first?" has no answer you can point at, when the entire point of the demo is that the app explains itself. **It is a network call in the request path** of the feature a marker will click first, so an API key, a rate limit and a fallback all become demo-day risks. **It costs money per use**, on a project with a fixed budget of zero. |
| **Embedding-based similarity** | Solves "these bios are semantically similar", which is not the question. The question is "does a developer who knows Python need this business developer, and can we say why in a sentence". Weighted overlap answers the actual question and produces the explanation for free. It is also a vector store, a model download and a similarity function. |
| **A hybrid: deterministic score, LLM writes the reason** | Attractive, and it is roughly the deferred design — but the reason text does not need a model. `["You both know Python, React.", "Both on Software Development."]` can be built from the contributing factors with a list comprehension, and then it is **testable** ([04](../specs/04_matching_and_search.md) §9 has a test that reasons mention only contributing factors). A model-generated reason can hallucinate a shared skill that does not exist, which is worse than no reason at all. |
| **An AI provider in the running app at all, for the demo** | No budget, needs an API key on every machine, and adds a network dependency to a laptop demo. See the deferred spec §1 for the operational comparison between a local model and a hosted API. |
| **Neither AI nor deterministic matching** | Not a real option — the brief's essential list includes "search and matching". |
| **Scoring with a different algorithm — collaborative filtering, popularity, or an explicit compatibility questionnaire** | All worse here. Collaborative filtering needs history, and at demo time the database has no history. Popularity is not available before users exist. A questionnaire adds profile fields and a new screen to build. Weighted overlap over the fields we already have is the most signal for the least work. |

## What we agreed, specifically

The team split on whether AI should be in the demo. The compromise that
everyone accepted:

- **The demo ships deterministic matching.** It works, it is explainable, it is
  testable, and it costs nothing.
- **The AI design is written down now**, in full, so it can be built later
  without re-litigating the decision — and so the discussion that produced it is
  not lost.
- **The deferred design is honest about what it is:** one optional line of text,
  generated on demand, cached, and never sent without the user reading and
  editing it.

That last point is what makes the deferred feature safe to build at all. A model
speaking on a user's behalf to a stranger in a professional context is a
reputational hazard, not a feature.

### The weights are documented, not tuned

30 / 10 / 5 / 20 is a judgement call about what matters for this product, and it
is written in a table in [04](../specs/04_matching_and_search.md) §2 and in a named
constant in code, with a unit test per weight. That is deliberate: a scoring
function with magic numbers is unexplainable, and "why is this person first" is
a question the app promises to answer.

## Consequences

**Cost.** The demo does not show anything AI-generated. If a marker asks "is
this AI?", the honest answer is: matching is deterministic and explainable by
design, AI icebreakers are specced and deliberately deferred, and here is the
design. That answer is stronger than a fragile AI call that fails on stage.

**Cost.** The scoring weights are not empirically tuned. They are reasoned from
the product's premise — the whole app is about crossing sides, so a
complementary role outweighs three shared skills. Tuning needs data we will not
have. If the demo data makes the top match obviously wrong, **change the
weights**, not the algorithm.

**Gained.** Matching is a pure function with no I/O, so its unit tests are the
fastest and most valuable tests in the project. It never fails in a demo. It
costs nothing. And every suggestion has a defensible, inspectable reason.

**Gained, strategically:** the AI feature becomes *possible* later without
risk, because the architecture has no LLM in the request path. Generation is a
button, cached, failure returns `null`, and the page renders either way. That is
the property which makes deferring safe rather than merely postponed.

**Risk to watch:** someone reads "AI-assisted matching" on the brief and assumes
it was forgotten. It is in `roadmap.md`'s deferred set and in the PRD's
out-of-scope table, and the reasoning is here. Say it out loud in the demo.

## Related

- [deferred_ai_icebreakers.md](../specs/deferred_ai_icebreakers.md) — the full AI design
- [0011](0011-scope-tiers-and-cut-line.md) — how deferral is enforced
- [0010](0010-test-strategy.md) — why testability drove this decision