/** Connections: three tabs from one endpoint. specs/05 §6. */

import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { connections as connApi } from '../api/client'
import { ApiError } from '../api/client'
import type { Connection } from '../api/types'
import { Avatar, Button, EmptyState, ErrorState, Spinner } from '../components/ui'
import { useQuery } from '../hooks/useQuery'

type Tab = 'received' | 'sent' | 'connected'

export function ConnectionsPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) ?? 'received'
  const [reloadKey, bumpReload] = useState(0)
  const summary = useQuery(() => connApi.summary(), [reloadKey])

  const query = useQuery(() => connApi.list(tab), [tab, reloadKey])

  const setTab = (next: Tab) => {
    setParams({ tab: next }, { replace: true })
  }

  const items = (query.data?.items ?? []) as Connection[]
  const counts = summary.data

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Connections</h1>

      <div className="flex gap-2" role="tablist">
        {(['received', 'sent', 'connected'] as Tab[]).map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={`rounded-lg px-4 py-2 text-sm capitalize ${
              tab === name
                ? 'bg-brand-600 text-white'
                : 'border border-slate-300 bg-white text-slate-700'
            }`}
          >
            {name}
            {counts && name === 'received' && counts.received_pending > 0 && (
              <span className="ml-1.5 rounded-full bg-red-600 px-1.5 text-xs text-white">
                {counts.received_pending}
              </span>
            )}
            {counts && name === 'sent' && counts.sent_pending > 0 && (
              <span className="ml-1.5 text-xs opacity-70">{counts.sent_pending}</span>
            )}
          </button>
        ))}
      </div>

      {query.loading && <Spinner />}
      {query.error && <ErrorState message={query.error.message} onRetry={query.refetch} />}

      {!query.loading && !query.error && items.length === 0 && (
        <EmptyState
          title={
            tab === 'received'
              ? 'No requests waiting. Send one from your matches.'
              : tab === 'sent'
                ? "You haven't asked anyone yet."
                : "You haven't connected with anyone yet."
          }
          action={
            <Link to="/matches" className="text-brand-600 underline">
              Browse matches
            </Link>
          }
        />
      )}

      <ul className="space-y-3">
        {items.map((connection) => (
          <li key={connection.id}>
            <ConnectionRow connection={connection} onChange={() => bumpReload((n) => n + 1)} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function ConnectionRow({
  connection,
  onChange,
}: {
  connection: Connection
  onChange: () => void
}) {
  const [busy, setBusy] = useState(false)
  // Inline, never alert(). A dialog blocks the page, and a failure the user
  // cannot see is worse than no button — "Message" silently doing nothing
  // looks exactly like a broken feature.
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4">
      <Link to={`/users/${connection.other.id}`}>
        <Avatar user={connection.other} size={44} />
      </Link>
      <div className="min-w-0 flex-1">
        <Link to={`/users/${connection.other.id}`} className="font-medium text-slate-900">
          {connection.other.display_name}
        </Link>
        {connection.message && (
          <p className="mt-1 text-sm text-slate-600">“{connection.message}”</p>
        )}
        <p className="mt-1 text-xs text-slate-400">
          {connection.status === 'accepted'
            ? 'Connected'
            : connection.status === 'declined'
              ? 'Declined'
              : 'Pending'}
        </p>
        {error && (
          <p role="alert" className="mt-1 text-sm text-red-600">
            {error}
          </p>
        )}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-2">
        {connection.status === 'pending' && connection.responded_at === null && (
          <>
            <Button onClick={() => act(() => connApi.respond(connection.id, 'accept'))} disabled={busy}>
              Accept
            </Button>
            {/* Decline is one click. A confirmation modal here is friction that
                gets clicked through without reading. */}
            <button
              onClick={() => act(() => connApi.respond(connection.id, 'decline'))}
              disabled={busy}
              className="text-sm text-slate-500 underline"
            >
              Decline
            </button>
          </>
        )}

        {connection.status === 'pending' && (
          <button
            onClick={() => act(() => connApi.withdraw(connection.id))}
            disabled={busy}
            className="text-sm text-slate-500 underline"
          >
            Withdraw
          </button>
        )}

        {/* Threads are created lazily on first message, so a freshly accepted
            connection has none yet. Link when one exists, otherwise create it
            on click — and navigate in-app rather than reloading the page. */}
        {connection.status === 'accepted' &&
          (connection.thread_id ? (
            <Link
              to={`/messages/${connection.thread_id}`}
              className="rounded-lg border border-brand-300 px-3 py-1.5 text-sm text-brand-700"
            >
              Message
            </Link>
          ) : (
            <button
              onClick={() =>
                act(async () => {
                  const { id } = await connApi.openThread(connection.id)
                  navigate(`/messages/${id}`)
                })
              }
              disabled={busy}
              className="rounded-lg border border-brand-300 px-3 py-1.5 text-sm text-brand-700"
            >
              Message
            </button>
          ))}
      </div>
    </div>
  )
}