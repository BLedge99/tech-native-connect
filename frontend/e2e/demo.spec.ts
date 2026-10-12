import { expect, test, type Page } from '@playwright/test';

const password = 'Demo-E2E-Password-2026!';

async function registerAndCompleteProfile(
  page: Page,
  email: string,
  name: string,
  role: 'software_developer' | 'business_developer',
) {
  await page.goto('/register');
  await page.getByLabel('Your name').fill(name);
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: /create account/i }).click();

  await expect(page.getByText('Add a role and at least one skill to see matches.')).toBeVisible();
  await page.getByRole('link', { name: 'Edit profile ↗' }).click();
  await page.getByLabel('Your role').selectOption(role);
  await expect(page.getByLabel('Your role')).toHaveValue(role);
  await page.getByLabel('Python').check();
  await expect(page.getByLabel('Python')).toBeChecked();
  await page.getByRole('button', { name: /save profile/i }).click();
  await expect(page.getByText('Profile saved.')).toBeVisible();
}

test('two cohort members match, connect, and exchange live messages', async ({ browser }) => {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();
  const runId = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
  const nameA = `E2E Builder ${runId}`;
  const nameB = `E2E Partner ${runId}`;
  const emailA = `e2e-builder-${runId}@example.com`;
  const emailB = `e2e-partner-${runId}@example.com`;
  const firstMessage = `Starting a demo conversation ${runId}.`;
  const liveMessage = `Live message received ${runId}.`;

  try {
    await registerAndCompleteProfile(pageA, emailA, nameA, 'software_developer');
    await registerAndCompleteProfile(pageB, emailB, nameB, 'business_developer');

    await pageA.getByRole('link', { name: 'Matches' }).click();
    const candidate = pageA.locator('.match-card').filter({ hasText: nameB });
    await expect(candidate).toBeVisible();
    await candidate.getByRole('button', { name: 'Connect' }).click();
    await expect(candidate.getByText('Request sent')).toBeVisible();

    await pageB.getByRole('link', { name: 'Connections' }).click();
    const incoming = pageB.locator('.list-card').filter({ hasText: nameA });
    await expect(incoming).toBeVisible();
    await incoming.getByRole('button', { name: 'Accept' }).click();

    await pageA.getByRole('link', { name: 'Connections' }).click();
    await pageA.getByRole('tab', { name: 'Connected' }).click();
    const accepted = pageA.locator('.list-card').filter({ hasText: nameB });
    await accepted.getByRole('link', { name: /open messages/i }).click();
    await pageA.getByLabel('Your message').fill(firstMessage);
    await pageA.getByRole('button', { name: /^send/i }).click();
    await expect(pageA).toHaveURL(/\/messages\/[0-9a-f-]+$/i);

    await pageB.goto('/messages');
    const thread = pageB.locator('.thread-card').filter({ hasText: nameA });
    await expect(thread).toBeVisible();
    await thread.click();
    await expect(pageB.getByText(firstMessage)).toBeVisible();
    await expect(pageB.getByText('Live connection')).toBeVisible();

    await pageA.getByLabel('Your message').fill(liveMessage);
    await pageA.getByRole('button', { name: /^send/i }).click();
    await expect(pageB.getByText(liveMessage)).toBeVisible();

    await pageB.getByRole('link', { name: /notifications/i }).click();
    await expect(pageB.getByText(`${nameA} sent you a message`)).toHaveCount(2);
  } finally {
    await contextA.close();
    await contextB.close();
  }
});
