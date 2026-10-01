# 0011 — Two scope tiers, with a cut line

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [`PRD.md`](../PRD.md), [`roadmap.md`](../roadmap.md), all specs

## Context

The project brief is generous. It lists **six essential features** and **six
suggested additional features** plus **four stretch goals** — sixteen items, for
five people with fourteen days.

Saying "we will do all of it" is how a project ends up with sixteen things that
half work. The brief itself says: *"You can be flexible with the project brief,
provided the essential items are covered."*

So the flexibility is explicitly permitted. The question was where to draw the
line, and it has to be drawn **before** anyone is emotionally invested in a
feature.

## Decision

**Two tiers, and a written cut line agreed in advance.**

### Required for the demo — 9 features

Essentials, plus three suggestions chosen for what sells the product:

1. Registration, login, sessions
2. Profiles
3. Landing page and home feed
4. Matching and search
5. Connection requests
6. Messaging
7. **Notifications** ← suggestion
8. **Project ideas board** ← suggestion
9. **Admin screens** ← suggestion

### Deferred — specced, not built — 4 features

| Feature | Why deferred |
|---|---|
| Events and meetups | New domain with its own UI; nothing in the demo needs it |
| Privacy settings, deletion, export | Most reversible-into-hardest feature in the brief ([deferred_privacy_settings](../specs/deferred_privacy_settings.md) §1) |
| Safety: block, report, moderation | Depends on connections, messaging **and** admins all being solid |
| AI icebreakers | [0009](0009-deterministic-matching-first.md) |

### Cut line, in order

If we are behind, cut from the bottom:

1. **Admin screens.** Nothing depends on them. `seed.py` keeps admin logins
   working, so the demo still shows admin access without a panel.
2. **Project ideas board.** Notifications are already proven by features 5 and 6.
3. **Notifications**, downgraded from live toasts to a poll.
4. **Never** cut the login → profile → match → request → message loop. A login-only
   demo that cannot send a message is not worth showing.

## Rejected

| Option | Why it lost |
|---|---|
| **All 6 essentials + all 6 suggestions** | Sixteen items in fourteen days. Sixteen half-built features and nothing that works end to end. Rejected by arithmetic. |
| **All 6 essentials only** | The most disciplined option and genuinely tempting. Rejected because three of the suggestions are what make the app look like a product rather than a prototype: notifications prove the real-time layer, the ideas board gives the second user group something to *do* rather than only browse, and admin screens answer the question every marker asks, "can you see who is using this?" Nine features was the compromise the team landed on. |
| **Essentials + every suggestion** | Same as the first option, renamed. |
| **Features assigned to people up front** | Rejected because it front-loads the coordination problem and leaves whoever drew admin screens idle at the end. The roadmap is dependency-ordered and work is self-assigned; the critical path is visible in [`roadmap.md`](../roadmap.md). |
| **Choosing by what is fun to build** | Rejected. Matching is the fun one; landing pages are not. Fun-ordering would ship the landing page last and matching first, which is backwards — matching cannot be built before profiles exist ([roadmap](../roadmap.md) feature 4 depends on 2). |
| **Deciding scope in week two** | The failure mode this ADR exists to prevent. By then everyone has spent days on features 8 and 9 and cutting them is painful enough that they will not be cut, and feature 6 ships untested. |
| **Cutting tests to save time** | Explicitly rejected. See [0010](0010-test-strategy.md). The cut line is for features, not for quality. |

## How deferral is made real

A deferred feature that is not visibly deferred gets built by accident at 11pm
by someone who found the spec and thought it was a task. So:

1. **Deferred specs live in separate files**, named `deferred_*.md`, never
   numbered in the main sequence.
2. **Each opens with a banner**: "STATUS: NOT FOR THE DEMO. DO NOT BUILD."
3. **They are excluded from `roadmap.md`'s numbered features**, and appear only
   in a separate table.
4. **`AGENTS.md` §4 states it in the rules**, not just in a comment.
5. **The demo walkthrough does not mention them as missing.** They are
   deliberate scope decisions recorded in [`PRD.md`](../PRD.md) §Out of scope.

The point of writing full specs for deferred features is the opposite of getting
them built. It is so that whoever builds them later has a design instead of an
argument — and so nobody rediscovers the same decision from scratch.

## Consequences

**Cost: three suggestions are on the knife edge.** If we fall behind, the ideas
board and admin screens go. Notifications could be downgraded from live toasts
to a poll, which is a visible quality reduction on the app's most impressive
feature.

**Cost: deferring safety tools is a real product risk.** Blocking, reporting and
a moderation queue are how a social product handles harassment, and we are not
building them. The honest position is that a cohort-only network with mutual
opt-in and admin deactivation has *some* mitigation, and that block/report is
specced and unshipped. **Do not describe this app as having safety tools.** The
deferred spec's closing section has a suggested wording.

**Gained:** the team can be behind and know what to do, without a conversation.
Nine features with a written cut line is a plan; sixteen features with an
optimistic finish date is not.

**Gained:** the demo loop is protected by construction. Features 1 → 2 → 4 → 5
→ 6 are dependency-ordered and explicitly not cuttable, so the thing a marker
sees is the thing that survives schedule pressure.

**Risk to watch: scope creep from the brief.** Every suggestion in the PDF feels
individually small and collectively enormous. When someone suggests a tenth
feature, the response is to point at this ADR — not to agree that it is small.

**Also:** if a deferred feature genuinely must be built, that is a **new ADR**
superseding this one, with an explicit statement of what gets cut in its place.
Never add to Tier 1 without removing something from it.

## Related

- [0009](0009-deterministic-matching-first.md) — the AI split decision
- [0010](0010-test-strategy.md) — tests are not on the cut line
- [`roadmap.md`](../roadmap.md) §Cut line — the operational version of this