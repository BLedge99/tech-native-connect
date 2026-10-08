/**
 * Regression tests for the §12 review findings that are only visible in a
 * browser. Added 8 October 2026, before the fix — every test here is expected
 * to fail against the code as it stands.
 *
 *   B2  unread_messages is hardcoded to 0
 *   B3  ThreadPage calls hooks below an early return
 *   B4  the toast dedupe evicts an unrelated toast
 *   B5  the magic link points at the API origin, not the app
 *   B9  photo upload leaves the database in the wrong state
 *   B16 a long conversation cannot be scrolled back through
 *   B19 a signed-out visitor opens a WebSocket
 *
 * Two rules hold throughout, and both are load-bearing:
 *
 *   1. **No network mocking.** playwright.config.ts states the policy in a
 *      comment; `scripts/check-no-mocking.mjs` now enforces it. A test that
 *      intercepts a request is not testing the demo.
 *   2. **Every assertion has an independent witness** — a fresh authenticated
 *      `page.request` call, a direct Postgres read, or the real WebSocket
 *      object's own state. Nothing here asserts only on rendered pixels.
 */

import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { closeDb, messageBodies, messageCount, photoCount, unreadTotal } from './db'
import { completeProfile, gotoSettled, register, uniqueEmail, uniqueName } from './helpers'

const MAILPIT = process.env.MAILPIT_URL ?? 'http://mailpit:8025'
const APP_ORIGIN = new URL(process.env.E2E_BASE_URL ?? 'http://localhost:5173').origin

/** A real 1x1 PNG. The server sniffs magic bytes; this one is genuinely an image. */
const TINY_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
)

/** Past the cap in config.py, and still a valid PNG by magic bytes. */
const OVERSIZED_PNG = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  Buffer.alloc(3 * 1024 * 1024),
])

test.afterAll(async () => {
  await closeDb()
})

// ─── Helpers ────────────────────────────────────────────────────────────────

/** A second, independent browser with its own cookie jar. */
async function otherUser(browser: import('@playwright/test').Browser, name: string) {
  const context: BrowserContext = await browser.newContext()
  const page = await context.newPage()
  await register(page, { name })
  await completeProfile(page, { role: 'Business developer', skill: 'Pitching' })
  return { context, page }
}

/** POST as the signed-in owner of `page`, using its cookie jar. */
async function postAs(page: Page, path: string, body?: unknown) {
  const response = await page.request.post(path, { data: body })
  return { status: response.status(), body: await response.json().catch(() => null) }
}

async function me(page: Page) {
  const response = await page.request.get('/api/v1/users/me')
  expect(response.status(), 'the test user should be signed in').toBe(200)
  return response.json()
}

/** Toast text for a notification, matched on the actor's display name. */
function toast(page: Page, fragment: string) {
  return page.getByRole('status').filter({ hasText: fragment })
}

// ─── B5: the magic link ─────────────────────────────────────────────────────

/** Pull the *absolute* sign-in URL out of the Mailpit inbox.
 *
 * The absolute URL, not just the token. `tests-videos/helpers.ts` returns only
 * the token and rebuilds the URL on the frontend origin, which is precisely why
 * the hardcoded API origin went unnoticed: the recording suite works around it.
 */
