/** Shared E2E helpers. */

import { expect, type Page } from '@playwright/test'

let counter = 0

export function uniqueEmail(prefix: string): string {
  counter += 1
  // Slugify: a display name like "New Person" contains a space, and
  // "New Person-1@example.com" is rejected by EmailStr before it leaves the
  // browser. Silent failure that looks like a backend bug.
  const slug = prefix
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return `${slug || 'user'}-${Date.now().toString(36)}-${counter}@example.com`
}

/** A short unique suffix so a test user never collides with a seeded demo user.
 *  The seed data has a "Tomas Nowak", so a test user of the same name makes
 *  getByText(...).first() match the wrong person — which looks exactly like a
 *  broken feature. */
export function uniqueName(base: string): string {
  counter += 1
  return `${base} ${Math.random().toString(36).slice(2, 5).toUpperCase()}`
}

export async function register(
  page: Page,
  { name, email, password = 'correct-horse' }: { name: string; email?: string; password?: string },
): Promise<string> {
  // The display name is used verbatim. Callers that need to select on it must
  // pass a uniqueName() themselves — uniquifying here would silently produce a
  // different name from the one the test is holding.
  const address = email ?? uniqueEmail(name)
  await page.goto('/register')
  await page.getByLabel('Display name').fill(name)
  await page.getByLabel('Email').fill(address)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign up' }).click()

  // Wait for the POST to land AND for navigation to finish. Waiting on the h1
  // is not enough — that heading is already on /register, so the assertion
  // passes before the session cookie exists and the next goto() bounces to
  // /login.
  await page.waitForURL((url) => !url.pathname.startsWith('/register'))
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  return address
}

export async function login(
  page: Page,
  email: string,
  password = 'correct-horse',
): Promise<void> {
  await gotoSettled(page, '/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Log in' }).click()
  // Deliberately no navigation wait: a test may be asserting that a WRONG
  // password does NOT navigate. Wait for the response instead.
  await page.waitForResponse((r) => r.url().includes('/api/v1/auth/login'))
}

/** Navigate, tolerating an in-app redirect.
 *
 * A client-side <Navigate> during the initial load aborts the document request,
 * so page.goto rejects with ERR_ABORTED even though the navigation succeeded.
 * Wait for the URL to settle instead of treating the abort as a failure.
 */
export async function gotoSettled(page: Page, path: string): Promise<void> {
  await page.goto(path).catch(() => {
    // Aborted by an in-app redirect. Not a failure — but verify below.
  })
  try {
    await page.waitForURL((url) => url.pathname === path, { timeout: 5_000 })
  } catch {
    // A guard may have redirected (e.g. to /login). That is a real outcome the
    // caller asserts on, so do not throw here.
  }
}

/** Signs out and waits until it has actually happened.
 *
 * `waitForURL('/')` is a no-op when the user is already on `/`, so it returns
 * instantly and the next goto() aborts the in-flight POST /auth/logout. The
 * session cookie then survives and the "logged out" state never arrives.
 */
export async function logout(page: Page): Promise<void> {
  const response = page.waitForResponse(
    (r) => r.url().includes('/api/v1/auth/logout') && r.status() === 204,
  )
  await page.getByRole('button', { name: 'Log out' }).click()
  await response
  // The cookie must be gone, not merely the user state.
  // Wait for the logged-out view, not for a load event. logout() ends with
  // window.location.replace('/'), and waiting on domcontentloaded races the
  // in-flight document — which shows up as a flaky "page has been closed".
  await page.getByRole('link', { name: /sign up/i }).first().waitFor()
  await expect
    .poll(async () => (await page.context().cookies()).filter((c) => c.name === 'session').length)
    .toBe(0)
}

/** Give the user a role and one skill, which is what unlocks matching. */
export async function completeProfile(
  page: Page,
  { role, skill }: { role: 'Software developer' | 'Business developer'; skill: string },
): Promise<void> {
  await page.goto('/profile/edit')
  await page.getByRole('radio', { name: role }).click()

  await page.getByPlaceholder('Search skills…').fill(skill)
  await page.getByRole('checkbox', { name: skill }).first().check()

  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText(/matching is unlocked/i)).toBeVisible()

  // Return to the feed, which is where the gate's effect is visible. A user
  // does this; a test that stays on the form proves nothing about the feed.
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /hi /i })).toBeVisible()
}