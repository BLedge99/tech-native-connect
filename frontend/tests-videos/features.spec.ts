/** Evidence recordings, one per feature spec.
 *
 * These are not tests — nothing here asserts a business rule. Each test drives
 * one feature the way a person would and leaves the UI settled long enough for
 * a viewer to read it. The on-screen captions carry the explanation.
 *
 * Run:  docker compose exec -T frontend npx playwright test -c playwright.videos.config.ts
 * Then: ./scripts/build-videos.sh   (adds the side-by-side composites and mp4s)
 */

import { beat, say, step } from './captions'
import {
  completeProfile,
  deleteIdeasTitled,
  fetchMagicLink,
  login,
  logout,
  register,
  uniqueEmail,
  uniqueName,
  writeTestPng,
} from './helpers'
import { expect, test } from './record'

// ─── 01 · Landing page — spec 01 ─────────────────────────────────────────────

test('01 landing page — the pitch, logged out', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    /meet the other half/i,
  )
  await say(page, 'Spec 01 — a logged-out visitor gets the pitch, never a login form')
  await beat(page, 2200)

  await step(page, 'The problem: two halves of one cohort, no way to meet', 1800)
  await page.mouse.wheel(0, 620)
  await beat(page, 1600)

  await step(page, 'How it works — three steps, ending in mutual opt-in', 1800)
  await page.mouse.wheel(0, 620)
  await beat(page, 1600)

  await step(page, 'Built for both halves of the cohort', 1600)
  await page.mouse.wheel(0, 700)
  await beat(page, 1600)

  await page.mouse.wheel(0, -4000)
  await beat(page, 800)
  await step(page, 'One call to action: create your profile', 1200)
  await page.getByRole('link', { name: 'Create your profile' }).click()
  await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible()
  await beat(page, 1800)
})

// ─── 02 · Registration, login, magic link — spec 02 ──────────────────────────

test('02 registration, login and magic link', async ({ page }) => {
  const displayName = uniqueName('Nina Hart')
  const email = uniqueEmail('nina')
  await register(page, { name: displayName, email })
  await expect(page.getByText(/add a role and at least one skill/i)).toBeVisible()
  await say(page, 'Signed up. Incomplete profile, so no strangers are suggested yet')
  await beat(page, 2400)

  await step(page, 'Log out — the server revokes the session, not just the client', 1800)
  await logout(page)

  await step(page, 'Sign back in with the same credentials', 1400)
  await login(page, email, 'correct-horse')
  await expect(page.getByRole('heading', { level: 1 })).toContainText(/hi /i)
  await beat(page, 1800)

  await logout(page)

  await step(page, 'Passwordless: request a sign-in link', 1600)
  await page.goto('/forgot-password')
  await page.getByLabel('Email').fill(email)
  await beat(page, 600)
  await page.getByRole('button', { name: 'Send me a link' }).click()
  await expect(page.getByText(/If that address has an account/i)).toBeVisible()
  await say(page, 'Always the same answer, whether or not the account exists')
  await beat(page, 2400)

  await step(page, 'No real email is sent — Mailpit catches it (localhost:8025)', 2000)
  const token = await fetchMagicLink(email)
  await beat(page, 1200)

  await step(page, 'Follow the link: signed in, no password typed', 1600)
  await page.goto(`/api/v1/auth/magic-link/verify?token=${token}`)
  await page.waitForURL((url) => !url.pathname.includes('magic-link'))
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
  await beat(page, 2600)
})

// ─── 03 · Profiles — spec 03 ─────────────────────────────────────────────────

