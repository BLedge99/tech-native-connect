/** MatchCard. Defined once here and reused on /matches, the home feed, and
 *  profiles — specs/01 §6, specs/04 §8.
 *
 * The button state comes entirely from the server's connection_state. Never from
 * local optimism: the state machine is the source of truth. */

import { Link } from 'react-router-dom'
import type { ConnectionState, Match } from '../api/types'
import { Avatar, RoleBadge } from './ui'

interface Props {
  match: Match
  onConnect?: (userId: string) => void
  onWithdraw?: () => void
}

export function MatchCard({ match, onConnect, onWithdraw }: Props) {
  const { user, reasons, shared_skills, connection_state } = match

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start gap-3">
        <Link to={`/users/${user.id}`} className="flex items-center gap-3">
          <Avatar user={{ ...user, has_photo: user.profile.has_photo, photo_url: user.profile.photo_url }} size={48} />
          <div>
            <h3 className="font-semibold text-slate-900">{user.display_name}</h3>
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <RoleBadge role={user.profile.role} />
              {user.profile.course && <span>{user.profile.course.name}</span>}
            </div>
          </div>
        </Link>
        <div className="ml-auto">
          <ConnectionAction
            state={connection_state}
            onConnect={() => onConnect?.(user.id)}
            onWithdraw={onWithdraw}
          />
        </div>
      </div>

      {reasons.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-slate-600">
          {reasons.slice(0, 2).map((reason) => (
            <li key={reason} className="italic">
              “{reason}”
            </li>
          ))}
        </ul>
      )}

      {shared_skills.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">
          Skills: {shared_skills.map((s) => s.name).join(' · ')}
        </p>
      )}
    </article>
  )
}

export function ConnectionAction({
  state,
  onConnect,
  onWithdraw,
  threadId,
  onOpenThread,
}: {
  state: ConnectionState
  onConnect?: () => void
  onWithdraw?: () => void
  /** Present once a conversation exists. */
  threadId?: string | null
  /** Called when connected but no thread exists yet — threads are created
   *  lazily on first message (spec 05 §5), so there is nothing to link to. */
  onOpenThread?: () => void
}) {
  switch (state) {
    case 'none':
      return (
        <button
          onClick={onConnect}
          className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
        >
          Connect
        </button>
      )
    case 'pending_outgoing':
      return (
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Request sent</span>
          <button onClick={onWithdraw} className="text-xs text-slate-500 underline">
            Withdraw
          </button>
        </div>
      )
    case 'pending_incoming':
      return (
        <Link
          to="/connections"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700"
        >
          Wants to connect
        </Link>
      )
    case 'connected':
      if (threadId) {
        return (
          <Link
            to={`/messages/${threadId}`}
            className="rounded-lg border border-brand-300 px-3 py-1.5 text-sm text-brand-700"
          >
            Message
          </Link>
        )
      }
      return (
        <button
          onClick={onOpenThread}
          className="rounded-lg border border-brand-300 px-3 py-1.5 text-sm text-brand-700"
        >
          Message
        </button>
      )
    case 'declined':
      return <span className="text-xs text-slate-400">Not connected</span>
  }
}