/**
 * Public reachability over the Cloudflare Quick Tunnel.
 *
 * Skipped unless TUNNEL_URL is set, so the default suite is unaffected:
 *
 *   ./run.bat tunnel
 *   docker compose exec -T -e TUNNEL_URL=https://<printed-url> \
 *     frontend npx playwright test tunnel.spec.ts
 *
 * ## Why this file exists
 *
 * Cloudflare error 1033 ("the edge knows this hostname but no cloudflared
 * instance is registered for it") only ever appeared for other people's
 * devices, never for the machine hosting the site. Nothing in the app could
 * reproduce it, because the app was never the problem.
 *
 * This suite is the reproduction. The Playwright container is on the Compose
 * bridge network, not on the host's loopback — so `http://localhost:5173` and
 * `https://<host>.trycloudflare.com` are genuinely different network paths.
 * Anything that resolves on the host but not elsewhere fails here.
 *
 * Same two rules as regression.spec.ts: no network mocking, and every
 * assertion has a witness that is not the rendered page.
 */

import { expect, test } from '@playwright/test'
import { gotoSettled, login, logout, register } from './helpers'

const TUNNEL = process.env.TUNNEL_URL?.replace(/\/+$/, '')

// Overrides baseURL so helpers/relative paths go to the public hostname.
// Without this every goto() would hit the container's own localhost.
test.use({ baseURL: TUNNEL })

test.skip(!TUNNEL, 'set TUNNEL_URL to the URL printed by `run.bat tunnel`')

test.describe('cloudflare tunnel is reachable from off-host', () => {
  test('serves the health endpoint', async ({ request }) => {
    const response = await request.get(`${TUNNEL}/api/v1/health`)
    expect(response.status()).toBe(200)
    expect(await response.json()).toMatchObject({ status: 'ok', database: 'ok' })
  })

  test('serves the landing page and its assets', async ({ page }) => {
    const bad: string[] = []
    page.on('requestfailed', (r) => bad.push(`${r.url()} ${r.failure()?.errorText}`))
    page.on('response', (r) => {
      if (r.status() >= 400) bad.push(`${r.url()} ${r.status()}`)
    })

    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      /Meet the other half of your bootcamp/,
    )

    // A signed-out visitor's session probe answers 401. That is correct, and
    // it is the proof the Vite proxy and the CORS regex both survived the
    // tunnel — a 401 is a real response from the backend, not a blocked one.
    // HMR chatter is legitimately noisy; everything else must be clean.
    const real = bad.filter(
      (b) => !/__vite|hot-update|websocket/i.test(b) && !b.endsWith('/api/v1/users/me 401'),
    )
    expect(real).toEqual([])
  })

  test('signs in and loads matches under the tunnel origin', async ({ page }) => {
    await login(page, 'priya@example.com', 'demo-password-123')
    // login() waits for the response, not the navigation it triggers. Settle
    // before asserting, or this races the client-side redirect.
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()

    // Independent witness for the UI: the session cookie must have been set
    // for THIS host, not left behind on localhost.
    const cookies = await page.context().cookies()
    const session = cookies.find((c) => c.name === 'session')
    expect(session, 'no session cookie over the tunnel').toBeTruthy()
    expect(session!.domain).toContain('trycloudflare.com')

    await gotoSettled(page, '/matches')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    // Signed in, not bounced to /login.
    expect(new URL(page.url()).pathname).toBe('/matches')
  })

  test('accepts the WebSocket handshake from a tunnel origin', async ({ page }) => {
    await login(page, 'priya@example.com', 'demo-password-123')
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()

    // The real browser WebSocket's own readyState. The app's socket is inside
    // a provider; opening a second one is the independent check that the
    // origin check in routers/messaging.py accepts a trycloudflare.com Origin
    // — if it does not, the socket closes 1008 and live messaging is dead for
    // every visitor outside the host machine while working on localhost.
    //
    // `WebSocket` is not a global in the Playwright process, so the expected
    // constant is read from inside the page.
    const OPEN = await page.evaluate(() => WebSocket.OPEN)
    const result = await page.evaluate(
      () =>
        new Promise<{ state: number; closeCode: number }>((resolve) => {
          const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
          const socket = new WebSocket(`${proto}://${window.location.host}/api/v1/ws`)
          const timer = setTimeout(
            () => resolve({ state: socket.readyState, closeCode: -1 }),
            10_000,
          )
          socket.onopen = () => {
            clearTimeout(timer)
            resolve({ state: socket.readyState, closeCode: 0 })
          }
          socket.onerror = () => {
            clearTimeout(timer)
            resolve({ state: socket.readyState, closeCode: -1 })
          }
          socket.onclose = (e) => {
            clearTimeout(timer)
            resolve({ state: socket.readyState, closeCode: e.code })
          }
        }),
    )

    expect(result.closeCode, 'handshake was refused').toBe(0)
    expect(result.state).toBe(OPEN)
  })
})
/**
 * The journey a visitor actually walks over the tunnel, in the order they walk
 * it. Added after a report that registration worked, logging out worked, and
 * then logging back in did not.
 */
test.describe('an external visitor can register, sign out and sign back in', () => {
  test('the same credentials work after a sign out', async ({ page }) => {
    const email = `tunnel-roundtrip-${Date.now()}@example.com`
    const password = 'round-trip-password'

    await register(page, { email, name: 'Round Trip', password })
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()

    await logout(page)

    await login(page, email, password)
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
    expect(new URL(page.url()).pathname).not.toBe('/login')
  })
})

test.describe('the sign-in-link page helps an external visitor', () => {
  test('an unknown address does not dead-end on localhost:8025', async ({ page }) => {
    await page.goto('/forgot-password')
    await page.getByLabel('Email').fill(`nobody-here-${Date.now()}@example.com`)
    await page.getByRole('button', { name: 'Send me a link' }).click()

    // An address with no account correctly gets no link. What it must not do
    // is point the visitor at a dev inbox on their own machine.
    const body = page.locator('body')
    await expect(body).not.toContainText('localhost:8025')
    await expect(body).toContainText(/sign up|create an account|register/i)
  })
})