test('03 profile — building one from nothing', async ({ page }) => {
  const displayName = uniqueName('Rafael Okonkwo')
  await register(page, { name: displayName })

  await step(page, 'A new account lands on a prompt, not on other people', 2000)

  await page.goto('/profile/edit')
  await expect(page.getByRole('heading', { name: 'Edit profile' })).toBeVisible()
  await say(page, 'Spec 03 — profile. Role and one skill are the minimum')
  await beat(page, 2200)

  await expect(page.getByText(/Matching needs a role and at least one skill/i)).toBeVisible()
  await step(page, 'The gate is stated on the form, before you can get it wrong', 2000)

  await page.getByRole('radio', { name: 'Software developer' }).click()
  await beat(page, 900)
  await page.getByPlaceholder('Search skills…').fill('Python')
  await page.getByRole('checkbox', { name: 'Python' }).first().check()
  await beat(page, 500)
  await page.getByPlaceholder('Search skills…').fill('')
  await page.getByPlaceholder('Search skills…').fill('PostgreSQL')
  await page.getByRole('checkbox', { name: 'PostgreSQL' }).first().check()
  await beat(page, 700)
  await page.getByPlaceholder('Search skills…').fill('')
  await page.getByPlaceholder('Search interests…').fill('Fintech')
  await page.getByRole('checkbox', { name: 'Fintech' }).first().check()
  await page.getByLabel('Course').selectOption({ label: 'Software Development' })
  await beat(page, 900)

  await step(page, 'Skills, interests and course all feed the matching reasons', 2000)

  await page.getByLabel('Bio').fill('Backend developer. I like data problems more than interface problems, and I will happily own the boring migration.')
  await page.getByLabel('Looking for').fill('Someone with a real operational problem I can help with.')
  await beat(page, 1000)

  await step(page, 'Every field is length-capped and validated at the boundary', 1800)
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Saved. Matching is unlocked.')).toBeVisible()
  await beat(page, 2400)

  await expect(page.getByText(/matching is unlocked/i).first()).toBeVisible()

  const png = await writeTestPng('/tmp/video-avatar.png', [56, 130, 246])
  await step(page, 'Photo upload: type and size checked server-side', 1600)
  await page.locator('input[type="file"]').setInputFiles(png)
  await expect(page.getByText('Photo updated.')).toBeVisible()
  await beat(page, 2200)

  await page.goto('/profile')
  await step(page, 'The stored profile', 2400)
  await expect(page.getByRole('heading', { name: 'Your profile' })).toBeVisible()
  await page.mouse.wheel(0, 320)
  await beat(page, 2200)
})

// ─── 04 · Matching and search — spec 04 ──────────────────────────────────────

test('04 matching and search', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('tomas@example.com')
  await page.getByLabel('Password').fill('demo-password-123')
  await page.getByRole('button', { name: 'Log in' }).click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'))
  await beat(page, 1500)

  await page.goto('/matches')
  await expect(page.getByRole('heading', { name: 'People on your course' })).toBeVisible()
  await expect(page.locator('article').first()).toBeVisible()
  await say(page, 'Spec 04 — matches, ranked, each one with the reason it was picked')
  await beat(page, 2600)

  await page.mouse.wheel(0, 400)
  await beat(page, 2200)
  await step(page, 'Every suggestion says why — no black box ranking', 2000)

  await page.mouse.wheel(0, -4000)
  await page.getByRole('button', { name: 'Business' }).click()
  await page.waitForURL(/role=business_developer/)
  await beat(page, 2000)
  await say(page, 'Filter by role — the filter lives in the URL, so it survives a reload')
  await beat(page, 2200)

  await page.getByRole('button', { name: 'Everyone' }).click()
  await page.waitForURL((url) => !url.search.includes('role='))
  await page.getByLabel('Skill', { exact: true }).fill('Pitching')
  await page.getByLabel('Skill', { exact: true }).blur()
  await page.waitForURL(/skill=Pitching/)
  await beat(page, 2200)
  await say(page, 'Search by shared skill')
  await beat(page, 1800)

  await page.getByLabel('Interest', { exact: true }).fill('Fintech')
  await page.getByLabel('Interest', { exact: true }).blur()
  await page.waitForURL(/interest=Fintech/)
  await beat(page, 2200)

  await page.goto('/matches')
  await expect(page.locator('article').first()).toBeVisible()
  await step(page, 'Open anyone to see the full profile and why you matched', 1600)
  await page.locator('article h3').first().click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await beat(page, 2600)
  await page.mouse.wheel(0, 380)
  await beat(page, 2400)

  await step(page, 'Connect from here — one click, no interest required yet', 2000)
  const connect = page.getByRole('button', { name: 'Connect' })
  if (await connect.count()) {
    await connect.first().click()
    await beat(page, 1600)
    await expect(page.getByText('Request sent')).toBeVisible()
    await beat(page, 2400)
  }
})
// ─── 08 · Notifications — spec 07 ────────────────────────────────────────────

