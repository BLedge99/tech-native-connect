# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two groups studying the same bootcamp course at the same time:

- **Software developers**, looking for a business problem worth building against.
- **Business developers**, looking for a technical collaborator who can build what they describe.

The pairing *is* the situation. They share a cohort but not a context: each can describe a problem the other cannot yet evaluate.

## Product Purpose

Bootcamp Connect introduces each cohort member to the people on their own course whose skills and interests match what they are looking for, and states why each pairing was suggested.

Success is a formed working relationship — a request sent, an accepted connection, a live conversation. An account that never reaches a message is not a success for the person who made it.

## Positioning

Three things a neighbouring product could not truthfully copy:

1. **Cohort-scoped.** Matches are drawn from the user's own course, not a global talent pool. The pool is deliberately small.
2. **Reasons, not a score.** Every match states why it was suggested — shared skills, complementary interests — rather than presenting an unexplained ranking.
3. **Both parties must accept.** Expressing interest is not permission to message. A thread opens only when both people have accepted, so no candidate can be spammed.

## Operating Context

- **Coursework.** This is an assessed project. There are no real users; the audience for a demonstration is an assessor, not a cohort.
- **Runs locally in Docker.** `run.bat` is the only supported entry point — `dev`, `tunnel`, `url`, `logs`, `down`, `clean`. Docker, Node and Python live inside the containers, never on the host.
- **Demonstrations run over a Cloudflare Quick Tunnel**, yielding a public `*.trycloudflare.com` URL so the app can be reached from other devices. The hostname is random and changes whenever the container is recreated, so the URL must be re-shared per demonstration. This is how the app is shared — there is no hosted deployment.
- **Email never leaves the machine.** Mailpit is the dev mail server and catches magic links. Over the tunnel the link is surfaced in the browser instead, because Mailpit is not reachable from another device.
- **Test accounts are seeded** — a business developer and an admin — so a demonstration needs no setup.

The repository also contains a Render blueprint for a single-image free-tier deploy. **It is not how this project is run** and is not a deployment commitment.

## Capabilities and Constraints

Capabilities: registration with magic-link or password sign-in; profiles gated on a role and at least one skill; ranked matching with reasons plus skill and interest filtering; connection requests requiring mutual acceptance; one-to-one messaging with live delivery; notifications; a project-ideas board; an admin area.

Durable product rules. These are the rules a marker is most likely to probe, and breaking one is a defect rather than a design choice:

1. No valid session means no data — every user-scoped endpoint returns `401`.
2. A chat thread opens only when both people have accepted.
3. Matching is inaccessible until the profile is complete (role chosen, at least one skill). An incomplete profile gets `403 profile_incomplete`, never partial results.
4. Users read and write only their own profile. Admins are the sole exception, and their access is audited.
5. Every input is validated at the HTTP boundary — length caps, enum checks, email format, file type and size.
6. The app degrades, it does not break. A non-essential failure still renders the page. This matters in front of an assessor.

Terminology in use: cohort, profile, match, match reason, connection request, connection, thread, message, notification, idea, interest.

Open decisions, deliberately not settled:

- **The name is not confirmed as final.** "Bootcamp Connect" is simply what it currently calls itself.
- **No pricing, licensing or commercial model** exists, and none should be invented.
- **No accessibility conformance target has been adopted.**

## Brand Commitments

**The terminal identity is committed.** The dark terminal chrome, command/status framing and monospace-leaning interface are a deliberate direction that future visual work must preserve rather than replace.

The product name and the prose voice are **not** confirmed as binding.

## Evidence on Hand

- Nine demonstration videos in `videos/`, one per feature; two are two-window recordings so live messaging is visible without cutting.
- Seeded demo accounts with known credentials (`backend/app/seed.py`).
- A Mailpit inbox holding real magic-link mail.

**These absences are binding.** There are no real users, no testimonials, no usage metrics, no customer logos and no press. None of it may be fabricated into product copy, marketing surfaces or evidence.

## Product Principles

1. **Earn the second screen.** The visitor's next action matters more than the page's polish. The demo path is sign up → profile → matches → request → accept → message → notification.
2. **Say why, never just rank.** Any suggestion, score or grouping must be explainable in a sentence the user can check.
3. **Consent before access.** Nothing is visible to another person until both sides agree.
4. **Degrade, don't break.** In front of an assessor, a half-working page is worse than an honest inline error.
5. **The honest state is the deliverable.** Where something is incomplete, blocked or out of scope, show that plainly instead of papering over it.

## Accessibility & Inclusion

Deliberate decisions already made in the interface, to be preserved: distinct accessible names on multi-selects that would otherwise share a placeholder, an accessible name on the search input, inline `role="alert"` errors rather than native `alert()` dialogs, and `prefers-reduced-motion` handling. No formal conformance target has been adopted.