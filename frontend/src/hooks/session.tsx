/** Session state. One place that knows about the current user and the CSRF token. */

import { createContext, useContext } from 'react'
import type { Me } from '../api/types'

export interface SessionValue {
  user: Me | null
  loading: boolean
  refresh: () => Promise<void>
  setUser: (user: Me | null) => void
  /** Establish a session from a register/login response. Cancels any
   *  in-flight /users/me check so it cannot log the user back out. */
  adopt: (user: Me) => Me
  logout: () => Promise<void>
}

export const SessionContext = createContext<SessionValue | null>(null)

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used inside SessionProvider')
  return ctx
}

/** A 401 from /users/me means "logged out", not "try again". Retrying it just
 *  delays the redirect on every logged-out page load. */
export function isUnauthorised(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    'status' in err &&
    (err as { status: number }).status === 401
  )
}