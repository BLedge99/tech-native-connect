/** Two-perspective recordings.
 *
 * Two separate browser contexts with separate cookie jars, because that is the
 * only honest way to film a feature that needs two people. Each window records
 * its own video; scripts/build-videos.sh hstacks the pair into one file.
 *
 * These tests deliberately do NOT use ./record — there is no default page here,
 * only two hand-made windows, so there is nothing for that fixture to save.
 */

import { expect, test } from '@playwright/test'
import { beat, say, sayAll } from './captions'
import {
  completeProfile,
  register,
  twoWindows,
  uniqueEmail,
  resetThread,
  uniqueName,
} from './helpers'

test.describe.configure({ mode: 'serial' })

/**
 * The settled bubble, as opposed to the optimistic one.
 *
 * Sending renders a pending copy immediately (marked `opacity-60`) and then
 * replaces it with the server's copy once the POST resolves. Waiting for the
 * non-pending bubble is therefore both "it arrived" and "the optimistic copy was
 * reconciled" — and :not(.opacity-60) is what distinguishes them.
 */
function bubble(page: import('@playwright/test').Page, body: string) {
  return page.locator('div.rounded-2xl:not(.opacity-60)', { hasText: body })
}

/** Type, send, and wait for the message to be settled — exactly once. */
async function sendMessage(page: import('@playwright/test').Page, body: string): Promise<void> {
  await page.getByLabel('Message').fill(body)
  await beat(page, 700)
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(bubble(page, body)).toHaveCount(1)
  await beat(page, 500)
}

// ─── 05 · Connection requests, both sides — spec 05 ──────────────────────────

test('05 connection requests — two windows', async ({ browser }) => {
  const [biz, dev] = await twoWindows(browser, 'A · new business developer', 'B · Tomas, software developer')

  // ── A: sign up and complete a profile ──────────────────────────────────────
  await register(biz.page, { name: uniqueName('Iris Delgado') })
  await expect(biz.page.getByText(/add a role and at least one skill/i)).toBeVisible()
  await sayAll([biz.page], 'A signs up — matching stays locked until there is a role and a skill')
  await beat(biz.page, 2400)

  await completeProfile(biz.page, 'Business developer', 'Pitching')
  await biz.page.goto('/profile/edit')
  await biz.page.getByPlaceholder('Search interests…').fill('Fintech')
  await biz.page.getByRole('checkbox', { name: 'Fintech' }).first().check()
  await beat(biz.page, 900)
  await sayAll([biz.page], 'A adds interests — these become the "why you matched" reasons')
  await beat(biz.page, 2200)

  // ── B: sign in as a seeded developer ───────────────────────────────────────
  await dev.page.goto('/login')
  await dev.page.getByLabel('Email').fill('tomas@example.com')
  await dev.page.getByLabel('Password').fill('demo-password-123')
  await sayAll([dev.page], 'B is already signed in as Tomas, a seeded developer')
  await beat(dev.page, 1200)
  await dev.page.getByRole('button', { name: 'Log in' }).click()
  await dev.page.waitForURL((url) => !url.pathname.startsWith('/login'))
  await beat(dev.page, 1800)

  // ── A: browse matches and send a request ───────────────────────────────────
  await biz.page.goto('/matches')
  // exact: the cohort also contains test users called "Tomas Nowak T82".
  const tomasCard = biz.page.getByRole('heading', { level: 3, name: 'Tomas Nowak', exact: true })
  await expect(tomasCard).toBeVisible()
  await sayAll([biz.page], 'A sees the whole course, ranked, each with a reason')
  await beat(biz.page, 2800)

  await tomasCard.click()
  await expect(biz.page.getByRole('heading', { level: 1 })).toBeVisible()
  await beat(biz.page, 2400)
  await sayAll([biz.page], 'A opens Tomas: shared Fintech interest is the stated reason')
  await beat(biz.page, 2400)

  await biz.page.mouse.wheel(0, 400)
  await beat(biz.page, 1800)
  await biz.page.mouse.wheel(0, -400)
  await beat(biz.page, 700)

  await biz.page.getByRole('button', { name: 'Connect' }).click()
  await expect(biz.page.getByText(/request sent|request/i).first()).toBeVisible()
  await sayAll([biz.page], 'A sends a request. Nothing is mutual yet.')
  await beat(biz.page, 2600)

  // ── Rule 2: no thread until both have accepted ─────────────────────────────
  await biz.page.goto('/messages')
  await expect(biz.page.getByText(/No conversations yet/i)).toBeVisible()
  await sayAll([biz.page], 'Rule 2 — A cannot message yet. Expressing interest is not permission.')
  await beat(biz.page, 3000)
  await sayAll([dev.page], 'B has not accepted. A one-sided conversation would be a data leak.')
  await beat(dev.page, 1200)

  // ── B: sees the request and accepts ────────────────────────────────────────
  await dev.page.goto('/connections?tab=received')
  await expect(dev.page.getByText(/Iris/)).toBeVisible()
  await sayAll([dev.page], 'B sees the request in their notifications and connections')
  await beat(dev.page, 3000)

  await dev.page.getByRole('button', { name: 'Decline' }).first().waitFor()
  await sayAll([dev.page], 'Accept or decline — B decides. A cannot accept their own request.')
  await beat(dev.page, 2400)

  await dev.page.getByRole('button', { name: 'Accept' }).first().click()
  await expect(dev.page.getByText('Connected')).toBeVisible()
  await sayAll([dev.page], 'B accepts — now, and only now, a conversation can exist')
  await beat(dev.page, 3000)

  // ── A: sees the acceptance ─────────────────────────────────────────────────
  await biz.page.goto('/connections?tab=connected')
  await expect(biz.page.getByText('Connected').first()).toBeVisible()
  await sayAll([biz.page], 'A is told immediately — the three tabs: received, sent, connected')
  await beat(biz.page, 2600)

  await dev.page.getByRole('tab', { name: /sent/ }).click()
  await beat(dev.page, 1600)
  await dev.page.getByRole('tab', { name: /connected/ }).click()
  await beat(dev.page, 2000)

  await biz.save('05-connection-requests-two-windows__A')
  await dev.save('05-connection-requests-two-windows__B')
})

