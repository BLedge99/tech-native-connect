/** Home feed. Four widgets, each owning its own loading/empty/error state —
 *  one failing request must never blank the page. specs/01 §3, §4. */

import { Link } from 'react-router-dom'
import { matches as matchesApi, notifications as notifApi, connections as connApi } from '../api/client'
import type { Match, AppNotification, ConnectionSummary } from '../api/types'
import { MatchCard } from '../components/MatchCard'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { useQuery } from '../hooks/useQuery'
import { useSession } from '../hooks/session'

export function HomeFeed() {
  const { user } = useSession()
  if (!user) return null

  // profile_complete false means suggestions are not even requested — the
  // backend would answer 403, and showing that error on a page that should be
  // showing a prompt is exactly the bug this avoids.
  if (!user.profile.profile_complete) {
    return <ProfileIncompletePrompt />
  }

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-slate-900">Hi {user.first_name}</h1>
      <SuggestedMatchesWidget />
      <RecentActivityWidget />
    </div>
  )
}

/** Names exactly what is missing. "Profile incomplete" tells the user nothing. */
function ProfileIncompletePrompt() {
  const { user } = useSession()
  const missing: string[] = []
  if (!user?.profile.role) missing.push('a role')
  if ((user?.profile.skills.length ?? 0) === 0) missing.push('at least one skill')

  return (
    <div className="rounded-2xl border border-brand-200 bg-brand-50 p-8 text-center">
      <h1 className="text-2xl font-bold text-slate-900">
        Hi {user?.first_name}. One more step.
      </h1>
      <p className="mx-auto mt-2 max-w-md text-slate-600">
        Add {missing.join(' and ')} to see who you should be talking to on your course.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <Link
          to="/profile/edit"
          className="rounded-lg bg-brand-600 px-5 py-2.5 font-medium text-white hover:bg-brand-700"
        >
          Complete your profile
        </Link>
        {!user?.profile.role && (
          <Link
            to="/profile/edit?focus=role"
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-slate-700"
          >
            Choose a role
          </Link>
        )}
        {user?.profile.role && (user?.profile.skills.length ?? 0) === 0 && (
          <Link
            to="/profile/edit?focus=skills"
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-slate-700"
          >
            Add skills
          </Link>
        )}
      </div>
    </div>
  )
}

function SuggestedMatchesWidget() {
  const query = useQuery(() => matchesApi.list({ limit: 6 }), [])
  const summary = useQuery(() => connApi.summary(), [])
  const summaryData = summary.data as ConnectionSummary | null

  if (query.loading) return <Spinner label="Finding people" />
  if (query.error) {
    // Widget failure is not page failure — specs/01 §3.
    return (
      <section>
        <h2 className="mb-3 text-lg font-semibold">Suggested for you</h2>
        <ErrorState message="Couldn't load suggestions." onRetry={query.refetch} />
      </section>
    )
  }

  const items = (query.data?.items ?? []) as Match[]
  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Suggested for you</h2>
        <Link to="/matches" className="text-sm text-brand-600 underline">
          See all
        </Link>
      </div>
      {items.length === 0 ? (
        <EmptyState title="Nobody new to suggest yet. Check back once more people join." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map((m) => (
            <MatchCard key={m.user.id} match={m} />
          ))}
        </div>
      )}
      {summaryData && summaryData.received_pending > 0 && (
        <p className="mt-4 text-sm text-slate-600">
          You have {summaryData.received_pending} pending request
          {summaryData.received_pending === 1 ? '' : 's'}.{' '}
          <Link to="/connections?tab=received" className="text-brand-600 underline">
            Review them
          </Link>
        </p>
      )}
    </section>
  )
}

function RecentActivityWidget() {
  const query = useQuery(() => notifApi.list(), [])

  if (query.loading) return <Spinner label="Loading activity" />
  if (query.error) {
    return (
      <section>
        <h2 className="mb-3 text-lg font-semibold">Recent activity</h2>
        <ErrorState message="Couldn't load activity." onRetry={query.refetch} />
      </section>
    )
  }

  const items = (query.data?.items ?? []).slice(0, 5) as AppNotification[]
  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Recent activity</h2>
        <Link to="/notifications" className="text-sm text-brand-600 underline">
          See all
        </Link>
      </div>
      {items.length === 0 ? (
        <EmptyState title="Nothing yet. Connect with someone and this fills up." />
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
          {items.map((n) => (
            <li key={n.id}>
              <Link to={n.url} className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50">
                {!n.read_at && <span className="h-2 w-2 rounded-full bg-brand-600" />}
                <span className={n.read_at ? 'text-sm text-slate-500' : 'text-sm font-medium'}>
                  {n.text}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}