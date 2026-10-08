/**
 * ThreadPage component tests.
 *
 * Added 8 October 2026 with the §12 review, before the fix. The reason these
 * are component tests rather than Playwright: React's hook-order warning is a
 * development-build console message, and the toast dedupe is a five second
 * window. Both are deterministic in jsdom and awkward to provoke through a
 * real browser.
 *
 *   B3  hooks are declared below `if (loading) return <Spinner/>`, so the
 *       first render runs fewer hooks than the second
 *   B16 the client cannot page a conversation's history
 */

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, type Mock, test, vi } from 'vitest'

// jsdom does not implement scrollIntoView, and ThreadPage calls it from a
// layout effect on the very first render.
beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

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
    // Mirrors the real implementation: a ref for the latest listener plus one
    // effect. The hook count has to match, because that is the whole subject.
    useSocketListener: (_event: string, listener: (frame: Record<string, unknown>) => void) => {
      const ref = React.useRef(listener)
      ref.current = listener
      React.useEffect(() => {
        const wrapped = (frame: Record<string, unknown>) => ref.current(frame)
        socket.listeners.push(wrapped)
        return () => {
          socket.listeners = socket.listeners.filter((entry) => entry !== wrapped)
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [])
    },
    useThreadSubscription: () => {},
  }
})

vi.mock('../api/client', () => {
  class ApiError extends Error {
    status: number
    code: string
    fields?: Record<string, string>
    constructor(status: number, code: string, message: string) {
      super(message)
      this.status = status
      this.code = code
    }
  }
  return {
    ApiError,
    messages: {
      thread: vi.fn(),
      history: vi.fn(),
      send: vi.fn(),
    },
  }
})

import { messages } from '../api/client'
import { SessionContext, type SessionValue } from '../hooks/session'
import { ThreadPage } from './MessagingPage'

const THREAD_ID = 'aaaaaaaa-1111-2222-3333-444444444444'
const ME = '99999999-8888-7777-6666-555555555555'
const THEM = '00000000-1111-2222-3333-444444444444'

const session = {
  user: {
    id: ME,
    email: 'me@example.com',
    display_name: 'Me',
    first_name: 'Me',
    is_admin: false,
    is_active: true,
    csrf_token: 'token',
    profile: {
      bio: null,
      role: 'software_developer',
      course: null,
      looking_for: null,
      skills: [],
      interests: [],
      profile_complete: true,
      has_photo: false,
      photo_url: null,
    },
  },
  loading: false,
} as unknown as SessionValue

function message(body: string, id: string, sender = THEM) {
  return {
    id,
    thread_id: THREAD_ID,
    sender_id: sender,
    body,
    created_at: new Date('2026-01-01T00:00:00Z').toISOString(),
  }
}

function renderThread() {
  return render(
    <SessionContext.Provider value={session}>
      <MemoryRouter initialEntries={[`/messages/${THREAD_ID}`]}>
        <Routes>
          <Route path="/messages/:threadId" element={<ThreadPage />} />
        </Routes>
      </MemoryRouter>
    </SessionContext.Provider>,
  )
}

/** The mocked client, typed loosely so the fixtures need no casts. */
const mockThread = messages.thread as unknown as Mock
const mockHistory = messages.history as unknown as Mock

beforeEach(() => {
  socket.listeners = []
  mockThread.mockResolvedValue({
    id: THREAD_ID,
    other: { id: THEM, display_name: 'Them', first_name: 'Them', has_photo: false, photo_url: null },
    last_message: null,
    unread_count: 0,
    last_message_at: null,
  })
  mockHistory.mockResolvedValue({
    items: [message('first', 'm1'), message('second', 'm2')],
    next_cursor: null,
  })
})

// ─── B3: hook order ─────────────────────────────────────────────────────────

