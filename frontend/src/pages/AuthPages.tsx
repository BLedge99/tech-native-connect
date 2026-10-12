import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { requestMagicLink } from '../api/auth';
import type { ApiError } from '../api/http';
import { useAuth } from '../auth/AuthContext';

function AuthFrame({ children, eyebrow, title, detail }: {
  children: ReactNode;
  eyebrow: string;
  title: string;
  detail: string;
}) {
  return (
    <main className="auth-page">
      <header className="site-mark"><Link to="/" aria-label="Bootcamp Connect home">BC<span>.</span></Link></header>
      <section className="auth-panel" aria-labelledby="auth-title">
        <p className="eyebrow">{eyebrow}</p>
        <h1 id="auth-title">{title}</h1>
        <p className="auth-detail">{detail}</p>
        {children}
      </section>
      <p className="auth-foot">Bootcamp Connect <span>·</span> Find your people, build what’s next.</p>
    </main>
  );
}

function ErrorMessage({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return <p className="form-error" role="alert">{error.error.message}</p>;
}

export function RegisterPage() {
  const { user, loading, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (loading) return <div className="page-loading" role="status">Loading your session…</div>;
  if (user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({ email, password, display_name: displayName });
      const from = (location.state as { from?: { pathname?: string; search?: string; hash?: string } } | null)?.from;
      const destination = from ? `${from.pathname ?? '/'}${from.search ?? ''}${from.hash ?? ''}` : '/';
      navigate(destination.startsWith('/') && !destination.startsWith('//') ? destination : '/', { replace: true });
    } catch (reason) {
      setError(reason as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthFrame eyebrow="Join your cohort" title="Make the first move." detail="Meet the person who can turn your idea into something real.">
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="display-name">Your name</label>
        <input id="display-name" name="display_name" autoComplete="name" minLength={2} maxLength={80} required value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        <label htmlFor="register-email">Email address</label>
        <input id="register-email" name="email" type="email" autoComplete="email" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} aria-describedby={error?.error.fields?.email ? 'email-error' : undefined} />
        {error?.error.fields?.email && <span id="email-error" className="field-error">{error.error.fields.email}</span>}
        <label htmlFor="register-password">Password</label>
        <input id="register-password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
        {error?.error.fields?.password && <span className="field-error">{error.error.fields.password}</span>}
        <ErrorMessage error={error?.error.fields ? null : error} />
        <button className="primary-button" type="submit" disabled={submitting}>{submitting ? 'Creating account…' : 'Create account'} <span aria-hidden="true">↗</span></button>
      </form>
      <p className="switch-auth">Already part of the cohort? <Link to="/login">Sign in</Link></p>
    </AuthFrame>
  );
}

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (loading) return <div className="page-loading" role="status">Loading your session…</div>;
  if (user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email, password });
      const state = (location.state as { from?: { pathname?: string; search?: string; hash?: string } } | null)?.from;
      const stateFrom = state ? `${state.pathname ?? '/'}${state.search ?? ''}${state.hash ?? ''}` : undefined;
      const queryFrom = searchParams.get('from');
      const destination = stateFrom ?? queryFrom ?? '/';
      navigate(destination.startsWith('/') && !destination.startsWith('//') ? destination : '/', { replace: true });
    } catch (reason) {
      setError(reason as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthFrame eyebrow="Welcome back" title="Pick up where you left off." detail="Your next good idea might be one conversation away.">
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="login-email">Email address</label>
        <input id="login-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        <label htmlFor="login-password">Password</label>
        <input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
        <ErrorMessage error={error} />
        <button className="primary-button" type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'} <span aria-hidden="true">↗</span></button>
      </form>
      <p className="switch-auth"><Link to="/forgot-password">Sign in with a magic link</Link></p>
      <p className="switch-auth">New to the cohort? <Link to="/register">Create an account</Link></p>
    </AuthFrame>
  );
}

export function MagicLinkPage() {
  const { user, loading } = useAuth();
  const [email, setEmail] = useState('');
  const [result, setResult] = useState<{ message: string; dev_magic_link?: string } | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (loading) return <div className="page-loading" role="status">Loading your session…</div>;
  if (user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      setResult(await requestMagicLink(email));
    } catch (reason) {
      setError(reason as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthFrame eyebrow="Passwordless sign in" title="A link, then you’re in." detail="We’ll email a one-time sign-in link that expires in 15 minutes.">
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="magic-email">Email address</label>
        <input id="magic-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        <ErrorMessage error={error} />
        <button className="primary-button" type="submit" disabled={submitting}>{submitting ? 'Sending…' : 'Send sign-in link'} <span aria-hidden="true">↗</span></button>
      </form>
      {result && <div className="success-message" role="status"><p>{result.message}</p>{result.dev_magic_link && <p className="dev-link">Development shortcut: <a href={result.dev_magic_link}>open sign-in link</a>. Mailpit inbox is also available on port 8025.</p>}</div>}
      <p className="switch-auth"><Link to="/login">Back to password sign in</Link></p>
    </AuthFrame>
  );
}