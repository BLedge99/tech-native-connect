/** Notification bell. Reads unread_count from the same response as the list so
 *  the badge cannot disagree with the page it links to — specs/07 §6. */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { notifications as notifApi } from '../api/client'
import type { AppNotification } from '../api/types'
import { useSession } from '../hooks/session'
import { useSocketListener } from '../hooks/websocket'

/** Fired whenever something marks notifications read.
 *
 * The bell and the notifications page read the same data, and the bell's whole
 * promise is that its badge cannot disagree with the page it links to
 * (specs/07 §6). Without this, "Mark all read" cleared the page and left the
 * badge saying 3 until a full reload.
 */
export const NOTIFICATIONS_CHANGED = 'notifications:changed'

export function NotificationBell() {
  const { user } = useSession()
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [recent, setRecent] = useState<AppNotification[]>([])
  const boxRef = useRef<HTMLDivElement>(null)

  const load = async () => {
    try {
      const [page, badge] = await Promise.all([
        notifApi.list(),
        notifApi.unreadCount(),
      ])
      setCount(badge.unread_count)
      setRecent(page.items.slice(0, 8))
    } catch {
      // The bell is non-essential. Failing to load it must not break the page.
    }
  }

  useEffect(() => {
    if (user) void load()
  }, [user])

  // Live toasts arrive on the user's own socket topic — no subscribe needed.
  useSocketListener('notification', () => void load())

  // Read state changed elsewhere, so the count changed too.
  useEffect(() => {
    const reload = () => void load()
    window.addEventListener(NOTIFICATIONS_CHANGED, reload)
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED, reload)
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  if (!user) return null

  return (
    <div className="relative" ref={boxRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${count ? `, ${count} unread` : ''}`}
        className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {count > 0 && (
              <button
                onClick={async () => {
                  await notifApi.markAllRead()
                  void load()
                }}
                className="text-xs text-brand-600 underline"
              >
                Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-80 overflow-auto">
            {recent.length === 0 && (
              <li className="px-4 py-6 text-center text-sm text-slate-400">You're all caught up.</li>
            )}
            {recent.map((n) => (
              <li key={n.id} className="border-b border-slate-50 last:border-0">
                <Link
                  to={n.url}
                  onClick={async () => {
                    if (!n.read_at) await notifApi.markRead(n.id).catch(() => {})
                    setOpen(false)
                    void load()
                  }}
                  className={`block px-4 py-3 text-sm hover:bg-slate-50 ${
                    n.read_at ? 'text-slate-500' : 'font-medium text-slate-900'
                  }`}
                >
                  {n.text}
                </Link>
              </li>
            ))}
          </ul>
          <Link
            to="/notifications"
            onClick={() => setOpen(false)}
            className="block border-t border-slate-100 px-4 py-2 text-center text-xs text-brand-600"
          >
            See all
          </Link>
        </div>
      )}
    </div>
  )
}

/** Toasts. Debounced by actor within 5s so a fast typist does not produce 20
 *  toasts — specs/07 §3. */
export function ToastStack() {
  const { user } = useSession()
  const [toasts, setToasts] = useState<Array<{ id: string; text: string; actor: string | null }>>([])
  const seen = useRef(new Map<string, number>())

  useSocketListener('notification', (frame) => {
      const data = frame.data as {
        id: string
        text: string
        actor_id: string | null
      }
      if (!user) return
      // Belt and braces: the server already skips self-notifications, but the
      // failure mode here is embarrassing in a live demo.
      if (data.actor_id === user.id) return

      const last = seen.current.get(data.actor_id ?? 'unknown') ?? 0
      const now = Date.now()
      if (now - last < 5000) {
      // A repeat from the same actor is suppressed and nothing else. It must
      // not touch the toasts already on screen: removing one here used to
      // delete an unrelated actor's toast (B4). Refreshing the timestamp
      // keeps a continuous burst suppressed.
      seen.current.set(data.actor_id ?? 'unknown', now)
      return
}
      seen.current.set(data.actor_id ?? 'unknown', now)
      const id = `${data.id}-${now}`
      setToasts((prev) => [...prev, { id, text: data.text, actor: data.actor_id }])
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 5000)
  })

  if (toasts.length === 0) return null
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className="pointer-events-auto rounded-lg bg-slate-900 px-4 py-2 text-sm text-white shadow-lg"
        >
          {toast.text}
        </div>
      ))}
    </div>
  )
}
