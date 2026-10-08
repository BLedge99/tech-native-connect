import { expect, test } from '@playwright/test'

/**
 * Dev tooling contract tests.
 *
 * The bug this suite was written for: the dev panel told developers to log in
 * to Adminer with `bootcamp_connect`, a hand-typed database name that is one
 * keystroke away from the non-existent `bootcamp-connect`. The failure was
 * invisible to the product suite because Adminer is not part of the product.
 *
 * These tests drive the real containers. A misconfigured service fails here
 * rather than in front of a demo.
 */

/**
 * These tests run INSIDE the compose network (see the exec commands in
 * run.bat), so service names resolve as hostnames and published localhost
 * ports do not. Overridable for running the same suite against a browser on
 * the host instead.
 */
const ADMINER = process.env.ADMINER_URL ?? 'http://adminer:8080'
const MAILPIT = process.env.MAILPIT_URL ?? 'http://mailpit:8025'
const DEV_PANEL = '/dev'

/** Values must match docker-compose.yml. Underscores, not hyphens. */
const DB = {
  server: 'db',
  username: 'bootcamp',
  password: 'bootcamp',
  database: 'bootcamp_connect',
}

test.describe('Adminer DB GUI', () => {
  test('a developer can reach Adminer and it is not erroring', async ({ page }) => {
    const failures: string[] = []
    page.on('pageerror', (err) => failures.push(err.message))
    page.on('console', (msg) => {
      if (msg.type() === 'error') failures.push(msg.text())
    })

    const response = await page.goto(ADMINER, { waitUntil: 'domcontentloaded' })
    expect(response?.status(), 'Adminer must answer 200').toBe(200)

    // The failure mode we are guarding against: a PHP fatal such as
    // "Cannot redeclare function adminer_object()".
    const body = await page.locator('body').innerText()
    expect(body, 'no PHP fatal error').not.toContain('Fatal error')
    expect(body, 'no PHP parse error').not.toContain('Parse error')
    expect(body, 'no redeclare error').not.toContain('Cannot redeclare')
    expect(failures, `console/page errors: ${failures.join(' | ')}`).toEqual([])
  })

  test('credentials from the dev panel log in and expose the project DB', async ({ page }) => {
    await page.goto(`${ADMINER}/?pgsql=${DB.server}`, { waitUntil: 'domcontentloaded' })

    const needsLogin = await page.locator('input[name="auth[password]"]').count()
    test.skip(needsLogin === 0, 'Adminer autologin already established a session')

    await page.fill('input[name="auth[server]"]', DB.server)
    await page.fill('input[name="auth[username]"]', DB.username)
    await page.fill('input[name="auth[password]"]', DB.password)
    await page.fill('input[name="auth[db]"]', DB.database)
    await page.click('input[type="submit"]')
    await page.waitForLoadState('domcontentloaded')

    const body = await page.locator('body').innerText()

    // The regression this test exists for.
    expect(body, 'database name typo — must be bootcamp_connect').not.toContain('does not exist')
    expect(body, 'login must not be rejected').not.toContain('Invalid credentials')

    // Proof the data is actually reachable, not just that the page rendered.
    await expect(
      page.locator('a', { hasText: 'bootcamp_connect' }).first(),
      'project database should be listed',
    ).toBeVisible()
  })

  test('the project tables are visible once logged in', async ({ page }) => {
    await page.goto(`${ADMINER}/?pgsql=${DB.server}`, { waitUntil: 'domcontentloaded' })

    if (await page.locator('input[name="auth[password]"]').count()) {
      await page.fill('input[name="auth[server]"]', DB.server)
      await page.fill('input[name="auth[username]"]', DB.username)
      await page.fill('input[name="auth[password]"]', DB.password)
      await page.fill('input[name="auth[db]"]', DB.database)
      await page.click('input[type="submit"]')
      await page.waitForLoadState('domcontentloaded')
    }

    // ?sql= is Adminer's table-list view. Asserting on it is the real check:
    // proving a migrated schema is readable, not just that a page rendered.
    await page.goto(
      `${ADMINER}/?pgsql=${DB.server}&username=${DB.username}&db=${DB.database}&sql=`,
      { waitUntil: 'domcontentloaded' },
    )

    const body = await page.locator('body').innerText()
    expect(body, 'no SQL error').not.toContain('does not exist')

    // Tables created by the app's migrations. Names are the real ones from
    // 0001_initial — connection_requests, not connections.
    for (const table of ['users', 'connection_requests', 'notifications', 'threads']) {
      await expect(page.locator('a', { hasText: table, exact: true }).first(),
        `${table} table should be listed`).toBeVisible()
    }
  })
})

test.describe('Mailpit', () => {
  test('web inbox is reachable', async ({ page }) => {
    const response = await page.goto(MAILPIT, { waitUntil: 'domcontentloaded' })
    expect(response?.status()).toBe(200)
    await expect(page.locator('body')).toContainText(/mail|message|inbox/i)
  })
})

test.describe('Dev panel', () => {
  test('services tab lists every dev service with correct DB credentials', async ({ page }) => {
    await page.goto(DEV_PANEL)
    await expect(page.getByRole('heading', { name: 'Dev Panel' })).toBeVisible()

    for (const label of ['Main Site', 'API Docs', 'Mailpit', 'Database']) {
      await expect(page.getByRole('heading', { name: label, exact: true })).toBeVisible()
    }

    // The credentials shown must match what the container actually accepts.
    const dbCard = page.locator('a', { hasText: 'Database' }).first()
    await expect(dbCard).toContainText('bootcamp_connect')
    // Regression guard: the hyphenated typo must never reappear.
    await expect(dbCard).not.toContainText('bootcamp-connect')
  })

  test('videos tab serves real mp4 bytes from the backend', async ({ page }) => {
    await page.goto(DEV_PANEL)
    await page.getByRole('button', { name: 'Videos' }).click()

    const video = page.locator('video').first()
    await expect(video).toBeVisible()

    // metadata= means the browser will range-request the file. A 404 here is
    // the failure we previously shipped.
    const src = await video.getAttribute('src')
    expect(src).toBeTruthy()

    const response = await page.request.get(src!, { headers: { Range: 'bytes=0-1023' } })
    expect(response.status(), `video fetch for ${src}`).toBeLessThan(400)
    expect(response.headers()['content-type']).toContain('video/mp4')
  })
})