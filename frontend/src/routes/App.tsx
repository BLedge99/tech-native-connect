/** Route table and guards. specs/01 §5.
 *
 * Guards live here, never scattered through components.
 */

import { useEffect, useRef, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { api, auth as authApi, setCsrfToken } from '../api/client'
import { Shell, Spinner } from '../components/ui'
import { ToastStack } from '../components/Notifications'
import { WebSocketProvider } from '../hooks/websocket'
import { SessionContext, isUnauthorised, useSession } from '../hooks/session'
import type { Me } from '../api/types'
import { AdminPage } from '../pages/AdminPage'
import { IdeasPage, IdeaDetailPage, IdeaFormPage } from '../pages/IdeasPage'
import { LoginPage, MagicLinkPage, RegisterPage } from '../pages/AuthPages'
import { MatchesPage, PublicProfilePage } from '../pages/MatchesPage'
import { HomeFeed } from '../pages/HomeFeed'
import { LandingPage } from '../pages/LandingPage'
import { MessagesPage, ThreadPage } from '../pages/MessagingPage'
import { NotificationsPage } from '../pages/NotificationsPage'
import { ProfileEditPage, ProfilePage } from '../pages/ProfilePages'
import { ConnectionsPage } from '../pages/ConnectionsPage'
import { DevPanelPage } from '../pages/DevPanelPage'

function useSessionState() {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  // Bumped whenever a session is established, so a slow /users/me response
  // cannot clobber state a faster register/login just wrote.
  const sessionGeneration = useRef(0)

  const refresh = async () => {
    const generation = sessionGeneration.current
    try {
      const me = await api.get<Me>('/api/v1/users/me')
      // A login or registration completed while this request was in flight.
      // Writing now would log the user straight back out.
      if (generation !== sessionGeneration.current) return
      setCsrfToken(me.csrf_token)
      setUser(me)
    } catch (err) {
      if (generation !== sessionGeneration.current) return
      // 401 means logged out. It is not an error worth surfacing.
      if (!isUnauthorised(err)) console.warn('session check failed', err)
      setCsrfToken(null)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  /** Called by register/login so a late /users/me cannot undo them. */
  const adopt = (me: Me) => {
    sessionGeneration.current += 1
    setCsrfToken(me.csrf_token)
    setUser(me)
    return me
  }

  useEffect(() => {
    void refresh()
  }, [])

  const logout = async () => {
    // The server-side revocation must land BEFORE the navigation. A reload that
    // races it restarts the session check while the cookie is still valid and
    // the user lands straight back on a protected route.
    try {
      await authApi.logout()
    } finally {
      setCsrfToken(null)
      setUser(null)
      window.location.replace('/')
    }
  }

  return { user, loading, refresh, setUser, adopt, logout }
}

/** Wait for session resolution before rendering. A brief spinner beats a frame
 *  of private data. specs/01 §5 rule 3. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession()
  const location = useLocation()
  if (loading) return <FullPage />
  if (!user) return <Navigate to={`/login?from=${encodeURIComponent(location.pathname)}`} replace />
  return <>{children}</>
}

/** A signed-in non-admin gets a 403 page, not a login redirect. They are
 *  authenticated, just not permitted. specs/01 §5. */
function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession()
  if (loading) return <FullPage />
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_admin) {
    return (
      <Shell>
        <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
          <h1 className="text-xl font-bold">403 — no access</h1>
          <p className="mt-2 text-sm text-slate-600">
            You are signed in, but this area is for admins.
          </p>
        </div>
      </Shell>
    )
  }
  return <>{children}</>
}

/** Redirect if already signed in, so there is no confusing double state. */
function RedirectIfAuthed({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession()
  if (loading) return <FullPage />
  if (user) return <Navigate to="/" replace />
  return <>{children}</>
}

function FullPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner />
    </div>
  )
}

function NotFound() {
  return (
    <Shell>
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
        <h1 className="text-2xl font-bold">Page not found</h1>
        <a href="/" className="mt-3 inline-block text-brand-600 underline">
          Back home
        </a>
      </div>
    </Shell>
  )
}

function AuthedShell({ children }: { children: React.ReactNode }) {
  return (
    <Shell>
      {children}
    </Shell>
  )
}

export function App() {
  const state = useSessionState()

  return (
    <SessionContext.Provider value={state}>
      <BrowserRouter>
        <WebSocketProvider>
        <Routes>
            <Route
              path="/"
              element={
                <RootGate
                  loading={state.loading}
                  user={state.user}
                  pitch={<LandingPage />}
                  feed={
                    <AuthedShell>
                      <HomeFeed />
                    </AuthedShell>
                  }
                />
              }
            />

            <Route
              path="/register"
              element={
                <RedirectIfAuthed>
                  <RegisterPage />
                </RedirectIfAuthed>
              }
            />
            <Route
              path="/login"
              element={
                <RedirectIfAuthed>
                  <LoginPage />
                </RedirectIfAuthed>
              }
            />
            <Route
              path="/forgot-password"
              element={
                <RedirectIfAuthed>
                  <MagicLinkPage />
                </RedirectIfAuthed>
              }
            />

            <Route
              path="/matches"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <MatchesPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/users/:userId"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <PublicProfilePage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/connections"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <ConnectionsPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/messages"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <MessagesPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/messages/:threadId"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <ThreadPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/notifications"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <NotificationsPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/ideas"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <IdeasPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/ideas/new"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <IdeaFormPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/ideas/:ideaId"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <IdeaDetailPageWrapper />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/ideas/:ideaId/edit"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <IdeaEditWrapper />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/profile"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <ProfilePage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/profile/edit"
              element={
                <RequireAuth>
                  <AuthedShell>
                    <ProfileEditPage />
                  </AuthedShell>
                </RequireAuth>
              }
            />
            <Route
              path="/admin/*"
              element={
                <RequireAdmin>
                  <AuthedShell>
                    <AdminPage />
                  </AuthedShell>
                </RequireAdmin>
              }
            />

            {/* Dev panel — no auth required, development tool only */}
            <Route path="/dev" element={<DevPanelPage />} />

            <Route path="*" element={<NotFound />} />
        </Routes>
          <ToastStack />
        </WebSocketProvider>
      </BrowserRouter>
    </SessionContext.Provider>
  )
}

/** `/` decides between the pitch page and the feed from session state. One URL,
 *  two audiences — specs/01 §1. */
function RootGate({
  loading,
  user,
  pitch,
  feed,
}: {
  loading: boolean
  user: Me | null
  pitch: React.ReactNode
  feed: React.ReactNode
}) {
  if (loading) return <FullPage />
  return <>{user ? feed : pitch}</>
}

function IdeaDetailPageWrapper() {
  const { ideaId } = useParams()
  return <IdeaDetailPage ideaId={ideaId!} />
}

function IdeaEditWrapper() {
  const { ideaId } = useParams()
  return <IdeaFormPage ideaId={ideaId} />
}