/** Notifications page. specs/07 §6. */

import { Link } from 'react-router-dom'
import { notifications as notifApi } from '../api/client'
import type { AppNotification } from '../api/types'
import { NOTIFICATIONS_CHANGED } from '../components/Notifications'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { useQuery } from '../hooks/useQuery'

function dayGroup(date: string): string {
  const when = new Date(date)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString()
  if (same(when, today)) return 'Today'
  if (same(when, yesterday)) return 'Yesterday'
  return 'Earlier'
}

export function NotificationsPage() {
  const query = useQuery(() => notifApi.list(), [])

  if (query.loading) return <Spinner />
  if (query.error) return <ErrorState message="Couldn't load notifications." onRetry={query.refetch} />

  const items = query.data?.items ?? []
  const groups: Record<string, AppNotification[]> = {}
  for (const item of items) {
    const key = dayGroup(item.created_at)
    ;(groups[key] ??= []).push(item)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Notifications</h1>
        {items.some((i) => !i.read_at) && (
          <button
            onClick={async () => {
              await notifApi.markAllRead()
              // Tell the bell, or its badge keeps counting what is now read.
              window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED))
              query.refetch()
            }}
            className="text-sm text-brand-600 underline"
          >
            Mark all read
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <EmptyState title="You're all caught up." />
      ) : (
        Object.entries(groups).map(([day, rows]) => (
          <section key={day}>
            <h2 className="mb-2 text-sm font-medium text-slate-500">{day}</h2>
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
              {rows.map((n) => (
                <li key={n.id}>
                  <Link
                    to={n.url}
                    onClick={async () => {
                      // Mark read, then navigate, so the destination page's
                      // badge is already correct.
                      if (!n.read_at) {
                        await notifApi.markRead(n.id).catch(() => {})
                        window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED))
                      }
                      query.refetch()
                    }}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50"
                  >
                    {!n.read_at && <span className="h-2 w-2 rounded-full bg-brand-600" />}
                    <span className={n.read_at ? 'text-sm text-slate-500' : 'text-sm font-medium'}>
                      {n.text}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}