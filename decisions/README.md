# Architecture decision records

One file per significant decision. Each answers four questions: what we
decided, why, what we rejected, and what it costs us.

## Format

Every ADR is short. Four sections, no more:

```markdown
# NNNN — Title

**Status:** Accepted | Superseded by NNNN
**Date:** YYYY-MM-DD
**Affects:** specs/XX, specs/YY

## Context
Why we were choosing. The constraint that made this non-obvious.

## Decision
What we chose. One sentence, up front.

## Rejected
What else was on the table and why it lost. Be specific — "SQLite is simpler"
is not a reason.

## Consequences
What this costs. Every ADR has a cost. An ADR with none is not finished.
```

## Why these exist

Five people plus several AI agents, one repo, two weeks. The main failure mode
is not writing bad code — it is three people independently making different
reasonable choices, and nobody noticing until the merge.

An ADR makes a choice **findable and reversible**. `decisions/0002-postgres-not-sqlite.md`
tells a future contributor why the obvious shortcut was rejected, so nobody has
to rediscover it by hitting the same wall.

## Rules

1. **Write the ADR first**, then the code. Changing the stack without a record
   is how we end up with two conflicting opinions in one repo.
2. **Never edit an accepted ADR.** Write a new one that supersedes it and link
   both. History is the point — "we changed our minds and here is why" is more
   useful than a clean file.
3. **Rejections matter more than decisions.** The next person will ask "why not
   X?" and this is where the answer lives.
4. **Consequences must include the cost.** Every choice buys something and
   loses something. An ADR with only upsides is a sales pitch.
5. **Keep them short.** If it does not fit on one screen, it is probably an
   implementation detail, not a decision.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-fastapi-and-react.md) | FastAPI backend, React frontend | Accepted |
| [0002](0002-postgres-not-sqlite.md) | PostgreSQL from day one | Accepted |
| [0003](0003-vite-not-nextjs.md) | Vite SPA, not Next.js | Accepted |
| [0004](0004-cookie-sessions-not-jwt.md) | Cookie sessions, not JWT | Accepted |
| [0005](0005-websocket-in-process.md) | Native WebSocket, in-process registry | Accepted |
| [0006](0006-images-as-pg-blob.md) | Profile photos as Postgres blobs | Accepted |
| [0007](0007-mailpit-dev-mail.md) | Mailpit for dev email | Accepted |
| [0008](0008-magic-link-auth.md) | Build auth ourselves, magic link | Accepted |
| [0009](0009-deterministic-matching-first.md) | Deterministic matching first, AI deferred | Accepted |
| [0010](0010-test-strategy.md) | Comprehensive tests, E2E on the demo path | Accepted |
| [0011](0011-scope-tiers-and-cut-line.md) | Two tiers, with a cut line | Accepted |
| [0012](0012-monorepo-layout.md) | Single repo, backend/ and frontend/ | Accepted |

## Superseding an ADR

```markdown
**Status:** Superseded by [0015](0015-new-choice.md)
```

Leave the body untouched. Add the link at the top. The old reasoning stays
readable so nobody re-litigates it.