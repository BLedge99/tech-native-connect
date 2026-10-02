/** Helpers for the evidence recordings.
 *
 * Separate from tests/helpers.ts on purpose: those assert, these perform. Every
 * helper here leaves the page in a settled, visible state, because a video full
 * of spinners and half-loaded cards is not evidence of anything.
 */

import type { Browser, BrowserContext, Page } from '@playwright/test'
import { expect } from '@playwright/test'
import { beat, say, sayAll } from './captions'

export const VIDEO_DIR = '/app/videos-raw'
export const VIDEO_SIZE = { width: 1280, height: 800 }
export const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

let counter = 0

export function uniqueEmail(prefix: string): string {
  counter += 1
  const slug = prefix.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return `${slug || 'user'}-${Date.now().toString(36)}-${counter}@example.com`
}

/** Unique because the seeded cohort already contains a "Tomas Nowak", and a
 *  duplicate name makes every getByText ambiguous — which looks like a bug in
 *  the app and is not one. */
export function uniqueName(base: string): string {
  counter += 1
  return `${base} ${Math.random().toString(36).slice(2, 5).toUpperCase()}`
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export async function register(
  page: Page,
  opts: { name: string; email?: string; password?: string },
): Promise<string> {
  const email = opts.email ?? uniqueEmail(opts.name)
  await page.goto('/register')
  await say(page, 'Sign up — three fields, nothing else required')
  await beat(page)
  await page.getByLabel('Display name').fill(opts.name)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(opts.password ?? 'correct-horse')
  await beat(page, 600)
  await page.getByRole('button', { name: 'Sign up' }).click()
  // Waiting on the h1 is not enough: it is already on /register.
  await page.waitForURL((url) => !url.pathname.startsWith('/register'))
  return email
}

export async function login(page: Page, email: string, password = 'demo-password-123'): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await beat(page, 600)
  // Wait for the response, not the navigation: a wrong password renders an
  // inline error and stays put, which would otherwise look like a hung app.
  const response = page.waitForResponse((r) => r.url().includes('/api/v1/auth/login'))
  await page.getByRole('button', { name: 'Log in' }).click()
  const result = await response
  expect(result.status(), `login failed for ${email}`).toBe(200)
  await page.waitForURL((url) => !url.pathname.startsWith('/login'))
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
}

export async function loginSeeded(page: Page, name: string): Promise<void> {
  await say(page, `Sign in as ${name}, one of the seeded demo users`)
  await login(page, `${name.split(' ')[0].toLowerCase()}@example.com`)
}

export async function logout(page: Page): Promise<void> {
  const done = page.waitForResponse(
    (r) => r.url().includes('/api/v1/auth/logout') && r.status() === 204,
  )
  await page.getByRole('button', { name: 'Log out' }).click()
  await done
  // logout() ends in window.location.replace('/'), so this is a full load.
  await page.getByRole('link', { name: /sign up/i }).first().waitFor()
  await beat(page)
}

// ─── Profiles ────────────────────────────────────────────────────────────────

/** Role plus one skill: the minimum that unlocks matching (spec 04 §3). */
export async function completeProfile(
  page: Page,
  role: 'Software developer' | 'Business developer',
  skill: string,
): Promise<void> {
  await page.goto('/profile/edit')
  await say(page, 'Matching is locked until there is a role and one skill')
  await beat(page)
  await expect(page.getByText(/Matching needs a role and at least one skill/i)).toBeVisible()
  await page.getByRole('radio', { name: role }).click()
  await beat(page, 700)
  await page.getByPlaceholder('Search skills…').fill(skill)
  await page.getByRole('checkbox', { name: skill }).first().check()
  await beat(page, 500)
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Saved. Matching is unlocked.')).toBeVisible()
  await beat(page)
}

// ─── Two windows ─────────────────────────────────────────────────────────────

export interface Window {
  ctx: BrowserContext
  page: Page
  /** Close the context and rename its recording. saveAs() needs the close first. */
  save: (name: string) => Promise<void>
}

/** Two genuinely separate browsers with separate cookie jars — the only honest
 *  way to film a two-person feature. */
export async function twoWindows(browser: Browser, aLabel: string, bLabel: string): Promise<[Window, Window]> {
  const make = async (label: string): Promise<Window> => {
    const ctx = await browser.newContext({
      baseURL: BASE_URL,
      recordVideo: { dir: VIDEO_DIR, size: VIDEO_SIZE },
      viewport: VIDEO_SIZE,
    })
    // Label the window via a page global rather than addInitScript: the caption
    // machinery already repaints after every navigation, and an init script
    // silently did nothing on a document that was already loaded.
    await ctx.addInitScript((text) => {
      window.__evidenceWindowLabel = text
    }, label)
    const page = await ctx.newPage()
    // Go somewhere immediately. A window left on about:blank records a white
    // rectangle, which is half the picture saying nothing.
    await page.goto('/login')
    const win: Window = {
      ctx,
      page,
      save: async (name: string) => {
        const video = page.video()
        await ctx.close()
        if (video) await video.saveAs(`${VIDEO_DIR}/${name}.webm`)
      },
    }
    await say(page, label)
    return win
  }
  return [await make(aLabel), await make(bLabel)]
}

/** Say the same step in both windows and let it land. */
export async function stepBoth(a: Page, b: Page, text: string, ms = 900): Promise<void> {
  await sayAll([a, b], text)
  await beat(a, ms)
}

// ─── Magic link ──────────────────────────────────────────────────────────────

const MAILPIT = 'http://mailpit:8025'

