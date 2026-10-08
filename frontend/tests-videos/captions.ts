/** On-screen captions.
 *
 * A DOM overlay rather than an ffmpeg drawtext filter, because the caption is
 * then perfectly in sync with the action — no guessing timings — and because it
 * needs nothing from the host but ffmpeg's hstack for the two-perspective cut.
 *
 * The bar sits at the bottom over a body padding-bottom, so it reads like a
 * lower third and never covers the thing being demonstrated. An overlay across
 * the top hid the app's own nav on every page, which is part of the evidence.
 */

import type { Page } from '@playwright/test'

declare global {
  interface Window {
    __evidenceWindowLabel?: string
  }
}

const ID = '__evidence_caption'
const BAR = 38

const STYLE = {
  position: 'fixed',
  bottom: '0',
  left: '0',
  right: '0',
  zIndex: '2147483647',
  background: 'rgba(15, 23, 42, 0.94)',
  color: '#ffffff',
  font: '600 15px/1.4 system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
  padding: '9px 18px',
  textAlign: 'center',
  pointerEvents: 'none',
  boxSizing: 'border-box',
} as const

/** Create the bar if it is gone (a full page load wipes it) and set the text. */
async function write(page: Page, text: string): Promise<void> {
  await page.evaluate(
    ({ id, style, bar, text }) => {
      const paint = (id: string, style: Record<string, string>, top: boolean) => {
        let el = document.getElementById(id)
        if (!el) {
          el = document.createElement('div')
          el.id = id
          Object.assign(el.style, style)
          document.body.appendChild(el)
        }
        return el
      }
      paint(id, style, false).textContent = text
      // Lift the app clear of the bar instead of covering it.
      document.body.style.paddingBottom = `${bar}px`

      // Window name badge, for the two-perspective composites.
      const label = window.__evidenceWindowLabel as string | undefined
      const badge = paint('__evidence_window_label', {
        position: 'fixed',
        bottom: `${bar + 8}px`,
        left: '12px',
        zIndex: '2147483647',
        background: 'rgba(15, 23, 42, 0.94)',
        color: '#ffffff',
        font: '700 12px/1 system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
        padding: '7px 11px',
        borderRadius: '999px',
        pointerEvents: 'none',
      }, false)
      badge.textContent = label ?? ''
      badge.style.display = label ? 'block' : 'none'
    },
    { id: ID, style: STYLE, bar: BAR, text },
  )
}

export async function say(page: Page, text: string): Promise<void> {
  await write(page, text)
}

/** Let the caption land before the action it describes — otherwise the viewer
 *  reads about a click a beat after seeing it. */
export async function beat(page: Page, ms = 900): Promise<void> {
  await page.waitForTimeout(ms)
}

export async function step(page: Page, text: string, ms = 900): Promise<Page> {
  await write(page, text)
  await beat(page, ms)
  return page
}

/** Say the same thing on several pages at once — used by the two-perspective
 *  recordings, where both windows are showing the same step. */
export async function sayAll(pages: Page[], text: string): Promise<void> {
  await Promise.all(pages.map((page) => write(page, text)))
}