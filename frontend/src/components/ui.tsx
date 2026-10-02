/** Shared presentational primitives. No component library — specs/00 §7 rule 7. */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { UserSummary } from '../api/types'
import { useSession } from '../hooks/session'
import { NotificationBell } from './Notifications'

export function Button({
  children,
  variant = 'primary',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
}) {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50'
  const styles = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700',
    secondary: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
    ghost: 'text-slate-600 hover:bg-slate-100',
  }[variant]
  return (
    <button className={`${base} ${styles}`} {...props}>
      {children}
    </button>
  )
}

export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string
  error?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  )
}

export const inputClass =
  'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none'

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" />
      {label}…
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p>{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 font-medium underline">
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
      <p>{title}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

/** Initials fallback. Every user without a photo must still look deliberate. */
export function Avatar({
  user,
  size = 40,
}: {
  user: UserSummary | { id: string; display_name: string; has_photo?: boolean; photo_url?: string | null }
  size?: number
}) {
  const initials = user.display_name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  if (user.has_photo && user.photo_url) {
    return (
      <img
        src={user.photo_url}
        alt=""
        width={size}
        height={size}
        className="shrink-0 rounded-full object-cover"
        style={{ width: size, height: size }}
      />
    )
  }

  // Deterministic colour from the id, so the same person is always the same colour.
  const hue = [...user.id].reduce((acc, ch) => (acc + ch.charCodeAt(0)) % 360, 0)
  return (
    <div
      aria-hidden
      className="flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{ width: size, height: size, backgroundColor: `hsl(${hue} 55% 45%)`, fontSize: size / 2.6 }}
    >
      {initials}
    </div>
  )
}

export function RoleBadge({ role }: { role: string | null }) {
  if (!role) return null
  const label = role === 'software_developer' ? 'Developer' : 'Business developer'
  return (
    <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
      {label}
    </span>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useSession()

  return (
    <div className="min-h-full">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="text-lg font-bold text-brand-700">
            Bootcamp Connect
          </Link>
          {user && (
            <nav aria-label="Main" className="flex items-center gap-4 text-sm">
              <Link to="/matches" className="text-slate-600 hover:text-slate-900">
                Matches
              </Link>
              <Link to="/connections" className="text-slate-600 hover:text-slate-900">
                Connections
              </Link>
              <Link to="/messages" className="text-slate-600 hover:text-slate-900">
                Messages
              </Link>
              <Link to="/ideas" className="text-slate-600 hover:text-slate-900">
                Ideas
              </Link>
              <Link to="/profile" className="text-slate-600 hover:text-slate-900">
                Profile
              </Link>
              {user.is_admin && (
                <Link to="/admin" className="text-slate-600 hover:text-slate-900">
                  Admin
                </Link>
              )}
              <NotificationBell />
              <button onClick={() => void logout()} className="text-slate-600 hover:text-slate-900">
                Log out
              </button>
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  )
}