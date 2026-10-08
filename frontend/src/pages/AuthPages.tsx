/** Login, register, and magic link. specs/02 §5. */

import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, auth as authApi } from '../api/client'
import { Button, Field, inputClass } from '../components/ui'
import { useSession } from '../hooks/session'

/** Only honour same-origin, single-slash paths. Otherwise `//evil.com` is an
 *  open redirect on the most trusted transition in the app. */
function safeDestination(from: string | null): string {
  if (from && from.startsWith('/') && !from.startsWith('//')) return from
  return '/'
}

export function LoginPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { adopt } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      adopt(await authApi.login({ email, password }))
      navigate(safeDestination(params.get('from')), { replace: true })
    } catch (err) {
      // Same message for an unknown email and a wrong password.
      setError(err instanceof ApiError ? err.message : 'Could not sign in.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Log in">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Email">
          <input
            type="email"
            className={inputClass}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </Field>
        <Field label="Password" error={error ?? undefined}>
          <input
            type="password"
            className={inputClass}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? 'Signing in…' : 'Log in'}
        </Button>
      </form>

      <div className="mt-6 border-t border-slate-200 pt-4">
        <Link to="/forgot-password" className="text-sm text-brand-600 underline">
          Email me a sign-in link instead
        </Link>
      </div>

      <p className="mt-6 text-sm text-slate-600">
        No account?{' '}
        <Link to="/register" className="text-brand-600 underline">
          Sign up
        </Link>
      </p>
    </AuthShell>
  )
}

export function RegisterPage() {
  const navigate = useNavigate()
  const { adopt } = useSession()
  const [form, setForm] = useState({ email: '', password: '', display_name: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setFieldErrors({})
    try {
      adopt(await authApi.register(form))
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        // A duplicate email shows inline on the field: the user is looking at
        // the form, so that is where the answer belongs.
        if (err.fields) setFieldErrors(err.fields)
        else setError(err.message)
      } else {
        setError('Could not create your account.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Three fields. You can add the rest afterwards.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Display name" error={fieldErrors.display_name}>
          <input
            className={inputClass}
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            required
            minLength={2}
            maxLength={80}
          />
        </Field>
        <Field label="Email" error={fieldErrors.email}>
          <input
            type="email"
            className={inputClass}
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            autoComplete="email"
            required
          />
        </Field>
        <Field
          label="Password"
          hint="At least 8 characters."
          error={fieldErrors.password}
        >
          <input
            type="password"
            className={inputClass}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            autoComplete="new-password"
            required
            minLength={8}
          />
        </Field>
        {error && (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? 'Creating…' : 'Sign up'}
        </Button>
      </form>

      <p className="mt-6 text-sm text-slate-600">
        Already have an account?{' '}
        <Link to="/login" className="text-brand-600 underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  )
}

export function MagicLinkPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      // Always 202, whether or not the address exists.
      await authApi.requestMagicLink(email)
      setSent(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Sign-in link" subtitle="We'll email you a link that works once.">
      {sent ? (
        <div className="space-y-4 text-sm text-slate-600">
          <p>If that address has an account, a link is on its way.</p>
          <p className="rounded-lg bg-slate-100 p-3 text-xs">
            Development shortcut: no email is actually sent. The link appears in
            Mailpit at{' '}
            <a href="http://localhost:8025" className="underline" target="_blank" rel="noreferrer">
              localhost:8025
            </a>
            .
          </p>
          <Link to="/login" className="text-brand-600 underline">
            Back to log in
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email">
            <input
              type="email"
              className={inputClass}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? 'Sending…' : 'Send me a link'}
          </Button>
        </form>
      )}
    </AuthShell>
  )
}

function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-full items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
    </div>
  )
}