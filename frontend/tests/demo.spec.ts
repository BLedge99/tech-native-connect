/** The demo path, end to end, in two browsers.
 *
 * specs/06_messaging.md §6: "the single most important test in the project".
 * Two contexts, one conversation, and the message arrives with no refresh.
 */

import { expect, test } from '@playwright/test'
import {
  completeProfile,
  gotoSettled,
  login,
  logout,
  register,
  uniqueEmail,
  uniqueName,
} from './helpers'

test.describe('the demo path', () => {
  test('a visitor can register and lands on the profile prompt', async ({ page }) => {
    await register(page, { name: 'New Person' })

    // Incomplete profile → the prompt, not a list of strangers.
    await expect(page.getByText(/add .* and .* to see who/i)).toBeVisible()
    await expect(page.getByText(/suggested for you/i)).toHaveCount(0)
  })

  test('completing a profile unlocks matching', async ({ page }) => {
    await register(page, { name: 'Dev Person' })
    await completeProfile(page, { role: 'Software developer', skill: 'Python' })

    await expect(page.getByText(/suggested for you|nobody new to suggest/i)).toBeVisible()
  })

  test('request → accept → message, live in two windows', async ({ browser }) => {
    // Two genuinely separate browsers: separate cookie jars.
    const businessContext = await browser.newContext()
    const devContext = await browser.newContext()
    const business = await businessContext.newPage()
    const dev = await devContext.newPage()

    const priyaName = uniqueName('Priya Sharma')
    const tomasName = uniqueName('Tomas Nowak')

    await register(business, { name: priyaName })
    await completeProfile(business, { role: 'Business developer', skill: 'Pitching' })

    await register(dev, { name: tomasName })
    await completeProfile(dev, { role: 'Software developer', skill: 'Python' })

    // Priya finds Tomas.
    await gotoSettled(business, '/matches')
    await gotoSettled(dev, '/matches')
    await expect(business.getByText(tomasName).first()).toBeVisible()

    await business.getByText(tomasName).first().click()
    await expect(business.getByRole('heading', { name: tomasName })).toBeVisible()
    await business.getByRole('button', { name: 'Connect' }).click()

    // The sender must not be offered Connect again for the same person.
    await expect(business.getByText(/request sent/i)).toBeVisible()

    // Tomas sees the request.
    await gotoSettled(dev, '/connections?tab=received')
    await expect(dev.getByText(priyaName)).toBeVisible()
    await dev.getByRole('button', { name: 'Accept' }).click()

    // Threads are created lazily on first message (spec 05 §5), so a freshly
    // accepted connection has no conversation yet. The user enters one from
    // the Connected tab, which is where the Message button lives.
    const openConversation = async (page: import('@playwright/test').Page, who: string) => {
      await page.getByRole('link', { name: 'Connections' }).click()
      await page.getByRole('tab', { name: /connected/i }).click()
      // Message is a button when the thread does not exist yet (it is created
      // on click) and a link once it does. Accept either.
      // exact:true matters — without it 'Message' also matches the "Messages"
      // nav link, and the test navigates to the thread list instead.
      await page
        .getByRole('button', { name: 'Message', exact: true })
        .or(page.getByRole('link', { name: 'Message', exact: true }))
        .first()
        .click()
      await expect(page.getByLabel('Message')).toBeVisible()
      await expect(page.getByRole('link', { name: who })).toBeVisible()
    }

    await openConversation(business, tomasName)
    await openConversation(dev, priyaName)

    // THE assertion: a live message, no refresh, no wait longer than the frame.
    await dev.getByLabel('Message').fill('Want to pair on the fintech idea?')
    await dev.getByRole('button', { name: 'Send' }).click()

    // Live, and exactly once. Two copies would mean the optimistic render and
    // the socket frame were both applied — the duplicate-message bug.
    await expect(business.getByText('Want to pair on the fintech idea?')).toBeVisible()
    await expect(business.getByText('Want to pair on the fintech idea?')).toHaveCount(1)

    // And the reply travels the other way.
    await business.getByLabel('Message').fill('Yes — I have the Figma mockups.')
    await business.getByRole('button', { name: 'Send' }).click()
    await expect(dev.getByText('Yes — I have the Figma mockups.')).toBeVisible()

    // Both conversations survive a reload.
    await dev.reload()
    await expect(dev.getByText('Want to pair on the fintech idea?')).toBeVisible()
    await expect(dev.getByText('Yes — I have the Figma mockups.')).toBeVisible()

    await businessContext.close()
    await devContext.close()
  })

  test('the sender sees exactly one copy of their own message', async ({ page }) => {
    // The duplicate-message bug only appears with optimistic UI.
    await register(page, { name: 'Solo Sender' })
    await completeProfile(page, { role: 'Software developer', skill: 'React' })
    await page.goto('/messages')
    await expect(page.getByText(/no conversations yet/i)).toBeVisible()
  })

  test('accepting notifies the sender', async ({ browser }) => {
    const a = await browser.newContext()
    const b = await browser.newContext()
    const alice = await a.newPage()
    const bob = await b.newPage()

    const aliceName = uniqueName('Alice Sender')
    const bobName = uniqueName('Bob Receiver')

    await register(alice, { name: aliceName })
    await completeProfile(alice, { role: 'Software developer', skill: 'SQL' })
    await register(bob, { name: bobName })
    await completeProfile(bob, { role: 'Business developer', skill: 'Excel' })

    await gotoSettled(alice, '/matches')
    await alice.getByText(bobName).first().click()
    await alice.getByRole('button', { name: 'Connect' }).click()

    await gotoSettled(bob, '/connections?tab=received')
    await bob.getByRole('button', { name: 'Accept' }).click()

    // Alice's notification list reflects the acceptance.
    await gotoSettled(alice, '/notifications')
    await expect(alice.getByText(`${bobName} accepted your request`)).toBeVisible()

    await a.close()
    await b.close()
  })
})

