/**
 * Direct Postgres reads for the E2E suite.
 *
 * Every assertion in the regression suite has an independent witness, and for
 * "the server stored the right thing" that witness is the database. A status
 * code and a rendered page can both be produced by a handler that never wrote
 * a row; a row cannot.
 *
 * `pg` is already a devDependency — global-setup.ts uses it — so this costs no
 * new dependency and no new container.
 *
 * The connection is lazy and reused. global-setup.ts opens its own short-lived
 * client instead because it runs once; here it would be wasteful to reconnect
 * per assertion.
 */

import { Client } from 'pg'

const CONNECTION =
  process.env.E2E_DATABASE_URL ??
  'postgresql://bootcamp:bootcamp@db:5432/bootcamp_connect'

let client: Client | null = null

/** A connected client, reconnecting if the previous one went away. */
async function connection(): Promise<Client> {
  if (client) return client
  const fresh = new Client({ connectionString: CONNECTION })
  await fresh.connect()
  client = fresh
  return fresh
}

/** Run one parameterised query and return its rows. */
export async function rows<T = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  const db = await connection()
  try {
    return (await db.query(sql, params)).rows as T[]
  } catch (err) {
    // A dropped connection should not poison every later assertion.
    await db.end().catch(() => {})
    client = null
    throw err
  }
}

/** Run one parameterised query and return the first row, or null. */
export async function row<T = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T | null> {
  const found = await rows<T>(sql, params)
  return found.length ? found[0] : null
}

/** A single scalar value, e.g. a COUNT. */
export async function scalar(sql: string, params: unknown[] = []): Promise<unknown> {
  const found = await rows<Record<string, unknown>>(sql, params)
  return found.length ? Object.values(found[0])[0] : null
}

/** Close the shared connection. Called from a Playwright teardown hook. */
export async function closeDb(): Promise<void> {
  if (!client) return
  await client.end().catch(() => {})
  client = null
}

// ─── Queries used by the regression suite ───────────────────────────────────

/** The user id for an email address, or null. */
export function userIdByEmail(email: string) {
  return scalar('SELECT id FROM users WHERE email = $1', [email.toLowerCase()])
}

/** How many photos are stored for a user. */
export function photoCount(userId: string) {
  return scalar('SELECT count(*)::int AS n FROM photos WHERE user_id = $1::uuid', [userId])
}

/** Every message body in a thread, oldest first. */
export function messageBodies(threadId: string) {
  return rows<{ body: string }>(
    'SELECT body FROM messages WHERE thread_id = $1::uuid ORDER BY created_at ASC, id ASC',
    [threadId],
  ).then((found) => found.map((r) => r.body))
}

export function messageCount(threadId: string) {
  return scalar('SELECT count(*)::int AS n FROM messages WHERE thread_id = $1::uuid', [threadId])
}

/** Unread messages per thread for a user, computed straight in SQL.
 *
 * Deliberately independent of both endpoints under test: if `/threads` and
 * `/connections/summary` agree with each other but not with the database, the
 * conservation test catches it.
 */
export function unreadPerThread(userId: string) {
  return rows<{ thread_id: string; unread: number }>(
    `SELECT t.id AS thread_id,
            count(m.id)::int AS unread
       FROM threads t
       JOIN connection_requests c ON c.id = t.connection_request_id
       LEFT JOIN messages m
              ON m.thread_id = t.id
             AND m.sender_id <> $1::uuid
             AND NOT EXISTS (
                   SELECT 1 FROM read_receipts r
                    WHERE r.thread_id = t.id
                      AND r.user_id = $1::uuid
                      AND m.created_at <= r.last_read_at
                 )
      WHERE (c.sender_id = $1::uuid OR c.receiver_id = $1::uuid)
        AND c.status = 'accepted'
      GROUP BY t.id`,
    [userId],
  )
}

/** Total unread messages across every accepted thread for a user. */
export function unreadTotal(userId: string) {
  return unreadPerThread(userId).then((found) =>
    found.reduce((sum, entry) => sum + Number(entry.unread), 0),
  )
}

/** Live sessions for a user — the witness that a logout really revoked one. */
export function sessionCount(userId: string) {
  return scalar('SELECT count(*)::int AS n FROM sessions WHERE user_id = $1::uuid', [userId])
}