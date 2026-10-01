# 01 — Landing page and home feed

**Goal:** two distinct first impressions. A logged-out visitor needs to
understand what this is within ten seconds. A logged-in user needs to land
somewhere useful.

**Depends on:** [02 — Registration](02_registration_and_login.md),
[03 — Profiles](03_profiles.md)
**Blocks:** nothing. This is the most cuttable feature on the board.

**Implementation status:** Not started.

---

## 1. Two surfaces, two audiences

| Route | Audience | Shows |
|---|---|---|
| `/` (logged out) | A marker, a prospective user | The pitch. What the app does, who it is for, how it works, sign up. |
| `/` (logged in) | An existing user | Home feed: suggestions, incomplete-profile prompt, recent activity. |

Both are `/`. The router decides which to render from session state. Do not
build two URLs for the same thing — logged-in users clicking a link to `/`
must see their feed, not a pitch page.

### Why this is not first

It needs to know what a profile and a match look like, so it depends on 02 and
03. But nothing depends on it, and it is cosmetic, so it sits after the
features on the critical path. If you are behind, this is the feature to
simplify.

## 2. The public pitch page

### Required content

Five sections, in this order. This ordering is the argument.

1. **Hero.** Product name, one sentence on what it does, one call to action
   → `/register`. No more. The sentence is the most important thing on the
   page and should be rewritten until it is obvious.
2. **The problem.** Developers want a business partner; business developers
   want someone who can build their idea. Two sentences.
3. **How it works.** Three numbered steps: complete your profile → get matched
   on shared skills and complementary roles → connect and talk. This maps
   exactly onto the demo loop, so the page teaches people how to use the app.
4. **Who it's for.** The two groups, side by side. Makes clear this is a
   bootcamp cohort tool, not a general network.
5. **Call to action.** Sign up, plus "already have an account? Log in".

### Constraints

- **No backend dependency.** It renders for logged-out visitors, who by
  definition have no session. If it fetches anything it must degrade silently.
- **Must not look broken without JavaScript content** — server-render the
  static shell, hydrate the interactive parts.
- **Every route is reachable without an account.** No dead ends.
- Mobile-first. Tailwind responsive classes; check at 375 px before calling it
  done.

## 3. The home feed (logged in)

Four widgets. This is the demo's opening screen — it should look like a product,
not a dashboard.

| Widget | Source | Behaviour |
|---|---|---|
| **Greeting** | `GET /users/me` | "Hi {first_name}". One line. |
| **Complete your profile** | `users/me.profile_complete` | **If incomplete, this is the only thing shown** — no suggestions, no activity. Two links: edit profile, add skills. See §4. |
| **Suggested for you** | `GET /matches?limit=6` | Top 6 matches, each a card with photo, name, role, course, shared skills, reason. See [04](04_matching_and_search.md). "See all" → `/matches`. |
| **Recent activity** | `GET /notifications?limit=5` | Last 5, unread bold, click → target. "See all" → `/notifications`. See [07](07_notifications.md). |

Suggested-for-you requires `profile_complete`. While incomplete, render the
complete-your-profile widget instead of making a request that will `403`.

### Widget failure is not page failure

**`AGENTS.md` §5 rule 6.** If `/matches` or `/notifications` fails, the home
feed still renders. A demo that shows a white screen because the suggestions
call failed is worse than one showing a greeting and a retry button.

```tsx
// Each widget fetches independently and owns its own error state.
<Widget error={matchesError}>   // renders "Couldn't load suggestions" + Retry
```

One request failing must never unmount or blank the other widgets. No global
error boundary wrapping the whole feed.

## 4. The incomplete-profile gate

This is the most important interaction on the page.

While `profile_complete` is `false`:

- Show **only** the complete-your-profile widget. Hide suggested-for-you and
  recent activity entirely — do not show empty containers or a `403` error.
- Say specifically what is missing: no role, or no skills. "Add a role and at
  least one skill to see matches" beats "Profile incomplete".
- Link to `/profile/edit`, deep-linked to the missing section if you can.
  `/profile/edit?focus=skills` should land on the skills input.

This mirrors a backend rule (`403 profile_incomplete`,
[04](04_matching_and_search.md)) but does not replace it. The backend still
refuses the request. The frontend just avoids making it.

## 5. Routing and guards

### Route table

| Route | Guard | Renders |
|---|---|---|
| `/` | none | Pitch page, or home feed if logged in |
| `/register` | redirect if logged in | Registration form |
| `/login` | redirect if logged in | Login form |
| `/matches` | required | Full match list |
| `/connections` | required | Requests and connections |
| `/messages` | required | Thread list |
| `/messages/:threadId` | required + membership | Chat view |
| `/notifications` | required | Notification list |
| `/ideas` | required | Project ideas board |
| `/ideas/new` | required | Post an idea |
| `/profile` | required | Own profile, read view |
| `/profile/edit` | required | Own profile, edit form |
| `/users/:userId` | required | Another user's public profile |
| `/settings` | required | Account settings |
| `/admin/*` | required + admin | Admin screens, [09](09_admin.md) |
| `*` | none | 404 with a link home |