/** Pull a sign-in link out of the Mailpit inbox.
 *
 * The link is minted against http://localhost:8000, which does not resolve
 * inside the frontend container. Navigating to it on the frontend origin works
 * because Vite proxies /api to the backend — same origin, no hardcoded host.
 */
export async function fetchMagicLink(email: string): Promise<string> {
  const list = await (await fetch(`${MAILPIT}/api/v1/messages?limit=50`)).json()
  const mine = (list.messages ?? [])
    .filter((m: { To?: { Address: string }[] }) =>
      m.To?.some((t) => t.Address.toLowerCase() === email.toLowerCase()),
    )
    .pop()
  if (!mine) throw new Error(`no Mailpit message for ${email}`)
  const full = await (await fetch(`${MAILPIT}/api/v1/message/${mine.ID}`)).json()
  const blob = `${full.HTML ?? ''}\n${full.Text ?? ''}`
  const match = blob.match(/magic-link\/verify\?token=([A-Za-z0-9_-]+)/)
  if (!match) throw new Error(`no magic link in message ${mine.ID}`)
  return match[1]
}

// ─── Repeatable demo data ────────────────────────────────────────────────────

const PG =
  process.env.E2E_DATABASE_URL ??
  'postgresql://bootcamp:bootcamp@db:5432/bootcamp_connect'

async function withDb<T>(fn: (client: import('pg').Client) => Promise<T>): Promise<T> {
  const { Client } = await import('pg')
  const client = new Client({ connectionString: PG })
  try {
    await client.connect()
    return await fn(client)
  } finally {
    await client.end().catch(() => {})
  }
}

/**
 * Delete ideas left by an earlier recording run.
 *
 * The ideas recording posts an idea with a fixed title, because a title with a
 * random suffix in it looks like debris in the finished video. That means every
 * run would otherwise leave another identical card behind, and two cards with
 * the same name is both a strict-mode selector failure and a video that looks
 * broken.
 *
 * Scoped to one exact title, so it cannot touch seeded demo data.
 */
export async function deleteIdeasTitled(title: string): Promise<void> {
  await withDb((db) =>
    db.query('DELETE FROM project_ideas WHERE title = $1', [title]).then(() => undefined),
  )
}

/**
 * Put a conversation back to a known state: empty, then one seeded message.
 *
 * The messaging recording asserts an exact bubble count, so anything a previous
 * run left in the thread makes the count wrong — and a video that only works on
 * a fresh database is not a deliverable. Deleting and re-inserting rather than
 * "keep the oldest" is deliberate: earlier attempts kept preserving a leftover
 * forever, because once the leftovers are the oldest rows, they are the history.
 *
 * Demo data only. There is no API for this and there should not be one.
 */
export async function resetThread(one: string, two: string): Promise<void> {
  await withDb(async (client) => {
    const pair = `(
       SELECT c.id FROM connection_requests c
        WHERE (c.sender_id = (SELECT id FROM users WHERE email = $1)
           AND c.receiver_id = (SELECT id FROM users WHERE email = $2))
           OR (c.sender_id = (SELECT id FROM users WHERE email = $2)
           AND c.receiver_id = (SELECT id FROM users WHERE email = $1)))`
    await client.query(`DELETE FROM messages WHERE thread_id =
       (SELECT t.id FROM threads t WHERE t.connection_request_id = ${pair})`, [one, two])
    await client.query(
      `INSERT INTO messages (thread_id, sender_id, body, created_at)
       VALUES ((SELECT t.id FROM threads t WHERE t.connection_request_id = ${pair}),
               (SELECT id FROM users WHERE email = $1),
               $3,
               now() - interval '2 hours')`,
      [one, two, 'Hey — is this still something you would want to build?'],
    )
  })
}

// ─── A real image to upload ──────────────────────────────────────────────────

/** A valid PNG, encoded here rather than shipped as a binary fixture.
 *
 * The profile photo is the one upload in the app, and a fake header passes the
 * type check but renders as a broken image — which is the opposite of evidence.
 * zlib is in the standard library, so this costs no dependency.
 */
export async function writeTestPng(path: string, rgb: [number, number, number]): Promise<string> {
  const { deflateSync } = await import('node:zlib')
  const { writeFile } = await import('node:fs/promises')
  const size = 240
  const raw = Buffer.alloc(size * (size * 3 + 1))
  let at = 0
  for (let y = 0; y < size; y++) {
    raw[at++] = 0 // filter: none
    for (let x = 0; x < size; x++) {
      // A soft diagonal gradient so it is visibly an image, not a flat square.
      const t = (x + y) / (size * 2)
      raw[at++] = Math.round(rgb[0] * (0.55 + 0.45 * t))
      raw[at++] = Math.round(rgb[1] * (0.55 + 0.45 * t))
      raw[at++] = Math.round(rgb[2] * (0.55 + 0.45 * t))
    }
  }
  const chunk = (type: string, data: Buffer): Buffer => {
    const len = Buffer.alloc(4)
    len.writeUInt32BE(data.length)
    const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
    const crc = Buffer.alloc(4)
    crc.writeUInt32BE(crc32(body) >>> 0)
    return Buffer.concat([len, body, crc])
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 2 // truecolour
  await writeFile(
    path,
    Buffer.concat([
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
      chunk('IHDR', ihdr),
      chunk('IDAT', deflateSync(raw)),
      chunk('IEND', Buffer.alloc(0)),
    ]),
  )
  return path
}

const CRC_TABLE = (() => {
  const table = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c
  }
  return table
})()

function crc32(buf: Buffer): number {
  let c = 0xffffffff
  for (const byte of buf) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}