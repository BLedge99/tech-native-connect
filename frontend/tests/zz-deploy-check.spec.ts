/** Manual deploy verification. Excluded from the default suite
 *  (playwright.config.ts testIgnore) — run it after a deploy:
 *    docker compose exec -T frontend npx playwright test zz-deploy-check
 *  Mirrors demo.spec.ts "request → accept → message" but waits for the
 *  PATCH acknowledgement. The race it was written to catch is now fixed in
 *  helpers.ts completeProfile(); this spec remains the end-to-end deploy
 *  smoke test. */
import { expect, test, type Page } from '@playwright/test'
import { gotoSettled, register, uniqueName } from './helpers'

async function saveProfile(page: Page, role: string, skill: string) {
  await page.goto('/profile/edit')
  await page.getByRole('radio', { name: role }).click()
  await page.getByPlaceholder('Search skills…').fill(skill)
  await page.getByRole('checkbox', { name: skill }).first().check()
  const saved = page.waitForResponse(
    (r) => r.url().includes('/api/v1/users/me') && r.request().method() === 'PATCH',
  )
  await page.getByRole('button', { name: 'Save profile' }).click()
  expect((await saved).status()).toBe(200)
  await expect(page.getByText(/^Saved\./)).toBeVisible()
}

test('deploy check: request → accept → live message over the socket', async ({ browser }) => {
  const businessContext = await browser.newContext()
  const devContext = await browser.newContext()
  const business = await businessContext.newPage()
  const dev = await devContext.newPage()

  const businessName = uniqueName('Priya Sharma')
  const devName = uniqueName('Tomas Nowak')

  await register(business, { name: businessName })
  await saveProfile(business, 'Business developer', 'Pitching')
  await register(dev, { name: devName })
  await saveProfile(dev, 'Software developer', 'Python')

  await gotoSettled(business, '/matches')
  await gotoSettled(dev, '/matches')
  await expect(business.getByText(devName).first()).toBeVisible()
  await business.getByText(devName).first().click()
  await business.getByRole('button', { name: 'Connect' }).click()
  await expect(business.getByText(/request sent/i)).toBeVisible()

  await gotoSettled(dev, '/connections?tab=received')
  await dev.getByRole('button', { name: 'Accept' }).click()

  const openConversation = async (page: Page, who: string) => {
    await page.getByRole('link', { name: 'Connections' }).click()
    await page.getByRole('tab', { name: /connected/i }).click()
    await page
      .getByRole('button', { name: 'Message', exact: true })
      .or(page.getByRole('link', { name: 'Message', exact: true }))
      .first()
      .click()
    await expect(page.getByLabel('Message')).toBeVisible()
    await expect(page.getByRole('link', { name: who })).toBeVisible()
  }
  await openConversation(business, devName)
  await openConversation(dev, businessName)

  await dev.getByLabel('Message').fill('Want to pair on the fintech idea?')
  await dev.getByRole('button', { name: 'Send' }).click()

  await expect(business.getByText('Want to pair on the fintech idea?')).toBeVisible()
  await expect(business.getByText('Want to pair on the fintech idea?')).toHaveCount(1)

  await business.getByLabel('Message').fill('Yes — I have the Figma mockups.')
  await business.getByRole('button', { name: 'Send' }).click()
  await expect(dev.getByText('Yes — I have the Figma mockups.')).toBeVisible()

  await dev.reload()
  await expect(dev.getByText('Want to pair on the fintech idea?')).toBeVisible()
})
