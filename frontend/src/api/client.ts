/** The ONLY place fetch is called. specs/00_conventions.md §7 rule 1.
 *
 * Two rules live here so callers cannot forget them:
 *  - credentials: 'include' on every request (the session cookie must travel)
 *  - X-CSRF-Token on every mutating request
 */

import type {
  AdminOverview,
  AdminUser,
  AppNotification,
  AuditRow,
  Connection,
  ConnectionSummary,
  Course,
  Idea,
  IdeaCategory,
  Match,
  Me,
  Message,
  Page,
  Ref,
  Thread,
} from './types'

export class ApiError extends Error {
  code: string
  status: number
  fields?: Record<string, string>

  constructor(status: number, code: string, message: string, fields?: Record<string, string>) {
    super(message)
    this.status = status
    this.code = code
    this.fields = fields
  }
}

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

let csrfToken: string | null = null

/** Set once from GET /users/me. Kept in memory, not localStorage: the session
 *  cookie is httpOnly, so a token in storage would be a downgrade. */
export function setCsrfToken(token: string | null) {
  csrfToken = token
}

export function getCsrfToken() {
  return csrfToken
}

/** Register and login both return the user WITH a CSRF token — a session is
 *  created as part of the request, before /users/me has ever been called. Set
 *  it from the response, or every subsequent mutation fails with
 *  "Not signed in yet." */
function adoptSession(user: Me): Me {
  setCsrfToken(user.csrf_token)
  return user
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  // Only attach CSRF when there is a session to protect. Register and login
  // CREATE the session, so they have no token yet and the server does not
  // require one — throwing here would block sign-up entirely.
  if (MUTATING.has(method) && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken
  }

  const res = await fetch(path, {
    method,
    headers,
    credentials: 'include',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (res.status === 204) return undefined as T

  const text = await res.text()
  const data = text ? JSON.parse(text) : null

  if (!res.ok) {
    const err = data?.error ?? {}
    throw new ApiError(
      res.status,
      err.code ?? 'error',
      err.message ?? 'Something went wrong.',
      err.fields,
    )
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),

  /** Multipart upload. Cannot go through request() because it sets a JSON
   *  Content-Type, and the boundary must be chosen by the browser. */
  async upload(path: string, file: File): Promise<void> {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(path, {
      method: 'POST',
      headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
      credentials: 'include',
      body: form,
    })
    if (!res.ok) {
      const data = await res.json().catch(() => null)
      const err = data?.error ?? {}
      throw new ApiError(
        res.status,
        err.code ?? 'error',
        err.message ?? 'Upload failed.',
        err.fields,
      )
    }
  },
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export const auth = {
  async register(body: { email: string; password: string; display_name: string }) {
    return adoptSession(await api.post<Me>('/api/v1/auth/register', body))
  },
  async login(body: { email: string; password: string }) {
    return adoptSession(await api.post<Me>('/api/v1/auth/login', body))
  },
  async logout() {
    await api.post<void>('/api/v1/auth/logout')
    setCsrfToken(null)
  },
  requestMagicLink: (email: string) =>
    api.post<{ message: string }>('/api/v1/auth/magic-link', { email }),
}

// ─── Users ───────────────────────────────────────────────────────────────────

export const users = {
  me: () => api.get<Me>('/api/v1/users/me'),
  updateMe: (body: {
    bio?: string | null
    role?: string | null
    course_id?: string | null
    looking_for?: string | null
    skill_ids?: string[]
    interest_ids?: string[]
  }) => api.patch<Me>('/api/v1/users/me', body),
  uploadPhoto: (file: File) => api.upload('/api/v1/users/me/photo', file),
  deletePhoto: () => api.del<void>('/api/v1/users/me/photo'),
  publicProfile: (id: string) => api.get<import('./types').UserPublic>(`/api/v1/users/${id}`),
  courses: () => api.get<Course[]>('/api/v1/courses'),
  skills: (q?: string) =>
    api.get<Ref[]>(`/api/v1/skills${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  interests: (q?: string) =>
    api.get<Ref[]>(`/api/v1/interests${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  photoUrl: (id: string) => `/api/v1/users/${id}/photo`,
}

// ─── Matching ────────────────────────────────────────────────────────────────

export const matches = {
  list: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    }
    return api.get<Page<Match>>(`/api/v1/matches${qs.toString() ? `?${qs}` : ''}`)
  },
}

// ─── Connections ─────────────────────────────────────────────────────────────

export const connections = {
  list: (filter?: 'received' | 'sent' | 'connected') =>
    api.get<Page<Connection>>(
      `/api/v1/connections${filter ? `?filter=${filter}` : ''}`,
    ),
  summary: () => api.get<ConnectionSummary>('/api/v1/connections/summary'),
  send: (receiver_id: string, message?: string) =>
    api.post<Connection>('/api/v1/connections', { receiver_id, message }),
  respond: (id: string, action: 'accept' | 'decline') =>
    api.patch<Connection>(`/api/v1/connections/${id}`, { action }),
  withdraw: (id: string) => api.del<void>(`/api/v1/connections/${id}`),
  openThread: (connectionId: string) =>
    api.post<{ id: string }>(`/api/v1/connections/${connectionId}/thread`),
}

// ─── Messaging ───────────────────────────────────────────────────────────────

export const messages = {
  threads: () => api.get<Thread[]>('/api/v1/threads'),
  thread: (id: string) => api.get<Thread>(`/api/v1/threads/${id}`),
  history: (id: string) => api.get<Page<Message>>(`/api/v1/threads/${id}/messages`),
  send: (id: string, body: string) =>
    api.post<Message>(`/api/v1/threads/${id}/messages`, { body }),
  markRead: (id: string) => api.post<void>(`/api/v1/threads/${id}/read`),
  unreadCount: (id: string) =>
    api.get<{ unread_count: number }>(`/api/v1/threads/${id}/messages/unread-count`),
}

// ─── Notifications ───────────────────────────────────────────────────────────

export const notifications = {
  list: (unreadOnly = false) =>
    api.get<Page<AppNotification>>(
      `/api/v1/notifications${unreadOnly ? '?unread_only=true' : ''}`,
    ),
  unreadCount: () => api.get<{ unread_count: number }>('/api/v1/notifications/unread-count'),
  markRead: (id: string) =>
    api.patch<AppNotification>(`/api/v1/notifications/${id}`, { read: true }),
  markAllRead: () => api.patch<void>('/api/v1/notifications/read-all'),
}

// ─── Project ideas ───────────────────────────────────────────────────────────

export const ideas = {
  list: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '' && v !== false) qs.set(k, String(v))
    }
    return api.get<Page<Idea>>(`/api/v1/ideas${qs.toString() ? `?${qs}` : ''}`)
  },
  create: (body: {
    title: string
    description: string
    category: IdeaCategory
    skills_needed?: string[]
    course_id?: string | null
  }) => api.post<Idea>('/api/v1/ideas', body),
  update: (id: string, body: Record<string, unknown>) =>
    api.patch<Idea>(`/api/v1/ideas/${id}`, body),
  remove: (id: string) => api.del<void>(`/api/v1/ideas/${id}`),
  expressInterest: (id: string) => api.post<void>(`/api/v1/ideas/${id}/interest`),
  withdrawInterest: (id: string) => api.del<void>(`/api/v1/ideas/${id}/interest`),
}