async function fetchMagicLinkUrl(email: string): Promise<string> {
  const list = await (await fetch(`${MAILPIT}/api/v1/messages?limit=50`)).json()
  const mine = (list.messages ?? [])
    .filter((m: { To?: { Address: string }[] }) =>
      m.To?.some((t: { Address: string }) => t.Address.toLowerCase() === email.toLowerCase()),
    )
    .pop()
  if (!mine) throw new Error(`no Mailpit message for ${email}`)

  const full = await (await fetch(`${MAILPIT}/api/v1/message/${mine.ID}`)).json()
  const blob = `${full.Text ?? ''}\n${full.HTML ?? ''}`
  const match = blob.match(/https?:\/\/[^\s"'<>]*magic-link\/verify\?token=[A-Za-z0-9_-]+/)
  if (!match) throw new Error(`no sign-in link in message ${mine.ID}`)
  return match[0]
}

test('a magic link signs you in and lands you on the app, not a 404', async ({ browser }) => {
  // A brand new account, so the link cannot be confused with an existing session.
  const setupContext = await browser.newContext()
  const setup = await setupContext.newPage()
  const email = uniqueEmail('magic-link')
  await register(setup, { name: uniqueName('Link Signin'), email })
  await completeProfile(setup, { role: 'Software developer', skill: 'Python' })

  await gotoSettled(setup, '/forgot-password')
  await setup.getByLabel('Email').fill(email)
  await setup.getByRole('button', { name: /send me a link/i }).click()
  await expect(setup.getByText(/if that address has an account/i)).toBeVisible()

  const link = await fetchMagicLinkUrl(email)

  // A fresh browser: nothing signed in, so a successful sign-in can only have
  // come from following the link.
  const freshContext = await browser.newContext()
  const fresh = await freshContext.newPage()
  await fresh.goto(link)
  await fresh.waitForLoadState('domcontentloaded')

  // Where the user actually ends up. The link is minted against the API origin,
  // so today this is a 404 served by the API rather than the app.
  expect(new URL(fresh.url()).origin).toBe(APP_ORIGIN)
  expect(new URL(fresh.url()).pathname).toBe('/')

  // And the session really exists — not merely a redirect that looks right.
  const signedIn = await me(fresh)
  expect(signedIn.email).toBe(email)

  await setupContext.close()
  await freshContext.close()
})

test('a magic link works exactly once', async ({ browser }) => {
  const setupContext = await browser.newContext()
  const setup = await setupContext.newPage()
  const email = uniqueEmail('magic-link-once')
  await register(setup, { name: uniqueName('Single Use'), email })

  await gotoSettled(setup, '/forgot-password')
  await setup.getByLabel('Email').fill(email)
  await setup.getByRole('button', { name: /send me a link/i }).click()
  await expect(setup.getByText(/if that address has an account/i)).toBeVisible()
  const link = await fetchMagicLinkUrl(email)

  const firstContext = await browser.newContext()
  const first = await firstContext.newPage()
  await first.goto(link)
  expect((await me(first)).email).toBe(email)

  // The same token again must be refused. Guards the row-lock fix in §11.
  const secondContext = await browser.newContext()
  const second = await secondContext.newPage()
  await second.goto(link)
  await second.waitForLoadState('domcontentloaded')
  expect((await me(second)).email).not.toBe(email)

  await setupContext.close()
  await firstContext.close()
  await secondContext.close()
})

// ─── B2: the unread count ───────────────────────────────────────────────────

test('the unread message count agrees with the thread list and the database', async ({
  browser,
}) => {
  const receiverContext = await browser.newContext()
  const receiver = await receiverContext.newPage()
  await register(receiver, { name: uniqueName('Receiver') })
  await completeProfile(receiver, { role: 'Business developer', skill: 'Pitching' })

  const senderContext = await browser.newContext()
  const senderPage = await senderContext.newPage()
  await register(senderPage, { name: uniqueName('Sender') })
  await completeProfile(senderPage, { role: 'Software developer', skill: 'Python' })

  const receiverMe = await me(receiver)

  const request = await postAs(senderPage, '/api/v1/connections', {
    receiver_id: receiverMe.id,
  })
  expect(request.status).toBe(201)

  const accepted = await receiver.request.patch(`/api/v1/connections/${request.body.id}`, {
    data: { action: 'accept' },
  })
  expect(accepted.status()).toBe(200)

  const threadResponse = await receiver.request.post(
    `/api/v1/connections/${request.body.id}/thread`,
  )
  expect(threadResponse.status()).toBe(201)
  const threadId = (await threadResponse.json()).id

  // Three messages, all unread for the receiver: the receiver never opens the
  // thread, because opening it marks everything read.
  for (let index = 0; index < 3; index += 1) {
    const message = await postAs(senderPage, `/api/v1/threads/${threadId}/messages`, {
      body: `unread ${index}`,
    })
    expect(message.status).toBe(201)
  }

  const threads = await (await receiver.request.get('/api/v1/threads')).json()
  const fromList = threads.items.reduce((sum: number, t: { unread_count: number }) => sum + t.unread_count, 0)

  const summary = await (await receiver.request.get('/api/v1/connections/summary')).json()
  const fromDatabase = await unreadTotal(receiverMe.id)

  expect(fromDatabase).toBe(3)
  expect(fromList, '/threads and the database disagree').toBe(fromDatabase)
  expect(
    summary.unread_messages,
    'connections/summary hardcodes unread_messages instead of counting',
  ).toBe(fromDatabase)

  // And the badge in the nav must not disagree with the page it links to
  // (specs/07 §6). Toasts and the bell both read /notifications, so the
  // witness here is the notification count, also checked against the database.
  await gotoSettled(receiver, '/messages')
  await expect(receiver.getByRole('heading', { level: 1, name: /messages/i })).toBeVisible()

  const unreadNotifications = await receiver.request.get('/api/v1/notifications/unread-count')
  const badge = await unreadNotifications.json()
  if (badge.unread_count > 0) {
    await expect(
      receiver.getByRole('button', { name: new RegExp(`Notifications, ${badge.unread_count} unread`) }),
    ).toBeVisible()
  } else {
    await expect(receiver.getByRole('button', { name: /^Notifications$/ })).toBeVisible()
  }

  await receiverContext.close()
  await senderContext.close()
})

// ─── B19: no socket for a signed-out visitor ────────────────────────────────

test('a signed-out visitor opens no websocket', async ({ page }) => {
  const sockets: string[] = []
  page.on('websocket', (socket) => sockets.push(socket.url()))

  await page.goto('/')
  await expect(page.getByRole('link', { name: /sign up/i }).first()).toBeVisible()
  // Long enough for a connect attempt and its rejection to have happened.
  await page.waitForTimeout(2_000)

  expect(
    sockets,
    'a signed-out visitor opened a WebSocket. The provider retries a rejected ' +
      'handshake forever at up to 30s intervals, so the landing page never stops trying.',
  ).toEqual([])

  // Positive control: signing in really does open one, so the assertion above
  // cannot pass just because WebSockets are broken in this environment.
  await register(page, { name: uniqueName('Socket Owner') })
  await expect.poll(() => sockets.length, { timeout: 15_000 }).toBeGreaterThan(0)
  expect(sockets.every((url) => url.endsWith('/api/v1/ws'))).toBe(true)
})

// ─── B3: no React hook errors ───────────────────────────────────────────────

test('opening a conversation logs no react hook errors', async ({ browser }) => {
  const first = await browser.newContext()
  const second = await browser.newContext()
  const a = await first.newPage()
  const b = await second.newPage()

  await register(a, { name: uniqueName('Hook A') })
  await completeProfile(a, { role: 'Software developer', skill: 'Python' })
  await register(b, { name: uniqueName('Hook B') })
  await completeProfile(b, { role: 'Business developer', skill: 'Pitching' })

  const aMe = await me(a)
  const bMe = await me(b)
  const request = await postAs(a, '/api/v1/connections', { receiver_id: bMe.id })
  expect(request.status).toBe(201)
  expect((await b.request.patch(`/api/v1/connections/${request.body.id}`, { data: { action: 'accept' } })).status()).toBe(200)

  const thread = await (
    await a.request.post(`/api/v1/connections/${request.body.id}/thread`)
  ).json()

  const problems: string[] = []
  a.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      problems.push(message.text())
    }
  })
  a.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))

  await gotoSettled(a, `/messages/${thread.id}`)
  await expect(a.getByLabel('Message')).toBeVisible()

  // The component's hooks are declared below `if (loading) return <Spinner/>`,
  // so the first render runs fewer hooks than the second and React complains.
  const hookErrors = problems.filter((text) => /rendered (more|fewer) hooks|hook order/i.test(text))
  expect(
    hookErrors,
    `React reported a hook-order violation on the thread page:\n${hookErrors.join('\n')}`,
  ).toEqual([])

  // The consequence of the same bug: the listener registered below the early
  // return has to still work once loading finishes.
  await postAs(b, `/api/v1/threads/${thread.id}/messages`, { body: 'hook listener works' })
  await expect(a.getByText('hook listener works')).toBeVisible()

  await first.close()
  await second.close()
})

