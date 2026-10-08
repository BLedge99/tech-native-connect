/** Messaging. The demo centrepiece. specs/06 §5. */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { messages as msgApi } from '../api/client'
import { ApiError } from '../api/client'
import type { Message, Thread } from '../api/types'
import { Avatar, EmptyState, ErrorState, Spinner } from '../components/ui'
import { useQuery } from '../hooks/useQuery'
import { useSession } from '../hooks/session'
import { useSocket, useSocketListener, useThreadSubscription } from '../hooks/websocket'

const MAX_CHARS = 2000

export function MessagesPage() {
  const query = useQuery(() => msgApi.threads(), [])
  const [extraThreads, setExtraThreads] = useState<Thread[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  useEffect(() => {
    setExtraThreads([])
    setNextCursor(query.data?.next_cursor ?? null)
  }, [query.data])

  if (query.loading) return <Spinner />
  if (query.error) return <ErrorState message="Couldn't load conversations." onRetry={query.refetch} />
  const threads = [...(query.data?.items ?? []), ...extraThreads]

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await msgApi.threads(nextCursor)
      setExtraThreads((current) => [...current, ...page.items])
      setNextCursor(page.next_cursor)
    } catch {
      setMoreError("Couldn't load more conversations.")
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div className="messaging-page space-y-6">
      <div>
        <p className="text-xs font-bold tracking-[.16em] text-brand-700">YOUR CONVERSATIONS</p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900">Messages</h1>
      </div>
      {threads.length === 0 ? (
        <EmptyState
          title="No conversations yet. Send a connection request to start one."
          action={
            <Link to="/matches" className="text-brand-600 underline">
              Find people to connect with
            </Link>
          }
        />
      ) : (
        <>
        <ul className="conversation-list overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {threads.map((thread) => (
            <li key={thread.id}>
              <Link to={`/messages/${thread.id}`} className="conversation-row flex items-center gap-3 px-4 py-4">
                <Avatar user={thread.other} size={44} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium text-slate-900">{thread.other.display_name}</span>
                    {thread.last_message_at && (
                      <span className="text-xs text-slate-400">
                        {new Date(thread.last_message_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <p className={`truncate text-sm ${thread.unread_count > 0 ? 'font-medium text-slate-900' : 'text-slate-500'}`}>
                    {thread.last_message?.body ?? 'Say hello'}
                  </p>
                </div>
                {thread.unread_count > 0 && (
                  <span className="rounded-full bg-brand-600 px-2 py-0.5 text-xs font-bold text-white">
                    {thread.unread_count}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
        {moreError && <p role="alert" className="text-sm text-red-700">{moreError}</p>}
        {nextCursor && <button className="text-sm text-brand-700 underline" onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load more conversations'}</button>}
        </>
      )}
    </div>
  )
}

export function ThreadPage() {
  const { threadId } = useParams()
  const { user } = useSession()
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [showEmojiPicker, setShowEmojiPicker] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const threadQuery = useQuery(() => msgApi.thread(threadId!), [threadId], { skip: !threadId })
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottom = useRef(true)
  const newestToast = useRef(false)

  // Merge, never replace.
  //
  // A refetch used to overwrite the list wholesale, which lost anything that
  // arrived while it was in flight: send a message while the "socket opened,
  // refetch history" effect is still running and your own message disappears
  // from your screen until the next reload — the POST succeeded, the composer
  // cleared, and there is no bubble. The server never sends the sender a socket
  // frame for its own message, so nothing puts it back.
  //
  // Messages are never deleted in this app, so a union cannot go stale.
  const loadHistory = async () => {
    if (!threadId) return
    try {
      const page = await msgApi.history(threadId)
      setMessages((prev) => {
        const byId = new Map(prev.map((m) => [m.id, m]))
        for (const m of page.items ?? []) {
          const existing = byId.get(m.id)
          // A pending entry is the optimistic copy; the server copy is not an
          // improvement over it.
          byId.set(m.id, existing?.pending ? existing : m)
        }
        return [...byId.values()].sort((a, b) => a.created_at.localeCompare(b.created_at))
      })
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load messages.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadHistory()
  }, [threadId])

  // Subscribe for as long as this view is mounted. The shared socket re-sends
  // the subscription after a reconnect.
  useThreadSubscription(threadId)

  // Live delivery. Reconcile by id — position-based matching merges two
  // identical messages into one.
  useSocketListener('message', (frame) => {
    const data = frame.data as unknown as Message
    if (data.thread_id !== threadId) return
    if (frame.type === 'ack') {
      setMessages((prev) => {
        if (prev.some((m) => m.id === data.id)) return prev
        const matchesPlaceholder = prev.some(
          (m) => m.client_id && m.client_id === data.client_id,
        )
        const replaced = prev.map((m) =>
          m.client_id && m.client_id === data.client_id ? { ...data, pending: false } : m,
        )
        return matchesPlaceholder ? replaced : [...replaced, { ...data, pending: false }]
      })
      return
    }
    setMessages((prev) =>
      prev.some((m) => m.id === data.id) ? prev : [...prev, { ...data, pending: false }],
    )
  })

  // Refetch on reconnect so nothing is missed while the socket was down.
  const { status } = useSocket()
  useEffect(() => {
    if (status === 'open') void loadHistory()
  }, [status])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    if (atBottom.current) newestToast.current = false
  }

  useLayoutEffect(() => {
    // Always scroll to bottom when YOU send; only auto-scroll on incoming when
    // already at the bottom. Yanking the scroll position mid-conversation is the
    // most annoying thing a chat UI can do.
    if (atBottom.current || newestToast.current) {
      bottomRef.current?.scrollIntoView({ block: 'end' })
      newestToast.current = false
    }
  }, [messages])

  const send = async () => {
    const body = draft.trim()
    if (!body || !threadId || !user) return
    const clientId = crypto.randomUUID()
    const optimistic: Message = {
      id: clientId,
      thread_id: threadId,
      sender_id: user.id,
      body,
      created_at: new Date().toISOString(),
      client_id: clientId,
      pending: true,
    }
    setMessages((prev) => [...prev, optimistic])
    setDraft('')

    try {
      const saved = await msgApi.send(threadId, body)
      setMessages((prev) => prev.map((m) => (m.id === clientId ? { ...saved, pending: false } : m)))
    } catch {
      // Roll back and say so. Never silently drop a message.
      setMessages((prev) => prev.filter((m) => m.id !== clientId))
      setDraft(body)
    }
  }

  if (loading) return <Spinner label="Opening conversation" />
  if (error) return <ErrorState message={error} onRetry={() => void loadHistory()} />

  const thread = threadQuery.data as Thread | null

  return (
    <div className="chat-shell flex h-[calc(100vh-10rem)] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-lg shadow-slate-900/5">
      <header className="chat-header flex items-center gap-3 border-b border-slate-200 px-5 py-4">
        {thread && <Avatar user={thread.other} size={36} />}
        <div>
          <Link
            to={`/users/${thread?.other.id}`}
            className="font-medium text-slate-900 hover:underline"
          >
            {thread?.other.display_name ?? 'Conversation'}
          </Link>
        </div>
      </header>

      <div ref={scrollRef} onScroll={onScroll} className="chat-stream flex-1 overflow-auto px-5 py-5">
        {messages.length === 0 && (
          <p className="py-8 text-center text-sm text-slate-400">
            No messages yet. Say hello.
          </p>
        )}
        {messages.map((message) => {
          const mine = message.sender_id === user?.id
          return (
            <div key={message.id} className={`message-line mb-3 flex ${mine ? 'message-line-mine justify-end' : 'justify-start'}`}>
              <div
                className={`message-bubble max-w-[70%] rounded-2xl px-4 py-2.5 text-sm ${
                  mine ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-900'
                } ${message.pending ? 'opacity-60' : ''}`}
              >
                {message.body}
                {!message.pending && (
                  <span className="ml-2 text-[10px] opacity-70">
                    {new Date(message.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                )}
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      <div className="message-composer border-t border-slate-200 p-4">
        {showEmojiPicker && (
          <div className="emoji-picker mb-3 flex flex-wrap gap-1 rounded-xl border border-brand-100 bg-brand-50 p-2" aria-label="Emoji picker">
            {['😀', '👋', '👏', '✨', '🚀', '💡', '🎉', '👍', '❤️', '🙌'].map((emoji) => (
              <button key={emoji} type="button" onClick={() => setDraft((value) => `${value}${emoji}`)} className="emoji-option rounded-lg px-2 py-1 text-lg hover:bg-white" aria-label={`Add ${emoji}`}>{emoji}</button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <button type="button" onClick={() => setShowEmojiPicker((value) => !value)} className="emoji-toggle rounded-lg px-2 py-2 text-lg text-brand-700 hover:bg-brand-50" aria-label="Add emoji">☺</button>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value.slice(0, MAX_CHARS))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            rows={2}
            placeholder="Write a message… Enter to send, Shift+Enter for a new line"
            aria-label="Message"
            className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
          />
          <button
            onClick={() => void send()}
            disabled={!draft.trim()}
            className="rounded-xl bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
        <p className="mt-1 text-right text-xs text-slate-400">
          {draft.length}/{MAX_CHARS}
        </p>
      </div>
    </div>
  )
}
