/** Admin panel. specs/09 §4.
 *
 * Admin manages the substrate — courses, skills, interests, users — not other
 * people's content. There are deliberately no controls to edit a profile or an
 * idea here. */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { admin as adminApi } from '../api/client'
import { ApiError } from '../api/client'
import type { AdminOverview, AdminUser, AuditRow, Page, Ref } from '../api/types'
import { Button, ErrorState, Spinner } from '../components/ui'
import { useQuery } from '../hooks/useQuery'

type Tab = 'overview' | 'users' | 'reference' | 'audit'

export function AdminPage() {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Admin</h1>
      <div className="flex gap-2" role="tablist">
        {(['overview', 'users', 'reference', 'audit'] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-4 py-2 text-sm capitalize ${
              tab === t ? 'bg-brand-600 text-white' : 'border border-slate-300 bg-white'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'users' && <UsersTab />}
      {tab === 'reference' && <ReferenceTab />}
      {tab === 'audit' && <AuditTab />}
    </div>
  )
}

/** Four counts, no charts. specs/09 §4. */
function OverviewTab() {
  const query = useQuery(() => adminApi.overview(), [])
  if (query.loading) return <Spinner />
  if (query.error) return <ErrorState message={query.error.message} onRetry={query.refetch} />
  const data = query.data as AdminOverview

  const cards = [
    { label: 'Total users', value: data.total_users },
    { label: 'Active', value: data.active_users },
    { label: 'New this week', value: data.new_this_week },
    { label: 'Connections made', value: data.connections_made },
    { label: 'Project ideas', value: data.project_ideas },
  ]

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {cards.map((card) => (
        <div key={card.label} className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-3xl font-bold text-slate-900">{card.value}</p>
          <p className="mt-1 text-sm text-slate-500">{card.label}</p>
        </div>
      ))}
    </div>
  )
}

function UsersTab() {
  const [search, setSearch] = useState('')
  const [reloadKey, bumpReload] = useState(0)
  const [extraUsers, setExtraUsers] = useState<AdminUser[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  const query = useQuery(() => adminApi.users({ q: search || undefined, limit: 100 }), [search, reloadKey])
  useEffect(() => {
    setExtraUsers([])
    setNextCursor(query.data?.next_cursor ?? null)
  }, [query.data])

  if (query.loading) return <Spinner />
  if (query.error) return <ErrorState message={query.error.message} onRetry={query.refetch} />
  const users = [...(query.data?.items ?? []), ...extraUsers]

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await adminApi.users({ q: search || undefined, limit: 100, cursor: nextCursor })
      setExtraUsers((current) => [...current, ...page.items])
      setNextCursor(page.next_cursor)
    } catch {
      setMoreError("Couldn't load more users.")
    } finally {
      setLoadingMore(false)
    }
  }

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      bumpReload((n) => n + 1)
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'That did not work.')
    }
  }

  return (
    <div className="space-y-4">
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by email or name…"
        aria-label="Search users"
        className="w-full max-w-sm rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th className="p-2">Name</th>
            <th className="p-2">Email</th>
            <th className="p-2">Role</th>
            <th className="p-2">Status</th>
            <th className="p-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u: AdminUser) => (
            <tr key={u.id} className="border-b border-slate-100">
              <td className="p-2">
                <Link to={`/users/${u.id}`} className="font-medium hover:underline">
                  {u.display_name}
                </Link>
                {u.is_admin && (
                  <span className="ml-1.5 rounded bg-brand-100 px-1.5 text-xs text-brand-700">admin</span>
                )}
              </td>
              <td className="p-2 text-slate-600">{u.email}</td>
              <td className="p-2 text-slate-600">{u.role ?? '—'}</td>
              <td className="p-2">
                <span className={u.is_active ? 'text-green-700' : 'text-slate-400'}>
                  {u.is_active ? 'active' : 'deactivated'}
                </span>
              </td>
              <td className="p-2">
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() =>
                      act(() =>
                        u.is_active ? adminApi.deactivate(u.id) : adminApi.reactivate(u.id),
                      )
                    }
                    className="text-xs underline"
                  >
                    {u.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                  <button
                    onClick={() =>
                      act(() => (u.is_admin ? adminApi.revokeAdmin(u.id) : adminApi.grantAdmin(u.id)))
                    }
                    className="text-xs underline"
                  >
                    {u.is_admin ? 'Revoke admin' : 'Make admin'}
                  </button>
                  <button
                    onClick={() => act(() => adminApi.user(u.id))}
                    className="text-xs underline"
                  >
                    View
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {moreError && <p role="alert" className="text-sm text-red-700">{moreError}</p>}
      {nextCursor && <button className="text-sm text-brand-700 underline" onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load more users'}</button>}
    </div>
  )
}

