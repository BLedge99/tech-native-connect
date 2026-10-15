/** Matches list, filters in the URL, and the profile detail view. specs/04 §8. */

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { connections as connApi, matches as matchesApi, users as usersApi } from '../api/client'
import { ApiError } from '../api/client'
import type { ConnectionState, Match, UserPublic } from '../api/types'
import { ConnectionAction, MatchCard } from '../components/MatchCard'
import { Avatar, ErrorState, RoleBadge, Spinner } from '../components/ui'
import { useQuery } from '../hooks/useQuery'

export function MatchesPage() {
  const [params, setParams] = useSearchParams()
  const [reloadKey, bumpReload] = useState(0)
  const [extra, setExtra] = useState<Match[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  const role = params.get('role') ?? ''
  const skill = params.get('skill') ?? ''
  const course = params.get('course_id') ?? ''
  const interest = params.get('interest') ?? ''

  const filters = {
    limit: 20,
    role: role || undefined,
    skill: skill || undefined,
    course_id: course || undefined,
    interest: interest || undefined,
  }
  const query = useQuery(() => matchesApi.list(filters), [
    role,
    skill,
    course,
    interest,
    reloadKey,
  ])
  const courses = useQuery(() => usersApi.courses(), [])

  // A filter change is a different result set, so page 2 of the old one is
  // meaningless.
  useEffect(() => {
    setExtra([])
    setNextCursor(query.data?.next_cursor ?? null)
  }, [query.data])

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const items = [...((query.data?.items ?? []) as Match[]), ...extra]

  // Without this the cursor is a working API nobody uses: a cohort of more than
  // twenty leaves the rest unreachable.
  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await matchesApi.list({ ...filters, cursor: nextCursor })
      setExtra((current) => [...current, ...page.items])
      setNextCursor(page.next_cursor)
    } catch {
      setMoreError("Couldn't load more matches.")
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">People on your course</h1>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex gap-2" role="group" aria-label="Filter by role">
          {[
            { value: '', label: 'Everyone' },
            { value: 'software_developer', label: 'Developers' },
            { value: 'business_developer', label: 'Business' },
          ].map((option) => (
            <button
              key={option.value}
              onClick={() => setFilter('role', option.value)}
              aria-pressed={role === option.value}
              className={`rounded-lg px-3 py-1.5 text-sm ${
                role === option.value
                  ? 'bg-brand-600 text-white'
                  : 'border border-slate-300 text-slate-700'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <label className="text-sm text-slate-600">
          Skill{' '}
          <input
            defaultValue={skill}
            onBlur={(e) => setFilter('skill', e.target.value)}
            placeholder="e.g. Python"
            className="ml-1 rounded-lg border border-slate-300 px-2 py-1"
          />
        </label>

        <label className="text-sm text-slate-600">
          Interest{' '}
          <input
            defaultValue={interest}
            onBlur={(e) => setFilter('interest', e.target.value)}
            placeholder="e.g. Fintech"
            className="ml-1 rounded-lg border border-slate-300 px-2 py-1"
          />
        </label>

        <label className="text-sm text-slate-600">
          Course{' '}
          <select
            value={course}
            onChange={(e) => setFilter('course_id', e.target.value)}
            className="ml-1 rounded-lg border border-slate-300 px-2 py-1"
          >
            <option value="">All</option>
            {(courses.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {query.loading && <Spinner label="Ranking people" />}
      {query.error && <ErrorState message={query.error.message} onRetry={query.refetch} />}
      {!query.loading && !query.error && items.length === 0 && (
        <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          No one matches these filters. Try widening them.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((match) => (
          <MatchCard
            key={match.user.id}
            match={match}
            onConnect={async (id) => {
              await connApi.send(id)
              bumpReload((n) => n + 1)
            }}
          />
        ))}
      </div>

      {moreError && <p role="alert" className="text-sm text-red-700">{moreError}</p>}
      {nextCursor && (
        <button
          className="text-sm text-brand-700 underline disabled:opacity-50"
          onClick={() => void loadMore()}
          disabled={loadingMore}
        >
          {loadingMore ? 'Loading…' : 'Load more people'}
        </button>
      )}
    </div>
  )
}

export function PublicProfilePage() {
  const { userId } = useParams()
  const navigate = useNavigate()
  const profileQuery = useQuery(
    () => usersApi.publicProfile(userId!),
    [userId],
    { skip: !userId },
  )
  // Connection state comes from /connections, NOT from the match list.
  // Matching EXCLUDES people with a pending request in either direction
  // (spec 04 §5), so once you send a request the person vanishes from
  // /matches and a state derived from it silently falls back to 'none' —
  // offering a Connect button for someone you already asked.
  const [busy, setBusy] = useState(false)
  const [reloadKey, bumpReload] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)

  const connectionsQuery = useQuery(() => connApi.list(), [reloadKey])
  const matchesQuery = useQuery(() => matchesApi.list({ limit: 100 }), [reloadKey])

  if (profileQuery.loading) return <Spinner />
  if (profileQuery.error) return <ErrorState message="That person does not exist." />
  const person = profileQuery.data as UserPublic

  const connection = (connectionsQuery.data?.items ?? []).find(
    (c) => c.other.id === person.id,
  )

  // A connection row knows its status but not its direction, so derive the
  // same shape the match list provides.
  const state: ConnectionState = !connection
    ? 'none'
    : connection.status === 'accepted'
      ? 'connected'
      : connection.status === 'declined'
        ? 'declined'
        : 'pending_outgoing'

  const match = (matchesQuery.data?.items ?? []).find(
    (m) => (m as Match).user.id === person.id,
  ) as Match | undefined

  const respond = async (action: 'accept' | 'decline' | 'withdraw') => {
    setBusy(true)
    try {
      if (action === 'withdraw') await connApi.withdraw(connection!.id)
      else await connApi.respond(connection!.id, action)
      bumpReload((n) => n + 1)
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  const connect = async () => {
    setBusy(true)
    try {
      await connApi.send(person.id)
      bumpReload((n) => n + 1)
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'Could not send the request.')
    } finally {
      setBusy(false)
    }
  }

  /** Connected, but no conversation exists yet. Create it, then go there.
   *  Linking to /messages would land on an empty list with no way forward. */
  const openThread = async () => {
    if (!connection) return
    setBusy(true)
    try {
      const { id } = await connApi.openThread(connection.id)
      navigate(`/messages/${id}`)
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'Could not open the conversation.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Link to="/matches" className="text-sm text-slate-500 underline">
        ← Back to matches
      </Link>

      <div className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="flex items-start gap-4">
          <Avatar
            user={{
              id: person.id,
              display_name: person.display_name,
              has_photo: person.profile.has_photo,
              photo_url: person.profile.photo_url,
            }}
            size={80}
          />
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-slate-900">{person.display_name}</h1>
            <div className="mt-1 flex items-center gap-2 text-sm text-slate-500">
              <RoleBadge role={person.profile.role} />
              {person.profile.course && <span>{person.profile.course.name}</span>}
            </div>
          </div>
          <ConnectionAction
            state={state}
            threadId={connection?.thread_id}
            onConnect={connect}
            onWithdraw={() => void respond('withdraw')}
            onOpenThread={openThread}
          />
        </div>

        {match && match.reasons.length > 0 && (
          <ul className="mt-4 space-y-1 rounded-lg bg-brand-50 p-3 text-sm text-brand-900">
            <li className="font-medium">Why you're seeing {person.first_name}</li>
            {match.reasons.map((reason) => (
              <li key={reason}>• {reason}</li>
            ))}
          </ul>
        )}

        <dl className="mt-6 space-y-4 text-sm">
          <div>
            <dt className="font-medium text-slate-500">Bio</dt>
            <dd className="mt-1">{person.profile.bio || <span className="text-slate-400">Nothing yet</span>}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Looking for</dt>
            <dd className="mt-1">
              {person.profile.looking_for || <span className="text-slate-400">Nothing yet</span>}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Skills</dt>
            <dd className="mt-1 flex flex-wrap gap-2">
              {person.profile.skills.length === 0 && <span className="text-slate-400">None</span>}
              {person.profile.skills.map((s) => (
                <span key={s.id} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs">
                  {s.name}
                </span>
              ))}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Interests</dt>
            <dd className="mt-1 flex flex-wrap gap-2">
              {person.profile.interests.length === 0 && <span className="text-slate-400">None</span>}
              {person.profile.interests.map((i) => (
                <span key={i.id} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs">
                  {i.name}
                </span>
              ))}
            </dd>
          </div>
        </dl>

        {busy && <p className="mt-4 text-sm text-slate-500">Sending…</p>}
        {notice && (
          <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {notice}
          </p>
        )}
      </div>
    </div>
  )
}