// ─── B4: the toast dedupe ───────────────────────────────────────────────────

test('a repeated notification never evicts an unrelated toast', async ({ browser }) => {
  const viewerContext = await browser.newContext()
  const viewer = await viewerContext.newPage()
  await register(viewer, { name: uniqueName('Toast Viewer') })
  await completeProfile(viewer, { role: 'Business developer', skill: 'Pitching' })
  const viewerMe = await me(viewer)

  // The viewer authors an idea so the third event can come from the same actor
  // as the first without needing a second connection request.
  const idea = await postAs(viewer, '/api/v1/ideas', {
    title: 'A toast fixture idea',
    description:
      'An idea long enough to satisfy the fifty character minimum, used purely to ' +
      'generate a notification so the toast stack can be observed in a browser.',
    category: 'build_product',
  })
  expect(idea.status).toBe(201)

  const actorA = await otherUser(browser, uniqueName('Actor A'))
  const actorC = await otherUser(browser, uniqueName('Actor C'))

  // Toasts render wherever the user is, so any authenticated page works.
  await gotoSettled(viewer, '/messages')
  await expect(viewer.getByRole('heading', { level: 1, name: /messages/i })).toBeVisible()

  // Warm-up. Asserting this first means a failure below can only be the dedupe
  // bug, never a socket that was not open yet.
  expect((await postAs(actorA.page, '/api/v1/connections', { receiver_id: viewerMe.id })).status).toBe(201)
  await expect(toast(viewer, 'Actor A')).toBeVisible({ timeout: 15_000 })

  const actorAName = (await me(actorA.page)).display_name
  const actorCName = (await me(actorC.page)).display_name
  expect((await postAs(actorC.page, '/api/v1/connections', { receiver_id: viewerMe.id })).status).toBe(201)
  await expect(toast(viewer, actorCName)).toBeVisible({ timeout: 15_000 })

  // Same actor as the warm-up, well inside the five second window.
  expect((await postAs(actorA.page, `/api/v1/ideas/${idea.body.id}/interest`)).status).toBe(200)

  // Deduplicating a repeat must not delete anything. Today the handler removes
  // the oldest toast instead of the new one, so Actor A's toast disappears.
  await expect(
    toast(viewer, actorCName),
    "Actor C's toast was evicted by a repeat from a different actor",
  ).toBeVisible()
  await expect(
    toast(viewer, actorAName),
    "Actor A's first toast was deleted by its own repeat",
  ).toBeVisible()

  await viewerContext.close()
  await actorA.context.close()
  await actorC.context.close()
})

