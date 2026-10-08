/** A `test` that always saves its video under a stable, ordered filename.
 *
 * Playwright names recorded videos by an internal context hash, which tells you
 * nothing six days later. This renames them to the spec title on the way out.
 *
 * saveAs() blocks until the page closes and the file is complete, so it has to
 * happen in fixture teardown — not at the end of the test body.
 */

import { test as base } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const OUT = '/app/videos-raw'

function filename(title: string): string {
  return (
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 80) + '.webm'
  )
}

export const test = base.extend<{ record: void }>({
  record: [
    async ({ page, context }, use, testInfo) => {
      await use()
      const video = page.video()
      if (!video) return
      await mkdir(OUT, { recursive: true })
      // The context MUST be closed before saveAs() resolves — the video is only
      // finalised when the page goes away. Fixtures tear down in reverse order,
      // so `page` is still alive here and saveAs() would block until the test
      // times out. Closing it ourselves first is idempotent; Playwright's own
      // teardown then has nothing left to do.
      await context.close()
      await video.saveAs(path.join(OUT, filename(testInfo.title)))
    },
    { auto: true },
  ],
})

export { expect } from '@playwright/test'