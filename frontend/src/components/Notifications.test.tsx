/**
 * Notification bell and toast stack.
 *
 * Added 8 October 2026 with the §12 review, before the fix.
 *
 *   B4  the toast dedupe is inverted: within five seconds of the same actor it
 *       deletes the OLDEST toast — an unrelated one — and discards the new
 *       notification, which is the opposite of what its comment claims
 *
 * This is a component test rather than Playwright because the behaviour turns
 * on a five second window keyed by actor. In jsdom the window is deterministic
 * and there is no clock to race.
 *
 * The policy the tests pin: **a repeat is suppressed, and nothing else is
 * touched.** A toast from an unrelated actor must survive, and the duplicate
 * must not appear twice.
 */

import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, type Mock, test, vi } from 'vitest'

import { SessionContext, type SessionValue } from '../hooks/session'

const socket = vi.hoisted(() => ({
  listeners: [] as Array<(frame: Record<string, unknown>) => void>,
}))

vi.mock('../hooks/websocket', async () => {
  const React = await import('react')
  return {
    useSocket: () => ({
      status: 'open' as const,
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      send: vi.fn(() => true),
      onMessage: () => () => {},
      onNotification: () => () => {},
    }),
    useSocketListener: (_event: string, listener: (frame: Record<string, unknown>) => void) => {
      const ref = React.useRef(listener)
      ref.current = listener
      React.useEffect(() => {
        socket.listeners.push((frame) => ref.current(frame))
        return () => {
          socket.listeners = socket.listeners.filter((entry) => entry !== listener)
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [])
    },
    useThreadSubscription: () => {},
  }
})

vi.mock('../api/client', () => ({
  notifications: {
    list: vi.fn(async () => ({ items: [], next_cursor: null })),
    unreadCount: vi.fn(async () => ({ unread_count: 0 })),
    markRead: vi.fn(async () => ({})),
    markAllRead: vi.fn(async () => undefined),
  },
}))

import { NotificationBell, ToastStack } from './Notifications'

const ME = 'me-id'

const session = {
  user: { id: ME, display_name: 'Me', first_name: 'Me', email: 'me@example.com' },
  loading: false,
} as unknown as SessionValue

/** A notification frame as the server pushes it. */
function frame(id: string, text: string, actorId: string) {
  return {
    type: 'notification',
    data: { id, type: 'connection_requested', text, actor_id: actorId, actor_name: text },
  }
}

/** Deliver frames the way the socket would. */
async function deliver(...frames: Record<string, unknown>[]) {
  await act(async () => {
    socket.listeners.forEach((listener) => frames.forEach((f) => listener(f)))
  })
}

function renderToasts() {
  return render(
    <SessionContext.Provider value={session}>
      <ToastStack />
    </SessionContext.Provider>,
  )
}

beforeEach(() => {
  socket.listeners = []
})

// ─── B4: the dedupe ─────────────────────────────────────────────────────────

test('a repeat from the same actor does not evict an unrelated toast', async () => {
  renderToasts()

  // One from Alice, one from Carol, then a second from Alice inside the window.
  await deliver(frame('n1', 'Alice wants to connect', 'alice'))
  await expect(screen.getByText('Alice wants to connect')).toBeInTheDocument()

  await deliver(frame('n2', 'Carol wants to connect', 'carol'))
  await expect(screen.getByText('Carol wants to connect')).toBeInTheDocument()

  await deliver(
    frame('n3', 'Alice is interested in your idea "Ledger"', 'alice'),
  )

  // Both must still be on screen. The current handler removes the oldest toast
  // — Alice's — and drops the new one, so the first assertion below fails.
  await waitFor(() => {
    expect(screen.getByText('Alice wants to connect')).toBeInTheDocument()
  })
  expect(
    screen.getByText('Carol wants to connect'),
    "a repeat from Alice evicted Carol's toast",
  ).toBeInTheDocument()
})

test('a repeat from the same actor is not shown twice', async () => {
  renderToasts()

  await deliver(frame('n1', 'Alice wants to connect', 'alice'))
  await deliver(frame('n2', 'Carol wants to connect', 'carol'))
  await deliver(frame('n3', 'Alice is interested in your idea "Ledger"', 'alice'))

  // Suppressed, not duplicated.
  expect(screen.queryAllByText('Alice is interested in your idea "Ledger"')).toHaveLength(0)
  expect(screen.getAllByText('Alice wants to connect')).toHaveLength(1)
  expect(screen.getAllByText('Carol wants to connect')).toHaveLength(1)
})

test('a burst from one actor leaves exactly one toast', async () => {
  renderToasts()

  await deliver(
    frame('n1', 'Alice wants to connect', 'alice'),
    frame('n2', 'Alice is interested in your idea "One"', 'alice'),
    frame('n3', 'Alice is interested in your idea "Two"', 'alice'),
  )

  const rendered = screen.getAllByRole('status')
  expect(rendered).toHaveLength(1)
  expect(screen.getByText('Alice wants to connect')).toBeInTheDocument()
})

test('toasts from different actors all appear', async () => {
  renderToasts()

  await deliver(
    frame('n1', 'Alice wants to connect', 'alice'),
    frame('n2', 'Carol wants to connect', 'carol'),
    frame('n3', 'Dan accepted your request', 'dan'),
  )

  expect(screen.getAllByRole('status')).toHaveLength(3)
})

test('your own activity never toasts you', async () => {
  renderToasts()

  await deliver(frame('n1', 'You accepted your own request', ME))
  await deliver(frame('n2', 'Alice wants to connect', 'alice'))

  expect(screen.queryByText('You accepted your own request')).not.toBeInTheDocument()
  expect(screen.getByText('Alice wants to connect')).toBeInTheDocument()
})

// ─── The bell ───────────────────────────────────────────────────────────────

test('the bell reflects the unread count and nothing else is needed for it to work', async () => {
  const { notifications } = await import('../api/client')
  ;(notifications.unreadCount as unknown as Mock).mockResolvedValue({ unread_count: 3 })
  ;(notifications.list as unknown as Mock).mockResolvedValue({
    items: [
      {
        id: 'n1',
        type: 'connection_requested',
        text: 'Alice wants to connect',
        url: '/connections',
        read_at: null,
        created_at: new Date('2026-01-01T00:00:00Z').toISOString(),
        actor_id: 'alice',
        data: {},
      },
    ],
    next_cursor: null,
  })

  render(
    <SessionContext.Provider value={session}>
      <NotificationBell />
    </SessionContext.Provider>,
  )

  // The badge and the accessible name must agree — they come from the same
  // unread_count, which is the promise specs/07 §6 makes.
  const button = screen.getByRole('button', { name: /Notifications, 3 unread/ })
  expect(button).toBeInTheDocument()

  await userClick(button)
  await waitFor(() => expect(screen.getByText('Alice wants to connect')).toBeInTheDocument())
})

// userEvent is only needed for the one click above; imported lazily so the
// dedupe tests do not pay for it.
async function userClick(element: HTMLElement) {
  const { default: userEvent } = await import('@testing-library/user-event')
  await userEvent.click(element)
}