// ─── B16: paging a long conversation ────────────────────────────────────────

test('a long conversation can be scrolled back through its whole history', async ({ browser }) => {
  const readerContext = await browser.newContext()
  const reader = await readerContext.newPage()
  await register(reader, { name: uniqueName('Long Reader') })
  await completeProfile(reader, { role: 'Business developer', skill: 'Pitching' })

  const senderContext = await browser.newContext()
  const sender = await senderContext.newPage()
  await register(sender, { name: uniqueName('Long Sender') })
  await completeProfile(sender, { role: 'Software developer', skill: 'Python' })

  const readerMe = await me(reader)
  const request = await postAs(sender, '/api/v1/connections', { receiver_id: readerMe.id })
  expect(request.status).toBe(201)
  expect((await reader.request.patch(`/api/v1/connections/${request.body.id}`, { data: { action: 'accept' } })).status()).toBe(200)

  const threadId = (
    await (await reader.request.post(`/api/v1/connections/${request.body.id}/thread`)).json()
  ).id

  // Seeded through the API because clicking out 55 messages is not a test of
  // anything. Each one is a real persisted row.
  const seeded = 55
  for (let index = 0; index < seeded; index += 1) {
    const message = await postAs(sender, `/api/v1/threads/${threadId}/messages`, {
      body: `history ${index}`,
    })
    expect(message.status).toBe(201)
  }
  expect(await messageCount(threadId)).toBe(seeded)

  await gotoSettled(reader, `/messages/${threadId}`)
  await expect(reader.getByText(`history ${seeded - 1}`, { exact: true })).toBeVisible()

  // Older messages must be reachable. There is no cursor support in the client
  // and no control, so the first 50 are all that will ever render.
  const oldest = `history 0`
  await expect(reader.getByText(oldest, { exact: true })).toHaveCount(0)

  const loader = reader.getByRole('button', { name: /load (older|more)/i }).first()
  await expect(
    loader,
    `a ${seeded}-message conversation shows only the newest page and offers no ` +
      'way to reach the rest',
  ).toBeVisible()

  // Click until the first message appears. The bound is derived from walking
  // the API's own cursor chain rather than hardcoded, so it stays correct if the
  // page size changes.
  const pages = await (async () => {
    let count = 0
    let cursor: string | null = null
    do {
      const url = `/api/v1/threads/${threadId}/messages?limit=50${cursor ? `&cursor=${cursor}` : ''}`
      const body = await (await reader.request.get(url)).json()
      count += 1
      cursor = body.next_cursor
    } while (cursor && count < 20)
    return count
  })()
  expect(pages).toBeGreaterThan(1)

  for (let attempt = 0; attempt <= pages; attempt += 1) {
    if ((await reader.getByText(oldest, { exact: true }).count()) > 0) break
    await loader.click()
    await reader.waitForTimeout(300)
  }

  await expect(reader.getByText(oldest, { exact: true })).toBeVisible()

  // Every seeded message is on screen, which is the real assertion: not "the
  // load-more button exists" but "no message is unreachable".
  const bodies = await messageBodies(threadId)
  expect(bodies).toHaveLength(seeded)
  for (const body of bodies) {
    await expect(reader.getByText(body, { exact: true })).toHaveCount(1)
  }

  await readerContext.close()
  await senderContext.close()
})

