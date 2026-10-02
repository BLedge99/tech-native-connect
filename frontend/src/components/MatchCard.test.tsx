import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { MatchCard, ConnectionAction } from './MatchCard'
import { Avatar, EmptyState, ErrorState, Spinner } from './ui'
import type { Match, UserPublic } from '../api/types'

function user(overrides: Partial<UserPublic> = {}): UserPublic {
  return {
    id: 'u1',
    display_name: 'Priya Sharma',
    first_name: 'Priya',
    created_at: '2026-10-01T09:00:00Z',
    profile: {
      bio: null,
      role: 'business_developer',
      course: { id: 'c1', name: 'Business Development' },
      looking_for: null,
      skills: [{ id: 's1', name: 'Pitching' }],
      interests: [],
      profile_complete: true,
      has_photo: false,
      photo_url: null,
    },
    ...overrides,
  }
}

function summary() {
  return {
    id: 'u1',
    display_name: 'Priya Sharma',
    first_name: 'Priya',
    has_photo: false,
    photo_url: null,
  }
}

function match(overrides: Partial<Match> = {}): Match {
  return {
    user: user(),
    score: 70,
    reasons: ['You both know Python.', 'Both on Software Development.'],
    shared_skills: [{ id: 's1', name: 'Python' }],
    connection_state: 'none',
    ...overrides,
  }
}

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('MatchCard', () => {
  it('shows the reasons — the reason string is as important as the ordering', () => {
    renderWithRouter(<MatchCard match={match()} />)
    expect(screen.getByText(/you both know python/i)).toBeInTheDocument()
    expect(screen.getByText(/both on software development/i)).toBeInTheDocument()
  })

  it('shows at most two reasons on the card', () => {
    const m = match({
      reasons: ['One.', 'Two.', 'Three.', 'Four.'],
    })
    renderWithRouter(<MatchCard match={m} />)
    expect(screen.queryByText(/three/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/four/i)).not.toBeInTheDocument()
  })

  it('renders initials when there is no photo', () => {
    render(<Avatar user={summary()} />)
    // "Priya Sharma" -> PS
    expect(screen.getByText('PS')).toBeInTheDocument()
  })

  it('renders the photo when one exists', () => {
    const { container } = render(
      <Avatar user={{ id: 'u1', display_name: 'Priya Sharma', has_photo: true, photo_url: '/api/v1/users/u1/photo' }} />,
    )
    const img = container.querySelector('img')
    expect(img).toHaveAttribute('src', '/api/v1/users/u1/photo')
  })

  it('gives the same person the same fallback colour every time', () => {
    const { container: first } = render(<Avatar user={summary()} />)
    const { container: second } = render(<Avatar user={summary()} />)
    const bg = (c: HTMLElement) =>
      c.querySelector('div[aria-hidden]')?.getAttribute('style')
    expect(bg(first)).toEqual(bg(second))
  })
})

describe('ConnectionAction', () => {
  it('offers Connect when there is no connection', () => {
    const onConnect = vi.fn()
    renderWithRouter(<ConnectionAction state="none" onConnect={onConnect} />)
    expect(screen.getByRole('button', { name: /connect/i })).toBeInTheDocument()
  })

  it('never shows Connect to someone with a pending request we sent', () => {
    renderWithRouter(<ConnectionAction state="pending_outgoing" />)
    expect(screen.queryByRole('button', { name: /^connect$/i })).not.toBeInTheDocument()
    expect(screen.getByText(/request sent/i)).toBeInTheDocument()
  })

  it('never shows Connect to someone with a pending request we received', () => {
    renderWithRouter(<ConnectionAction state="pending_incoming" />)
    expect(screen.queryByRole('button', { name: /^connect$/i })).not.toBeInTheDocument()
    expect(screen.getByText(/wants to connect/i)).toBeInTheDocument()
  })

  it('offers Message once connected', () => {
    renderWithRouter(<ConnectionAction state="connected" />)
    expect(screen.getByText(/message/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^connect$/i })).not.toBeInTheDocument()
  })

  it('calls onConnect when clicked', async () => {
    const onConnect = vi.fn()
    renderWithRouter(<ConnectionAction state="none" onConnect={onConnect} />)
    await userEvent.click(screen.getByRole('button', { name: /connect/i }))
    expect(onConnect).toHaveBeenCalledTimes(1)
  })
})

describe('shared states', () => {
  it('renders a spinner with a label', () => {
    render(<Spinner label="Finding people" />)
    expect(screen.getByRole('status')).toHaveTextContent(/finding people/i)
  })

  it('an error state offers a retry', async () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Couldn't load suggestions." onRetry={onRetry} />)
    expect(screen.getByText(/couldn't load suggestions/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('an empty state is not an error', () => {
    render(<EmptyState title="No conversations yet." />)
    expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('an empty state can carry a next action', () => {
    renderWithRouter(<EmptyState title="No requests." action={<a href="/matches">Browse</a>} />)
    expect(screen.getByRole('link', { name: /browse/i })).toBeInTheDocument()
  })
})