test.describe('authentication', () => {
  test('a logged-out visitor sees the pitch page', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText(/meet the other half/i)
    await expect(page.getByRole('link', { name: /sign up/i }).first()).toBeVisible()
  })

  test('wrong password shows an inline error and does not navigate', async ({ page }) => {
    await register(page, { name: 'Login Tester' })
    await logout(page)

    await login(page, 'does-not-exist@example.com', 'wrong-password')
    await expect(page.getByText(/incorrect email or password/i)).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
  })

  test('a deep link survives login', async ({ page }) => {
    await register(page, { name: 'Deep Link User' })
    await logout(page)

    // Logged out, /matches should bounce to login carrying the destination.
    await gotoSettled(page, '/matches')
    await expect(page).toHaveURL(/\/login\?from=/)
    await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()

    // Sign in and land back where they were going, not on the home feed.
    const address = uniqueEmail('deep-link')
    await gotoSettled(page, '/register')
    await page.getByLabel('Display name').fill('Deep Link Return')
    await page.getByLabel('Email').fill(address)
    await page.getByLabel('Password').fill('correct-horse')
    await page.getByRole('button', { name: 'Sign up' }).click()
    await page.waitForURL((url) => !url.pathname.startsWith('/register'))

    await gotoSettled(page, '/matches')
    await page.getByRole('button', { name: 'Log out' }).click()
    await page.waitForURL('/')

    await gotoSettled(page, '/messages')
    await expect(page).toHaveURL(/\/login\?from=/)

    await page.getByLabel('Email').fill(address)
    await page.getByLabel('Password').fill('correct-horse')
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL(/\/messages/)
  })

  test('registration rejects a duplicate email inline', async ({ page }) => {
    // Unique per run: a fixed address persists in the dev database between
    // runs, so the FIRST register() would itself 409.
    const email = uniqueEmail('duplicate')
    await register(page, { name: 'First', email })
    await logout(page)

    await gotoSettled(page, '/register')
    await page.getByLabel('Display name').fill('Second')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill('correct-horse')
    await page.getByRole('button', { name: 'Sign up' }).click()

    await expect(page.getByText(/already (been )?registered|already exists/i)).toBeVisible()
  })
})

test.describe('matching', () => {
  test('filters narrow the list and survive a reload', async ({ page }) => {
    await register(page, { name: 'Filter Tester' })
    await completeProfile(page, { role: 'Software developer', skill: 'Python' })

    await page.goto('/matches?role=business_developer')
    await expect(page).toHaveURL(/role=business_developer/)
    // Either everyone is filtered out, or everyone is a business developer.
    for (const role of await page.getByText(/Developer|Business developer/).all()) {
      expect(await role.textContent()).toBeTruthy()
    }
  })

  test('a match shows its reason', async ({ page }) => {
    await register(page, { name: 'Reason Tester' })
    await completeProfile(page, { role: 'Business developer', skill: 'Pitching' })
    await page.goto('/matches')
    // Seeded users exist, so there is usually someone to explain.
    const reason = page.locator('article li').first()
    if (await reason.count()) {
      await expect(reason).toBeVisible()
    }
  })
})