test('08 notifications', async ({ page }) => {
  // Make Aisha something unread first. Without this the recording only works on a
  // database where nothing has been read yet — and "mark all read" means the
  // second run finds an empty bell.
  await register(page, { name: uniqueName('Nadia Sultana') })
  await completeProfile(page, 'Business developer', 'Pitching')
  await page.goto('/matches')
  await page.getByRole('heading', { level: 3, name: 'Aisha Bello', exact: true }).click()
  await page.getByRole('button', { name: 'Connect' }).click()
  await expect(page.getByText(/request sent/i).first()).toBeVisible()
  await logout(page)

  await login(page, 'aisha@example.com')
  await say(page, 'Spec 07 — notifications. The bell carries the unread count')
  await beat(page, 1800)

  const bell = page.getByRole('button', { name: /Notifications/ })
  await bell.click()
  await expect(page.getByRole('button', { name: 'Mark all read' })).toBeVisible()
  await beat(page, 2600)
  await say(page, 'Unread count in the accessible name, so it is not colour-only')
  await beat(page, 2000)

  await page.mouse.click(10, 400)
  await beat(page, 700)
  await page.goto('/notifications')
  await expect(page.getByRole('heading', { name: 'Notifications' })).toBeVisible()
  await beat(page, 2400)
  await say(page, 'Grouped by day, newest first')
  await beat(page, 2200)

  await step(page, 'Each notification links straight to the thing it is about', 2000)
  await page.getByRole('button', { name: 'Mark all read' }).click()
  await beat(page, 2400)
  // Marking read does not delete: the history stays, the unread state goes.
  // The honest signals are the badge clearing and the button disappearing.
  await expect(bell).toHaveAttribute('aria-label', 'Notifications')
  await expect(page.getByRole('button', { name: 'Mark all read' })).toHaveCount(0)
  await say(page, 'Mark all read: the badge clears, the history stays')
  await beat(page, 2600)

  // The dropdown keeps recent history whether or not it is read — the badge is
  // the thing that clears, so that is what to show.
  await bell.click()
  await expect(page.getByRole('link', { name: 'See all' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Mark all read' })).toHaveCount(0)
  await beat(page, 1200)
  await say(page, 'Recent notifications stay in the dropdown; the unread badge is gone')
  await beat(page, 2600)
})

// ─── 09 · Project ideas — spec 08 ────────────────────────────────────────────

const NEW_IDEA = 'Empty-return-leg dashboard for regional couriers'

test('09 project ideas board', async ({ page }) => {
  // Only business developers may post, which is the spec's own rule.
  await deleteIdeasTitled(NEW_IDEA)
  await login(page, 'priya@example.com')
  await page.goto('/ideas')
  await expect(page.getByRole('heading', { name: 'Project ideas' })).toBeVisible()
  await say(page, 'Spec 08 — the ideas board. Business developers post, developers answer')
  await beat(page, 2600)

  await page.mouse.wheel(0, 420)
  await beat(page, 2200)
  await step(page, 'Each idea states the skills it needs', 1800)

  await page.mouse.wheel(0, -4000)
  await page.getByRole('button', { name: 'Find a problem' }).click()
  await page.waitForURL(/category=find_problem/)
  await beat(page, 2200)
  await say(page, 'Filter by category — in the URL again')
  await beat(page, 1800)

  await page.goto('/ideas/new')
  await expect(page.getByRole('heading', { name: 'Post a project idea' })).toBeVisible()
  await step(page, 'Post an idea. Business developers only — developers answer.', 2000)
  await page.getByLabel('Title').fill(NEW_IDEA)
  await page
    .getByLabel('What is it?')
    .fill(
      'Route planning that shows the cost of every empty return leg, not just the drive time. ' +
        'Three couriers I spoke to said this is the number they guess at every morning and get wrong.',
    )
  await page.getByRole('radio', { name: 'Build a product' }).click()
  await beat(page, 700)
  await page.getByPlaceholder('e.g. Python, Figma').fill('Python')
  await page.keyboard.press('Enter')
  await page.getByPlaceholder('e.g. Python, Figma').fill('PostgreSQL')
  await page.keyboard.press('Enter')
  await beat(page, 1200)
  await say(page, 'Skills are free text — an empty conversation helps nobody')
  await beat(page, 1800)

  await step(page, 'Submit', 1000)
  await page.getByRole('button', { name: 'Post idea' }).click()
  await page.waitForURL(/\/ideas$/)
  await expect(page.getByText(NEW_IDEA).first()).toBeVisible()
  await beat(page, 2600)

  // ── The other half of the board: a developer picks it up ───────────────────
  await logout(page)
  await login(page, 'liam@example.com')
  await page.goto('/ideas')
  await page.getByLabel('Search ideas').fill('Empty-return-leg')
  await page.getByLabel('Search ideas').blur()
  await expect(page.getByRole('heading', { name: NEW_IDEA })).toBeVisible()
  await step(page, 'A developer finds it by search — spec 08 works both ways', 2400)

  await page.getByRole('heading', { name: NEW_IDEA }).click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await beat(page, 2400)

  const interested = page.getByRole('button', { name: /Express interest|I'm interested/ })
  await expect(interested).toBeEnabled()
  await interested.click()
  await beat(page, 2000)
  await expect(page.getByText('1 interested')).toBeVisible()
  await say(page, 'Express interest — one click, and the author sees the count')
  await beat(page, 2800)
})

// ── 10 · Admin — spec 09 ─────────────────────────────────────────────────────

test('10 admin screens', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('ben@bootcamp.example.com')
  await page.getByLabel('Password').fill('bootcamp-dev-admin')
  await page.getByRole('button', { name: 'Log in' }).click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'))
  await beat(page, 1500)

  // A non-admin is refused. Show the refusal before showing the panel.
  await logout(page)
  await login(page, 'tomas@example.com')
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: /403/ })).toBeVisible()
  await step(page, 'A signed-in non-admin gets 403, not a login redirect', 2600)

  await logout(page)
  await login(page, 'ben@bootcamp.example.com', 'bootcamp-dev-admin')
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible()
  await say(page, 'Spec 09 — admin. Every admin read of a user is audited')
  await beat(page, 2600)

  await step(page, 'Overview counts', 1600)
  await page.getByRole('tab', { name: 'users' }).click()
  await expect(page.getByRole('columnheader', { name: 'Email' })).toBeVisible()
  await beat(page, 2600)

  await page.getByLabel('Search users').fill('priya')
  await beat(page, 2000)
  await say(page, 'Search the user table by name or email')
  await beat(page, 2200)

  await page.getByRole('tab', { name: 'audit' }).click()
  await expect(page.getByRole('columnheader', { name: 'Action' })).toBeVisible()
  await beat(page, 2600)
  await say(page, 'The audit log — who did what, and when')
  await beat(page, 2600)

  await page.getByRole('tab', { name: 'reference' }).click()
  await expect(page.getByRole('heading', { name: 'Skills' })).toBeVisible()
  await beat(page, 2400)
  await say(page, 'Reference data: courses, skills and interests are admin-managed')
  await beat(page, 2600)
})