// ─── B9: the photo round trip ───────────────────────────────────────────────

test('an oversized photo is refused and leaves the stored one alone', async ({ page }) => {
  await register(page, { name: uniqueName('Uploader') })
  const user = await me(page)
  expect(await photoCount(user.id)).toBe(0)

  await gotoSettled(page, '/profile/edit')
  const input = page.locator('input[type="file"]')
  await input.setInputFiles({ name: 'avatar.png', mimeType: 'image/png', buffer: TINY_PNG })

  await expect
    .poll(async () => photoCount(user.id), { timeout: 15_000 })
    .toBe(1)
  await expect
    .poll(async () => (await me(page)).profile.has_photo, { timeout: 15_000 })
    .toBe(true)

  // Over the 2 MB cap. The server reads the whole body first, so this is also
  // the assertion that the rejection leaves the database untouched.
  await input.setInputFiles({ name: 'huge.png', mimeType: 'image/png', buffer: OVERSIZED_PNG })

  await expect(page.getByRole('alert')).toBeVisible({ timeout: 20_000 })
  await expect
    .poll(async () => photoCount(user.id), { timeout: 15_000 })
    .toBe(1)
  await expect
    .poll(async () => (await me(page)).profile.has_photo, { timeout: 15_000 })
    .toBe(true)

  // And the original photo still serves, byte for byte.
  const served = await page.request.get('/api/v1/users/me/photo')
  expect(served.status()).toBe(200)
  expect(Buffer.from(await served.body())).toEqual(TINY_PNG)
})