function ReferenceTab() {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <RefList title="Courses" load={adminApi.courses} create={adminApi.createCourse} rename={null} />
      <RefList title="Skills" load={adminApi.skills} create={(n) => adminApi.createSkill(n)} rename={adminApi.renameSkill} />
      <RefList title="Interests" load={adminApi.interests} create={adminApi.createInterest} rename={null} />
    </div>
  )
}

function RefList({
  title,
  load,
  create,
  rename,
}: {
  title: string
  load: (cursor?: string) => Promise<Page<Ref>>
  create: (name: string) => Promise<Ref>
  rename: ((id: string, name: string) => Promise<Ref>) | null
}) {
  const [reloadKey, bumpReload] = useState(0)
  const query = useQuery(() => load(), [reloadKey])
  const [draft, setDraft] = useState('')
  const [extraItems, setExtraItems] = useState<Ref[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  useEffect(() => {
    setExtraItems([])
    setNextCursor(query.data?.next_cursor ?? null)
  }, [query.data])

  const add = async () => {
    if (!draft.trim()) return
    try {
      await create(draft.trim())
      setDraft('')
      bumpReload((n) => n + 1)
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Could not add.')
    }
  }

  const items = [...(query.data?.items ?? []), ...extraItems]

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await load(nextCursor)
      setExtraItems((current) => [...current, ...page.items])
      setNextCursor(page.next_cursor)
    } catch {
      setMoreError(`Couldn't load more ${title.toLowerCase()}.`)
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="font-semibold text-slate-900">{title}</h2>
      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="Add…"
          aria-label={`Add ${title}`}
          className="flex-1 rounded-lg border border-slate-300 px-2 py-1 text-sm"
        />
        <Button onClick={add}>Add</Button>
      </div>
      <ul className="mt-3 max-h-72 space-y-1 overflow-auto text-sm">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-2">
            {rename ? (
              <input
                defaultValue={item.name}
                onBlur={async (e) => {
                  if (e.target.value !== item.name) {
                    await rename(item.id, e.target.value)
                    bumpReload((n) => n + 1)
                  }
                }}
                className="flex-1 rounded border border-transparent px-1 py-0.5 hover:border-slate-300"
              />
            ) : (
              <span className="flex-1">{item.name}</span>
            )}
            {rename && (
              <button
                onClick={async () => {
                  try {
                    await adminApi.deleteSkill(item.id)
                    bumpReload((n) => n + 1)
                  } catch (err) {
                    alert(err instanceof ApiError ? err.message : 'Could not delete.')
                  }
                }}
                className="text-xs text-red-600 underline"
              >
                Delete
              </button>
            )}
          </li>
        ))}
      </ul>
      {moreError && <p role="alert" className="mt-2 text-sm text-red-700">{moreError}</p>}
      {nextCursor && <button className="mt-2 text-xs text-brand-700 underline" onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading…' : `Load more ${title.toLowerCase()}`}</button>}
    </div>
  )
}

function AuditTab() {
  const [extraRows, setExtraRows] = useState<AuditRow[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  const query = useQuery(() => adminApi.audit(), [])
  useEffect(() => setNextCursor(query.data?.next_cursor ?? null), [query.data])
  if (query.loading) return <Spinner />
  if (query.error) return <ErrorState message={query.error.message} onRetry={query.refetch} />
  const rows = [...(query.data?.items ?? []), ...extraRows]

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await adminApi.audit(nextCursor)
      setExtraRows((current) => [...current, ...page.items])
      setNextCursor(page.next_cursor)
    } catch {
      setMoreError("Couldn't load more audit entries.")
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div>
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-slate-500">
          <th className="p-2">When</th>
          <th className="p-2">Action</th>
          <th className="p-2">Target</th>
          <th className="p-2">Detail</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row: AuditRow) => (
          <tr key={row.id} className="border-b border-slate-100">
            <td className="p-2 text-slate-500">
              {new Date(row.created_at).toLocaleString()}
            </td>
            <td className="p-2">{row.action}</td>
            <td className="p-2 text-slate-600">{row.target_type ?? '—'}</td>
            <td className="p-2 text-xs text-slate-500">
              {JSON.stringify(row.metadata)}
            </td>
          </tr>
        ))}
      </tbody>
      </table>
      {moreError && <p role="alert" className="text-sm text-red-700">{moreError}</p>}
      {nextCursor && <button className="mt-3 text-sm text-brand-700 underline" onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load more audit entries'}</button>}
    </div>
  )
}