test('opening a conversation logs no react hook-order error', async () => {
  const problems: string[] = []
  const spy = vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
    problems.push(args.map(String).join(' '))
  })

  try {
    renderThread()
    // Loading flips to false after the first fetch resolves, which is when the
    // component renders past its early return and reaches the hooks that were
    // skipped the first time.
    await waitFor(() => expect(screen.getByLabelText('Message')).toBeInTheDocument())

    const hookProblems = problems.filter((text) =>
      /rendered (more|fewer) hooks|change the order of hooks|hook order/i.test(text),
    )
    expect(
      hookProblems,
      `React reported a hook-order violation:\n${hookProblems.join('\n---\n')}`,
    ).toEqual([])
  } finally {
    spy.mockRestore()
  }
})

test('the socket listener still receives frames once loading finishes', async () => {
  // The functional consequence of the same defect: the listener registered
  // below the early return has to work once the component gets past the spinner.
  renderThread()
  await waitFor(() => expect(screen.getByLabelText('Message')).toBeInTheDocument())

  expect(socket.listeners.length, 'no socket listener was registered').toBeGreaterThan(0)

  await act(async () => {
    socket.listeners.forEach((listener) =>
      listener({
        type: 'message',
        data: message('arrived live', 'm3'),
      }),
    )
  })

  await waitFor(() => expect(screen.getByText('arrived live')).toBeInTheDocument())
})

test('a frame for a different thread is ignored', async () => {
  renderThread()
  await waitFor(() => expect(screen.getByLabelText('Message')).toBeInTheDocument())

  await act(async () => {
    socket.listeners.forEach((listener) =>
      listener({
        type: 'message',
        data: { ...message('not for this thread', 'm4'), thread_id: 'some-other-thread' },
      }),
    )
  })

  expect(screen.queryByText('not for this thread')).not.toBeInTheDocument()
})

// ─── Behaviour that must survive the fix ────────────────────────────────────

test('history and live frames merge without duplicating a message', async () => {
  renderThread()
  await waitFor(() => expect(screen.getByLabelText('Message')).toBeInTheDocument())

  await expect(screen.getByText('first')).toBeInTheDocument()

  // The server re-broadcasts something already in history.
  await act(async () => {
    socket.listeners.forEach((listener) =>
      listener({ type: 'message', data: message('second', 'm2') }),
    )
  })

  expect(screen.getAllByText('second')).toHaveLength(1)
})

test('a failed history fetch shows an inline error, not a dialog', async () => {
  const { ApiError } = await import('../api/client')
  mockHistory.mockRejectedValue(
    new ApiError(500, 'internal_error', 'Something went wrong on our end.'),
  )

  renderThread()
  await waitFor(() =>
    expect(screen.getByText('Something went wrong on our end.')).toBeInTheDocument(),
  )
})

test('a message is rolled back and the draft restored when sending fails', async () => {
  const { ApiError } = await import('../api/client')
  ;(messages.send as unknown as Mock).mockRejectedValue(
    new ApiError(500, 'internal_error', 'nope'),
  )

  renderThread()
  await waitFor(() => expect(screen.getByLabelText('Message')).toBeInTheDocument())

  const composer = screen.getByLabelText('Message')
  await userEvent.type(composer, 'this will not send')
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))

  // The optimistic bubble must not survive a failed send, and the text must
  // not be lost.
  await waitFor(() => expect(screen.getByDisplayValue('this will not send')).toBeInTheDocument())
  expect(screen.queryByText('this will not send')).not.toBeInTheDocument()
})

test('a whitespace-only draft cannot be sent', async () => {
  renderThread()
  await waitFor(() => expect(screen.getByLabelText('Message')).toBeInTheDocument())

  const send = screen.getByRole('button', { name: 'Send' })
  expect(send).toBeDisabled()

  await userEvent.type(screen.getByLabelText('Message'), '    ')
  expect(send).toBeDisabled()

  await userEvent.type(screen.getByLabelText('Message'), 'x')
  expect(send).toBeEnabled()
})
