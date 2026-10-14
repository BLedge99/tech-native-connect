# 0013 — Demo mode returns the magic link in the API response

**Status:** Accepted
**Date:** 2026-10-14
**Affects:** `backend/app/config.py`, `backend/app/routers/auth.py`,
`frontend/src/api/client.ts`, `frontend/src/pages/AuthPages.tsx`,
`render.yaml`

## Context

The Render free tier has no mail provider. The magic-link sign-in flow —
which is the only passwordless path and the one a marker is most likely to
exercise — cannot deliver email. Without a workaround, a free deployment is
unusable: the user requests a link, nothing arrives, and there is no way in.

The alternative is to return the link in the API response body and render it
inline on the sign-in page. This is safe only behind a flag, because the
magic-link endpoint's always-202 contract is what prevents account
enumeration: it refuses to say whether an address has an account.

## Decision

**`DEMO_EXPOSE_MAGIC_LINKS` (env var, default `false`).**

When `false` (every real deployment): the endpoint returns the standard
202 with a fixed message. No link, no enumeration.

When `true` (demo/free deployments): the endpoint returns the same 202, but
the body includes `demo_link` **only when the address has an active
account**. The sign-in page renders the link inline when present.

The tradeoff is deliberate and documented at all three layers:

- `config.py` — comment on the setting
- `routers/auth.py` — comment at the branch
- `AuthPages.tsx` — the UI labels it "Demo mode: email delivery is disabled"

## Rejected

| Option | Why it lost |
|---|---|
| **Always return the link** | Destroys the enumeration guarantee. An attacker can probe any email and learn whether it has an account. The always-202 contract exists precisely to prevent this. |
| **SMTP to a real provider** | Costs money, needs credentials in git or a secret store, and is another thing to break on demo day. The free tier has no place to put them. |
| **Skip magic link in demo mode** | The magic link is the passwordless path. A marker who clicks "email me a sign-in link" and gets nothing is a broken demo. |
| **Return the link for unknown addresses too** | Pointless — the link would 404 on use — and it would make the enumeration leak worse by confirming the flag is on. |

## Consequences

**Cost: account enumeration is possible when the flag is on.** An attacker
who can reach the endpoint can determine which emails have accounts. This is
acceptable for a demo deployment with seeded data and no real users; it is
not acceptable for production. The flag defaults to `false` and
`render.yaml` is the only place it is set to `1`.

**Cost: the frontend must handle both shapes.** `client.ts` types the
response as `{ message: string; demo_link?: string }`. The page branches on
presence. Three lines.

**Gained: a free deployment is fully usable.** The magic link works end to
end — request, receive, follow, sign in — with no mail infrastructure.

**Gained: the tradeoff is visible.** Anyone reading the code, the config, or
the UI sees that demo mode gives up the enumeration guarantee. It is not a
hidden compromise.

## Related

- [0008](0008-magic-link-auth.md) — why magic link exists
- [0010](0010-test-strategy.md) — the always-202 contract
- `docs/deploy.md` — how the flag is set in production
