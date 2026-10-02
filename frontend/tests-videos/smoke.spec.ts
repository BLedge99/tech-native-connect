import { beat, say } from './captions'
import { expect, test } from './record'

test('00 smoke — landing page', async ({ page }) => {
  await page.goto('/')
  await say(page, 'Smoke test: does the recorder work?')
  await beat(page, 1500)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await beat(page, 800)
})