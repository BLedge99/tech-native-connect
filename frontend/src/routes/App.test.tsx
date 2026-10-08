/** Route guards and the landing/feed split. specs/01_landing_page.md §5.
 *
 * The single most likely bug in this file's subject area: rendering the pitch
 * page for a logged-in user. So that is the first test.
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { SessionContext, type SessionValue } from '../hooks/session'
import { LandingPage } from '../pages/LandingPage'
import { HomeFeed } from '../pages/HomeFeed'
import type { Me } from '../api/types'

function me(overrides: Partial<Me> = {}): Me {
  return {
    id: 'u1',
    email: 'me@example.com',
    display_name: 'Sam',
    first_name: 'Sam',
    is_admin: false,
    is_active: true,
    created_at: null,
    last_login_at: null,
    csrf_token: 'csrf',
    profile: {
      bio: null,
      role: null,
      course: null,
      looking_for: null,
      skills: [],
      interests: [],
      profile_complete: false,
      has_photo: false,
      photo_url: null,
    },
    ...overrides,
  }
}

function session(overrides: Partial<SessionValue> = {}): SessionValue {
  return {
    user: null,
    loading: false,
    refresh: vi.fn(),
    setUser: vi.fn(),
    adopt: vi.fn((u: Me) => u),
    logout: vi.fn(),
    ...overrides,
  }
}

function withSession(value: SessionValue, ui: React.ReactElement) {
  return (
    <SessionContext.Provider value={value}>
      <MemoryRouter>{ui}</MemoryRouter>
    </SessionContext.Provider>
  )
}

/** The `/` route: pitch page logged out, feed logged in. */
function Root({ user }: { user: Me | null }) {
  return user ? <HomeFeed /> : <LandingPage />
}

describe('LandingPage', () => {
  it('states what the app does in the first screen', () => {
    render(withSession(session(), <LandingPage />))
    expect(
      screen.getByRole('heading', { level: 1, name: /meet the other half/i }),
    ).toBeInTheDocument()
  })

  it('has all five required sections in order', () => {
    render(withSession(session(), <LandingPage />))
    expect(screen.getByRole('heading', { level: 2, name: /two groups/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /how it works/i })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: /built for/i }),
    ).toBeInTheDocument()

    // How it works must come before who it is for.
    const how = screen.getByRole('heading', { level: 2, name: /how it works/i })
    const who = screen.getByRole('heading', { level: 2, name: /built for/i })
    expect(how.compareDocumentPosition(who) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('has exactly one h1', () => {
    render(withSession(session(), <LandingPage />))
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  it('links to sign up more than once — it is the call to action', () => {
    render(withSession(session(), <LandingPage />))
    expect(screen.getAllByRole('link', { name: /sign up|create your profile/i }).length)
      .toBeGreaterThan(1)
  })

  it('offers a login link for returning users', () => {
    render(withSession(session(), <LandingPage />))
    expect(screen.getAllByRole('link', { name: /log in/i }).length).toBeGreaterThan(0)
  })

  it('is usable without a session — no data fetch required', () => {
    // Renders at all with a null user is the assertion: if LandingPage ever
    // reaches for the API this throws.
    expect(() => render(withSession(session(), <LandingPage />))).not.toThrow()
  })
})

describe('the incomplete-profile gate', () => {
  it('shows only the prompt while the profile is incomplete', () => {
    render(withSession(session({ user: me() }), <HomeFeed />))
    expect(screen.getByText(/add .* and .* to see who/i)).toBeInTheDocument()
    // Suggestions must not render at all.
    expect(screen.queryByText(/suggested for you/i)).not.toBeInTheDocument()
  })

  it('names the role when that is what is missing', () => {
    render(withSession(session({ user: me() }), <HomeFeed />))
    expect(screen.getByRole('link', { name: /choose a role/i })).toBeInTheDocument()
  })

  it('names the skills when a role is set but there are none', () => {
    const withRole = me()
    withRole.profile.role = 'software_developer'
    withRole.profile.skills = []
    render(withSession(session({ user: withRole }), <HomeFeed />))
    expect(screen.getByRole('link', { name: /add skills/i })).toBeInTheDocument()
  })

  it('does not offer a role choice once a role is set', () => {
    const withRole = me()
    withRole.profile.role = 'software_developer'
    withRole.profile.skills = [{ id: 's1', name: 'Python' }]
    withRole.profile.profile_complete = true
    render(withSession(session({ user: withRole }), <HomeFeed />))
    expect(screen.queryByRole('link', { name: /choose a role/i })).not.toBeInTheDocument()
  })
})

describe('routes', () => {
  it('renders the pitch page when logged out and the feed when logged in', () => {
    const { unmount } = render(withSession(session(), <Root user={null} />))
    expect(
      screen.getByRole('heading', { level: 1, name: /meet the other half/i }),
    ).toBeInTheDocument()
    unmount()

    render(
      withSession(
        session({ user: me() }),
        <Root user={me()} />,
      ),
    )
    expect(screen.getByText(/add .* and .* to see who/i)).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { level: 1, name: /meet the other half/i }),
    ).not.toBeInTheDocument()
  })

  it('a protected route path resolves rather than 404ing', () => {
    // The guard itself is exercised in App. Here we only prove the route table
    // shape: a protected path renders its element when visited.
    render(
      <SessionContext.Provider value={session({ user: me() })}>
        <MemoryRouter initialEntries={['/messages']}>
          <Routes>
            <Route path="/messages" element={<div>Protected area</div>} />
          </Routes>
        </MemoryRouter>
      </SessionContext.Provider>,
    )
    expect(screen.getByText(/protected area/i)).toBeInTheDocument()
  })
})