import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import App from './App';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

function renderApp(fetchMock?: (input: RequestInfo | URL) => Promise<Response>) {
  vi.stubGlobal('fetch', fetchMock ?? vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ error: { code: 'unauthenticated', message: 'Sign in to continue.' } }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }),
  ));
  return render(<BrowserRouter><App /></BrowserRouter>);
}

function stubCurrentUser(profileComplete: boolean, isAdmin = false) {
  const skills = profileComplete ? [{ id: 'skill-1', name: 'Python' }] : [];
  const user = {
    id: 'user-1',
    email: 'sam@example.com',
    display_name: 'Sam Example',
    first_name: 'Sam',
    is_admin: isAdmin,
    profile_complete: profileComplete,
    profile: {
      bio: null,
      role: profileComplete ? 'software_developer' : null,
      course: null,
      looking_for: null,
      skills,
      interests: [],
      has_photo: false,
      photo_url: null,
      profile_complete: profileComplete,
    },
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/users/me')) return new Response(JSON.stringify(user), { status: 200 });
    if (url.includes('/matches')) return new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 });
    if (url.includes('/notifications')) return new Response(JSON.stringify({ items: [], next_cursor: null, unread_count: 0 }), { status: 200 });
    return new Response(JSON.stringify({ error: { code: 'not_found', message: 'Not found.' } }), { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('public authentication flow', () => {
  it('shows the public pitch and provides a working registration link', async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole('link', { name: /join your cohort/i }));

    expect(await screen.findByRole('heading', { name: 'Make the first move.' })).toBeInTheDocument();
    expect(screen.getByLabelText('Your name')).toBeRequired();
    expect(screen.getByLabelText('Email address')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('minLength', '8');
  });
});

describe('authenticated home feed', () => {
  it('does not request matches or activity while the profile is incomplete', async () => {
    const fetchMock = stubCurrentUser(false);
    renderApp(fetchMock);

    expect(await screen.findByText('Add a role and at least one skill to see matches.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit profile ↗' })).toHaveAttribute('href', '/profile/edit');
    expect(screen.getByRole('link', { name: 'Add skills ↗' })).toHaveAttribute('href', '/profile/edit?focus=skills#skills');
    const requests = fetchMock.mock.calls.map(([input]) => String(input));
    expect(requests.some((url) => url.includes('/matches'))).toBe(false);
    expect(requests.some((url) => url.includes('/notifications?limit=5'))).toBe(false);
  });

  it('renders both widgets when the profile is complete', async () => {
    const fetchMock = stubCurrentUser(true);
    renderApp(fetchMock);

    expect(await screen.findByRole('heading', { name: 'Your matches' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Recent activity' })).toBeInTheDocument();
    expect(screen.queryByText('Add a role and at least one skill to see matches.')).not.toBeInTheDocument();
  });

  it('shows a forbidden page to signed-in non-admins', async () => {
    stubCurrentUser(false);
    window.history.replaceState({}, '', '/admin');
    render(<BrowserRouter><App /></BrowserRouter>);

    expect(await screen.findByRole('heading', { name: 'This area is for admins.' })).toBeInTheDocument();
  });
});