// ─── Admin ───────────────────────────────────────────────────────────────────

export const admin = {
  overview: () => api.get<AdminOverview>('/api/v1/admin/overview'),
  users: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    }
    return api.get<Page<AdminUser>>(`/api/v1/admin/users${qs.toString() ? `?${qs}` : ''}`)
  },
  user: (id: string) => api.get<AdminUser>(`/api/v1/admin/users/${id}`),
  deactivate: (id: string) => api.post<void>(`/api/v1/admin/users/${id}/deactivate`),
  reactivate: (id: string) => api.post<void>(`/api/v1/admin/users/${id}/reactivate`),
  grantAdmin: (id: string) => api.post<void>(`/api/v1/admin/users/${id}/grant-admin`),
  revokeAdmin: (id: string) => api.del<void>(`/api/v1/admin/users/${id}/admin`),
  skills: () => api.get<Ref[]>('/api/v1/admin/skills'),
  createSkill: (name: string, category?: string) =>
    api.post<Ref>('/api/v1/admin/skills', { name, category }),
  renameSkill: (id: string, name: string) =>
    api.patch<Ref>(`/api/v1/admin/skills/${id}`, { name }),
  deleteSkill: (id: string) => api.del<void>(`/api/v1/admin/skills/${id}`),
  courses: () => api.get<Course[]>('/api/v1/admin/courses'),
  createCourse: (name: string) => api.post<Course>('/api/v1/admin/courses', { name }),
  interests: () => api.get<Ref[]>('/api/v1/admin/interests'),
  createInterest: (name: string) => api.post<Ref>('/api/v1/admin/interests', { name }),
  audit: () => api.get<Page<AuditRow>>('/api/v1/admin/audit'),
}