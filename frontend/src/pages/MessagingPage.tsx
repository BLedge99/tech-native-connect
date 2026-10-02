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

  if (query.loading) return <Spinner />
  if (query.error) return <ErrorState message="Couldn't load conversations." onRetry={query.refetch} />
  const threads = query.data ?? []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Messages</h1>
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
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
          {threads.map((thread) => (
            <li key={thread.id}>
              <Link to={`/messages/${thread.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50">
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
      )}
    </div>
  )
}

export function ThreadPage() {
  const { threadId } = useParams()
  const { user } = useSession()
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const threadQuery = useQuery(() => msgApi.thread(threadId!), [threadId], { skip: !threadId })
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottom = useRef(true)
  const newestToast = useRef(false)

  const loadHistory = async () => {
    if (!threadId) return
    try {
      const page = await msgApi.history(threadId)
      setMessages([...(page.items ?? [])].reverse())
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
    <div className="flex h-[calc(100vh-9rem)] flex-col rounded-xl border border-slate-200 bg-white">
      <header className="flex items-center gap-3 border-b border-slate-200 px-4 py-3">
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

      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-auto px-4 py-3">
        {messages.length === 0 && (
          <p className="py-8 text-center text-sm text-slate-400">
            No messages yet. Say hello.
          </p>
        )}
        {messages.map((message) => {
          const mine = message.sender_id === user?.id
          return (
            <div key={message.id} className={`mb-2 flex ${mine ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[70%] rounded-2xl px-3 py-2 text-sm ${
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

      <div className="border-t border-slate-200 p-3">
        <div className="flex items-end gap-2">
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
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
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