// ─── 07 · Live messaging, both sides — spec 06 (the centrepiece) ─────────────

test('07 live messaging — two windows', async ({ browser }) => {
  // A repeatable starting point: the seeded thread, trimmed to one message.
  await resetThread('aisha@example.com', 'liam@example.com')

  const [aisha, liam] = await twoWindows(browser, 'A · Aisha, business developer', 'B · Liam, software developer')

  const signIn = async (page: import('@playwright/test').Page, who: string, email: string) => {
    await page.goto('/login')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill('demo-password-123')
    await beat(page, 900)
    await page.getByRole('button', { name: 'Log in' }).click()
    await page.waitForURL((url) => !url.pathname.startsWith('/login'))
    await sayAll([page], `${who} signs in`)
    await beat(page, 1800)
  }

  await signIn(aisha.page, 'A', 'aisha@example.com')
  await signIn(liam.page, 'B', 'liam@example.com')

  // ── The conversation list ──────────────────────────────────────────────────
  await aisha.page.goto('/messages')
  await expect(aisha.page.getByRole('link', { name: /Liam/ })).toBeVisible()
  await liam.page.goto('/messages')
  await expect(liam.page.getByRole('link', { name: /Aisha/ })).toBeVisible()
  await sayAll([aisha.page, liam.page], 'Both open Messages — one thread, seeded with history')
  await beat(aisha.page, 3000)

  // ── Open the same thread in both windows ───────────────────────────────────
  await aisha.page.getByRole('link', { name: /Liam/ }).click()
  await expect(aisha.page.getByLabel('Message')).toBeVisible()
  await liam.page.getByRole('link', { name: /Aisha/ }).click()
  await expect(liam.page.getByLabel('Message')).toBeVisible()
  await sayAll([aisha.page, liam.page], 'Same thread, two browsers, two WebSocket subscriptions')
  await beat(aisha.page, 3200)

  await sayAll([aisha.page, liam.page], 'History loaded from the server, not from memory')
  await beat(aisha.page, 2600)

  await aisha.page.goto('/messages')
  await expect(aisha.page.getByRole('link', { name: /Liam/ })).toBeVisible()
  await sayAll([aisha.page], 'Unread counts live on the thread list, and clear on open')
  await beat(aisha.page, 2400)
  await aisha.page.getByRole('link', { name: /Liam/ }).click()
  await expect(aisha.page.getByLabel('Message')).toBeVisible()
  await beat(aisha.page, 1200)

  // ── Live delivery, A to B ──────────────────────────────────────────────────
  await sayAll([liam.page], 'B waits with the thread open — no refresh, no polling')
  await beat(liam.page, 1600)

  await sendMessage(aisha.page, 'Are you free Thursday to sketch the data model?')
  await expect(bubble(liam.page, 'Are you free Thursday to sketch the data model?')).toHaveCount(1)
  await sayAll([aisha.page, liam.page], 'A sends. It arrives in B over the WebSocket — no refresh.')
  await beat(aisha.page, 3400)

  // ── Live delivery, B to A ──────────────────────────────────────────────────
  await sendMessage(liam.page, 'Yes. I will bring a schema and a docker-compose.')
  await expect(bubble(aisha.page, 'Yes. I will bring a schema and a docker-compose.')).toHaveCount(1)
  await sayAll([aisha.page, liam.page], 'And straight back the other way')
  await beat(aisha.page, 3400)

  // ── Survives a reload ──────────────────────────────────────────────────────
  // Both windows reload. This is the real test of the socket: a fresh page load
  // means a fresh WebSocket, and the subscription has to be re-established
  // before the next message can arrive live.
  await aisha.page.reload()
  await liam.page.reload()
  await expect(aisha.page.getByLabel('Message')).toBeVisible()
  await expect(liam.page.getByLabel('Message')).toBeVisible()
  await expect(bubble(aisha.page, 'Yes. I will bring a schema and a docker-compose.')).toHaveCount(1)
  await sayAll([aisha.page, liam.page], 'Both windows reload: history intact, from Postgres')
  await beat(aisha.page, 3400)

  // ── And a third message to prove the socket is still live ──────────────────
  await sendMessage(aisha.page, 'Booking the study room now.')
  await expect(bubble(liam.page, 'Booking the study room now.')).toHaveCount(1)
  await sayAll([aisha.page, liam.page], 'Still live after a reload — the socket re-subscribes')
  await beat(aisha.page, 3400)

  await aisha.save('07-live-messaging-two-windows__A')
  await liam.save('07-live-messaging-two-windows__B')
})