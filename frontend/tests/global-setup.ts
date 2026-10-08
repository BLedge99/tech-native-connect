/** Resets the demo data before an E2E run.
 *
 * Without this, every run leaves another dozen users named "Alice Sender" in
 * the database. Pages get slower, selectors built on `.first()` become
 * ambiguous, and the suite goes flaky in a way that looks like an app bug.
 *
 * Only removes users that are not part of the seed data — the demo cohort and
 * the five admins are what the E2E tests match against.
 *
 * Connects to Postgres directly rather than shelling out to `docker compose`:
 * this runs inside the frontend container, where the compose CLI is not
 * available.
 */

import { Client } from 'pg'
import type { FullConfig } from '@playwright/test'

const KEEP = [
  'priya@example.com',
  'tomas@example.com',
  'aisha@example.com',
  'liam@example.com',
  'mei@example.com',
  'jordan@example.com',
  'sam@example.com',
  'elena@example.com',
  'ravi@example.com',
  'hana@example.com',
]

const CONNECTION =
  process.env.E2E_DATABASE_URL ??
  'postgresql://bootcamp:bootcamp@db:5432/bootcamp_connect'

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const client = new Client({ connectionString: CONNECTION })
  try {
    await client.connect()
    const result = await client.query(
      `DELETE FROM users
       WHERE email <> ALL($1::citext[])
         AND email NOT LIKE '%@bootcamp.example.com'`,
      [KEEP],
    )
    console.log(`[e2e] demo data reset (${result.rowCount ?? 0} test users removed)`)
  } catch (err) {
    // Do not block the run: the tests still work against accumulated data, they
    // are just flakier. Say so loudly rather than failing for the wrong reason.
    console.warn(
      '[e2e] could not reset demo data — the suite may be flaky.\n' +
        `       ${CONNECTION}\n       ${String(err).slice(0, 200)}`,
    )
  } finally {
    await client.end().catch(() => {})
  }
}