### Auth guard behaviour

```tsx
// In routes/, never inside a component body.
function RequireAuth({ children }) {
  const { user, loading } = useCurrentUser();
  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" state={{ from: location }} />;
  return children;
}
```

Three behaviours, all tested:

1. **Preserve the destination.** Redirect to `/login?from=<path>`. After login
   the user returns to where they were going, not to the home feed. This is
   the difference between "the app lost my page" and "the app works".
2. **Return the user if already logged in.** `/login` while authenticated →
   `/`. No confusing double state.
3. **Never flash protected content.** Wait for session resolution before
   rendering. A brief spinner beats a frame of private data.

`from` is user-controlled input. Use it as a path only if it starts with a
single `/` and not `//` — otherwise `//evil.com` is an open redirect.

### Admin guard

`RequireAdmin` wraps `/admin/*`. Non-admins get a 403 page, not a redirect to
login — they are authenticated, just not permitted. Server-side `get_current_admin`
still applies; this is cosmetic, not the enforcement point.

## 6. Component sketch

```
LandingPage
├── Hero
├── ProblemStatement
├── HowItWorks
├── WhoItsFor
└── CallToAction

HomeFeed
├── Greeting
├── ProfileIncompletePrompt     ← replaces everything else when incomplete
├── SuggestedMatchesWidget      ← independent loading / empty / error
│   └── MatchCard
├── RecentActivityWidget        ← independent loading / empty / error
│   └── NotificationRow
└── SuggestionList / ActivityListPage

NotFound
```

`MatchCard` is defined in [04](04_matching_and_search.md) and reused here.
Define it once.

## 7. Accessibility

Minimum for anything a marker might click through quickly:

- Semantic landmarks: `<header>`, `<main>`, `<nav>`, `<footer>`.
- One `<h1>` per page.
- Every form input has a `<label>`.
- Buttons that navigate are `<Link>` or `<button>` with a handler — not a bare
  `<div onClick>`. Keyboard must reach them.
- Visible focus rings. Do not remove outlines without replacing them.
- Images have `alt`; decorative ones get `alt=""`.
- Colour contrast at least 4.5:1 for body text.

## 8. Performance

- Public page ships as static Vite assets. Target Lighthouse performance ≥ 90
  on the pitch page.
- Home feed widgets fetch in parallel, not in sequence. Three sequential
  round-trips is visible.
- Match cards show a placeholder until images load; a photo blob must never
  cause layout shift.

## 9. Tests

### Unit / component

- Pitch page renders all five sections with a working signup link.
- Logged-in `/` renders the feed, not the pitch page.
- Incomplete profile → prompt only, suggestions widget **not** rendered, **no
  `/matches` request made**.
- Incomplete profile → message names what is missing.
- Complete profile → all four widgets render.
- Matches request fails → greeting, profile prompt and activity still render;
  error state with retry visible.
- Notifications request fails → matches still render.
- Loading state renders while in flight; no flash of empty state.
- `RequireAuth`: logged out → redirect to `/login` with `from`; logged in →
  children render.
- Login → returns to the original destination.
- `/login` while authenticated → redirects to `/`.
- `RequireAdmin` non-admin → 403 page, not a login redirect.
- Unknown route → 404 with a working link home.
- External `from` value (`//evil.com`) is not honoured.

### E2E

- Visitor loads `/`, reads the pitch, follows the CTA, registers.
- New user lands on home feed → sees the incomplete-profile prompt.
- Completing the profile → feed now shows suggestions.

### Integration

- `GET /` needs no session.
- Home feed data endpoints each require a session (`401` without).

## 10. Out of scope

Marketing copy beyond the five sections, illustrations and custom artwork,
SEO, analytics tracking, dark mode, i18n, an onboarding tour, social preview
meta tags. Do not start any of these.

## 11. Definition of done

Checklist from [`00_conventions.md`](00_conventions.md) §Done, plus:

- [ ] Logged out on `/` → all five pitch sections, working CTA
- [ ] Logged in on `/` → feed
- [ ] Incomplete profile → prompt only, no suggestions request
- [ ] A failing widget does not blank the page
- [ ] `from` round-trip works; open redirect refused
- [ ] Mobile layout checked at 375 px
- [ ] All tests in §9 pass

## 12. Agent notes

- The single most likely mistake is rendering the pitch page for a logged-in
  user. Test it explicitly.
- Second most likely: firing the `/matches` request while `profile_complete` is
  `false`, getting a `403`, and showing an error on a page that should be
  showing a prompt.
- `MatchCard` belongs to [04](04_matching_and_search.md). If you are building
  this before 04, define the component against the shape in 04 and expect 04 to
  fill in the matching logic.
- Do not add a component library. Tailwind only.