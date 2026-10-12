import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import {
  Link, Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams,
} from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { useRealtime, RealtimeProvider } from './realtime/RealtimeContext';
import { LoginPage, MagicLinkPage, RegisterPage } from './pages/AuthPages';
import * as api from './api/domain';
import type { ApiError } from './api/http';
import type { Idea, MatchItem, Message, Profile, PublicUser, Ref } from './api/domain';

function messageOf(error: unknown) {
  return (error as ApiError)?.error?.message ?? 'Something went wrong. Please try again.';
}

function useLoad<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try { setData(await loader()); } catch (reason) { setError(messageOf(reason)); } finally { setLoading(false); }
  // The caller supplies explicit dependencies for the loader.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);
  useEffect(() => { void reload(); }, [reload]);
  return { data, setData, loading, error, reload };
}

function Feedback({ loading, error, empty, isEmpty = false, retry, children }: {
  loading?: boolean; error?: string; empty?: string; isEmpty?: boolean; retry?: () => void; children?: ReactNode;
}) {
  if (loading) return <p className="state-message" role="status">Loading…</p>;
  if (error) return <div className="state-message state-error" role="alert"><span>{error}</span>{retry && <button className="small-button" onClick={retry}>Retry</button>}</div>;
  if (isEmpty && empty) return <p className="state-message">{empty}</p>;
  return <>{children}</>;
}

function PublicLanding() {
  return (
    <main className="welcome-page">
      <header className="welcome-header"><Link className="wordmark" to="/">Bootcamp Connect<span>.</span></Link><Link className="text-link" to="/login">Sign in</Link></header>
      <section className="welcome-copy">
        <p className="eyebrow">Same cohort. Different superpowers.</p>
        <h1>Build the thing<br />you keep talking about.</h1>
        <p>Bootcamp Connect matches software and business developers in the same cohort so they can build ideas together.</p>
        <Link className="primary-link" to="/register">Join your cohort <span aria-hidden="true">↗</span></Link>
      </section>
      <section className="landing-section problem-section">
        <p className="eyebrow">The problem</p>
        <h2>Good ideas need more than one kind of talent.</h2>
        <p>Software developers need a business partner who can shape and sell what they build. Business developers need someone who can turn their idea into a working product.</p>
      </section>
      <section className="landing-section">
        <p className="eyebrow">How it works</p>
        <ol className="landing-steps">
          <li><span>01</span><strong>Complete your profile</strong><p>Tell your cohort your role, skills and interests.</p></li>
          <li><span>02</span><strong>Meet your matches</strong><p>Find shared skills and complementary roles.</p></li>
          <li><span>03</span><strong>Connect and talk</strong><p>Accept a connection and start planning together.</p></li>
        </ol>
      </section>
      <section className="landing-section">
        <p className="eyebrow">Who it’s for</p>
        <div className="landing-audiences">
          <article><h2>Software developers</h2><p>Meet a business-minded partner who can help take your build beyond the classroom.</p></article>
          <article><h2>Business developers</h2><p>Find a technical partner in your bootcamp cohort who can bring your idea to life.</p></article>
        </div>
        <p className="landing-cohort-note">A focused way to meet the people studying alongside you — not another general network.</p>
      </section>
      <section className="landing-section landing-cta">
        <div><p className="eyebrow">Make your next project a team effort</p><h2>Your cohort is closer than you think.</h2></div>
        <div className="landing-cta-actions"><Link className="primary-link" to="/register">Create your profile ↗</Link><p>Already have an account? <Link to="/login">Log in</Link></p></div>
      </section>
      <footer className="welcome-footer"><span>01 — Tell us what you’re building</span><span>02 — Find your complementary skills</span><span>03 — Make something together</span></footer>
    </main>
  );
}

function Guard({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="page-loading" role="status">Loading your session…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (admin && !user.is_admin) return <main className="not-found" role="alert"><p className="eyebrow">403 / Forbidden</p><h1>This area is for admins.</h1><p>You’re signed in, but your account does not have admin access.</p><Link className="text-link" to="/">Back to your home feed ↗</Link></main>;
  return <>{children}</>;
}

function refreshNotificationBadge() {
  window.dispatchEvent(new Event('bootcamp-notifications-updated'));
}

function AppLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { events } = useRealtime();
  const location = useLocation();
  const [toast, setToast] = useState('');
  const [unread, setUnread] = useState(0);
  const [notificationError, setNotificationError] = useState('');
  const [logoutError, setLogoutError] = useState('');
  useEffect(() => {
    const notification = events[events.length - 1];
    if (!notification) return;
    if (!notification.type.includes('notification')) return;
    const text = String(notification.data.text ?? notification.data.message ?? 'You have a new notification.');
    setToast(text);
    const timer = window.setTimeout(() => setToast(''), 5000);
    return () => window.clearTimeout(timer);
  }, [events]);
  useEffect(() => {
    let active = true;
    const refresh = () => api.unreadNotificationCount()
      .then((result) => {
        if (active) {
          setUnread(result.unread_count);
          setNotificationError('');
        }
      })
      .catch((reason) => {
        if (active) setNotificationError(messageOf(reason));
      });
    const onNotificationChange = () => void refresh();
    void refresh();
    window.addEventListener('bootcamp-notifications-updated', onNotificationChange);
    return () => {
      active = false;
      window.removeEventListener('bootcamp-notifications-updated', onNotificationChange);
    };
  }, [events, location.pathname]);
  async function signOut() {
    setLogoutError('');
    try { await logout(); } catch (reason) { setLogoutError(messageOf(reason)); }
  }
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link className="wordmark" to="/">Bootcamp Connect<span>.</span></Link>
        <nav className="main-nav" aria-label="Main navigation">
          <Link to="/">Home</Link><Link to="/matches">Matches</Link><Link to="/connections">Connections</Link>
          <Link to="/messages">Messages</Link><Link to="/ideas">Ideas</Link>
        </nav>
        <div className="header-actions">
          <Link className="notification-link" to="/notifications" aria-label={`Notifications${notificationError ? ', count unavailable' : unread ? `, ${unread} unread` : ''}`} title={notificationError || undefined}>Updates <span className="badge">{notificationError ? '!' : unread}</span></Link>
          <Link to="/profile">{user?.first_name ?? 'Profile'}</Link>
          {user?.is_admin && <Link to="/admin">Admin</Link>}
          <button className="quiet-button" onClick={() => void signOut()}>Sign out</button>
        </div>
      </header>
      {logoutError && <p className="form-error header-error" role="alert">{logoutError}</p>}
      {toast && <div className="toast" role="status">{toast}<button aria-label="Dismiss notification" onClick={() => setToast('')}>×</button></div>}
      <main className="app-content">{children}</main>
    </div>
  );
}

function PageHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>{children}</div>;
}

function HomePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const profile = useLoad(() => api.getProfile());
  const profileComplete = profile.data?.profile_complete === true;
  const matches = useLoad(() => profileComplete
    ? api.getMatches({ limit: 6 })
    : Promise.resolve({ items: [], next_cursor: null }), [profileComplete]);
  const activity = useLoad(() => profileComplete
    ? api.getNotifications(5)
    : Promise.resolve({ items: [], next_cursor: null, unread_count: 0 }), [profileComplete]);
  const profileData = profile.data?.profile;
  const [activityError, setActivityError] = useState('');
  async function openActivity(item: NonNullable<typeof activity.data>['items'][number]) {
    setActivityError('');
    if (!item.read_at) {
      try { await api.markNotificationRead(item.id); refreshNotificationBadge(); } catch (reason) { setActivityError(messageOf(reason)); return; }
    }
    navigate(item.url);
  }
  if (profile.loading) return <div className="page-stack"><PageHeading eyebrow="Your cohort, connected" title={`Hi ${user?.first_name ?? 'there'}.`} /><Feedback loading /></div>;
  if (profile.error || !profileData) return <div className="page-stack"><PageHeading eyebrow="Your cohort, connected" title={`Hi ${user?.first_name ?? 'there'}.`} /><Feedback error={profile.error || 'Your profile could not be loaded.'} retry={() => void profile.reload()} /></div>;
  if (!profileComplete) {
    const missingRole = !profileData.role;
    const missingSkills = profileData.skills.length === 0;
    return <div className="page-stack">
      <PageHeading eyebrow="Your cohort, connected" title={`Hi ${user?.first_name ?? 'there'}.`} />
      <section className="welcome-card profile-incomplete-card">
        <div><p className="eyebrow">Your next step</p><h2>Complete your profile to meet your cohort.</h2>
          <p>{missingRole && missingSkills ? 'Add a role and at least one skill to see matches.' : missingRole ? 'Choose a role to see matches.' : 'Add at least one skill to see matches.'}</p>
          <div className="card-actions"><Link className="text-link" to="/profile/edit">Edit profile ↗</Link><Link className="text-link" to="/profile/edit?focus=skills#skills">Add skills ↗</Link></div>
        </div>
      </section>
    </div>;
  }
  return (
    <div className="page-stack">
      <PageHeading eyebrow="Your cohort, connected" title={`Hi ${user?.first_name ?? 'there'}.`}>
        <Link className="primary-link" to="/profile/edit">Your profile ↗</Link>
      </PageHeading>
      <section className="section-block"><div className="section-title"><h2>Your matches</h2><Link to="/matches">See all ↗</Link></div>
        <Feedback loading={matches.loading} error={matches.error} empty="No matches to show yet. Check back soon." isEmpty={!matches.loading && !matches.error && (matches.data?.items.length ?? 0) === 0} retry={() => void matches.reload()}><div className="card-grid">{matches.data?.items.map((match) => <MatchCard key={match.user.id} item={match} />)}</div></Feedback>
      </section>
      <section className="section-block"><div className="section-title"><h2>Recent activity</h2><Link to="/notifications">See all ↗</Link></div>
        {activityError && <p className="form-error" role="alert">{activityError}</p>}
        <Feedback loading={activity.loading} error={activity.error} empty="You’re all caught up." isEmpty={!activity.loading && !activity.error && (activity.data?.items.length ?? 0) === 0} retry={() => void activity.reload()}><div className="list-stack">{activity.data?.items.map((item) => <button className={`notification-card notification-row ${item.read_at ? '' : 'unread'}`} key={item.id} onClick={() => void openActivity(item)}><span><span>{item.data.text}</span><time>{new Date(item.created_at).toLocaleString()}</time></span><span aria-hidden="true">↗</span></button>)}</div></Feedback>
      </section>
    </div>
  );
}

function PersonCard({ person, children }: { person: PublicUser; children?: ReactNode }) {
  return <article className="person-card">
    {person.photo_url ? <img className="person-avatar" src={person.photo_url} alt="" /> : <div className="person-avatar" aria-hidden="true">{person.first_name?.slice(0, 1) ?? person.display_name.slice(0, 1)}</div>}
    <div className="person-card-main"><h3><Link to={`/users/${person.id}`}>{person.display_name}</Link></h3><p>{person.role?.replace('_', ' ') ?? 'Cohort member'}{person.course ? ` · ${person.course.name}` : ''}</p>
      {person.bio && <p className="clamp-text">{person.bio}</p>}{person.skills?.length ? <div className="chip-list">{person.skills.map((skill) => <span className="chip" key={skill.id}>{skill.name}</span>)}</div> : null}
      {children && <div className="card-actions">{children}</div>}</div>
  </article>;
}

function MatchCard({ item }: { item: MatchItem }) {
  const [state, setState] = useState(item.connection_state);
  const [error, setError] = useState('');
  async function connect() {
    setError('');
    try { await api.createConnection(item.user.id); setState('pending_outgoing'); } catch (reason) { setError(messageOf(reason)); }
  }
  return <article className="match-card"><div className="match-score">{item.score}<small>match</small></div>
    <PersonCard person={item.user}>
      {state === 'none' && <button className="small-primary" onClick={() => void connect()}>Connect</button>}
      {state === 'pending_outgoing' && <span className="status-label">Request sent</span>}
      {state === 'pending_incoming' && <Link className="text-link" to="/connections?tab=received">Respond to request</Link>}
      {state === 'connected' && <Link className="text-link" to="/messages">Connected · message</Link>}
    </PersonCard>
    <ul className="reason-list">{item.reasons.slice(0, 2).map((reason) => <li key={reason}>{reason}</li>)}</ul>
    {error && <p className="form-error" role="alert">{error}</p>}
  </article>;
}

function MatchesPage() {
  const profile = useLoad(() => api.getProfile());
  const profileComplete = profile.data?.profile_complete === true;
  const emptyRefs = { items: [], next_cursor: null };
  const courses = useLoad(() => profileComplete ? api.getCourses() : Promise.resolve(emptyRefs), [profileComplete]);
  const skills = useLoad(() => profileComplete ? api.getSkills() : Promise.resolve(emptyRefs), [profileComplete]);
  const interests = useLoad(() => profileComplete ? api.getInterests() : Promise.resolve(emptyRefs), [profileComplete]);
  const [role, setRole] = useState('');
  const [course, setCourse] = useState('');
  const [skill, setSkill] = useState('');
  const [interest, setInterest] = useState('');
  const [refresh, setRefresh] = useState(0);
  const matches = useLoad(() => profileComplete
    ? api.getMatches({ limit: 50, role: role || undefined, course_id: course || undefined, skill: skill ? [skill] : undefined, interest: interest ? [interest] : undefined })
    : Promise.resolve({ items: [], next_cursor: null }), [profileComplete, role, course, skill, interest, refresh]);
  if (profile.loading) return <div className="page-stack"><PageHeading eyebrow="Find your people" title="People worth building with." /><Feedback loading /></div>;
  if (profile.error) return <div className="page-stack"><PageHeading eyebrow="Find your people" title="People worth building with." /><Feedback error={profile.error} retry={() => void profile.reload()} /></div>;
  if (!profileComplete) return <div className="page-stack">
    <PageHeading eyebrow="Find your people" title="People worth building with." />
    <section className="welcome-card"><div><p className="eyebrow">One step first</p><h2>Complete your profile to unlock matches.</h2><p>Choose a role and add at least one skill so we can find relevant people.</p></div><Link className="primary-link" to="/profile/edit">Complete profile ↗</Link></section>
  </div>;
  return <div className="page-stack"><PageHeading eyebrow="Find your people" title="People worth building with." />
    <form className="filters" onSubmit={(event) => { event.preventDefault(); setRefresh((current) => current + 1); }} aria-label="Filter matches">
      <label>Role<select value={role} onChange={(event) => setRole(event.target.value)}><option value="">Any role</option><option value="software_developer">Software developer</option><option value="business_developer">Business developer</option></select></label>
      <label>Course<select value={course} onChange={(event) => setCourse(event.target.value)}><option value="">Any course</option>{courses.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Skill<select value={skill} onChange={(event) => setSkill(event.target.value)}><option value="">Any skill</option>{skills.data?.items.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}</select></label>
      <label>Interest<select value={interest} onChange={(event) => setInterest(event.target.value)}><option value="">Any interest</option>{interests.data?.items.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}</select></label>
    </form>
    <Feedback loading={matches.loading} error={matches.error} empty="No matches found. Try changing your filters, or complete your profile." isEmpty={!matches.loading && !matches.error && (matches.data?.items.length ?? 0) === 0}><div className="card-grid">{matches.data?.items.map((item) => <MatchCard key={item.user.id} item={item} />)}</div></Feedback>
  </div>;
}

function ProfilePage() {
  const result = useLoad(() => api.getProfile());
  const location = useLocation();
  const editing = location.pathname === '/profile/edit';
  const courses = useLoad(() => api.getCourses());
  const skills = useLoad(() => api.getSkills());
  const interests = useLoad(() => api.getInterests());
  const [form, setForm] = useState<Profile | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const profile = result.data?.profile;
    if (profile) setForm((current) => current ?? profile);
  }, [result.data]);
  useEffect(() => {
    if (form && location.hash) document.querySelector(location.hash)?.scrollIntoView({ block: 'center' });
  }, [form, location.hash]);
  if (result.loading) return <Feedback loading />;
  if (result.error || !form) return <Feedback error={result.error || 'Profile unavailable.'} />;
  if (!editing) return <div className="page-stack narrow-page">
    <PageHeading eyebrow="Your profile" title={result.data?.display_name ?? 'Your profile'}><Link className="primary-link" to="/profile/edit">Edit profile ↗</Link></PageHeading>
    <div className="form-panel profile-read">
      {form.photo_url && <img className="profile-photo" src={form.photo_url} alt={`${result.data?.display_name ?? 'Your'} profile`} />}
      <p>{form.role?.replace('_', ' ') ?? 'Role not chosen'}{form.course ? ` · ${form.course.name}` : ''}</p>
      {form.bio && <p>{form.bio}</p>}
      {form.looking_for && <p><strong>Looking for:</strong> {form.looking_for}</p>}
      <section><h2>Skills</h2>{form.skills.length ? <div className="chip-list">{form.skills.map((item) => <span className="chip" key={item.id}>{item.name}</span>)}</div> : <p>No skills added yet.</p>}</section>
      <section><h2>Interests</h2>{form.interests.length ? <div className="chip-list">{form.interests.map((item) => <span className="chip" key={item.id}>{item.name}</span>)}</div> : <p>No interests added yet.</p>}</section>
    </div>
  </div>;
  function update<K extends keyof Profile>(key: K, value: Profile[K]) { setForm((current) => current ? { ...current, [key]: value } : current); }
  function toggleRef(key: 'skills' | 'interests', id: string) {
    const current = form?.[key] ?? [];
    const ref = (key === 'skills' ? skills.data?.items : interests.data?.items)?.find((item) => item.id === id);
    if (!ref) return;
    update(key, current.some((item) => item.id === id) ? current.filter((item) => item.id !== id) : [...current, ref]);
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!form) return;
    setSaving(true); setError(''); setNotice('');
    try {
      const saved = await api.updateProfile({ bio: form.bio, role: form.role, course_id: form.course?.id ?? null, looking_for: form.looking_for, skill_ids: form.skills.map((item) => item.id), interest_ids: form.interests.map((item) => item.id) });
      setForm(saved.profile);
      setNotice('Profile saved.');
    } catch (reason) { setError(messageOf(reason)); } finally { setSaving(false); }
  }
  async function photoChanged(file?: File) {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setError('Choose a JPG, PNG or WebP image.'); return; }
    if (file.size > 2 * 1024 * 1024) { setError('Photo must be 2 MB or smaller.'); return; }
    try {
      const uploaded = await api.uploadPhoto(file);
      setForm((current) => current ? { ...current, has_photo: true, photo_url: `${uploaded.photo_url}?v=${Date.now()}` } : current);
      setNotice('Photo uploaded.');
    } catch (reason) { setError(messageOf(reason)); }
  }
  async function removePhoto() {
    try {
      await api.deletePhoto();
      setForm((current) => current ? { ...current, has_photo: false, photo_url: null } : current);
      setNotice('Photo removed.');
    } catch (reason) { setError(messageOf(reason)); }
  }
  return <div className="page-stack narrow-page"><PageHeading eyebrow="Your profile" title="Show the cohort what you bring." />
    <form className="form-panel" onSubmit={(event) => void save(event)}>
      <div className="form-grid">
        <label className="wide-field">About you <textarea maxLength={500} rows={4} value={form.bio ?? ''} onChange={(event) => update('bio', event.target.value)} /></label>
        <label id="role">Your role<select required value={form.role ?? ''} onChange={(event) => update('role', (event.target.value || null) as Profile['role'])}><option value="">Choose a role</option><option value="software_developer">Software developer</option><option value="business_developer">Business developer</option></select></label>
        <label>Your course<select value={form.course?.id ?? ''} onChange={(event) => update('course', courses.data?.items.find((item) => item.id === event.target.value) ?? null)}><option value="">Choose a course</option>{courses.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label className="wide-field">What are you looking for? <textarea maxLength={300} rows={3} value={form.looking_for ?? ''} onChange={(event) => update('looking_for', event.target.value)} /></label>
      </div>
      <fieldset id="skills" className="choice-field"><legend>Skills <span>(choose at least one)</span></legend><div className="choice-grid">{skills.data?.items.map((item) => <label className="check-option" key={item.id}><input type="checkbox" checked={form.skills.some((value) => value.id === item.id)} onChange={() => toggleRef('skills', item.id)} />{item.name}</label>)}</div></fieldset>
      <fieldset className="choice-field"><legend>Interests</legend><div className="choice-grid">{interests.data?.items.map((item) => <label className="check-option" key={item.id}><input type="checkbox" checked={form.interests.some((value) => value.id === item.id)} onChange={() => toggleRef('interests', item.id)} />{item.name}</label>)}</div></fieldset>
      <div className="photo-control">{form.photo_url && <img className="profile-photo" src={form.photo_url} alt="Your current profile" />}<label>Profile photo <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => void photoChanged(event.target.files?.[0])} /></label>{form.has_photo && <button type="button" className="quiet-button" onClick={() => void removePhoto()}>Remove photo</button>}</div>
      {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
      <button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Save profile'} <span aria-hidden="true">↗</span></button>
    </form>
  </div>;
}

function PersonPage() {
  const { userId = '' } = useParams();
  const person = useLoad(() => api.getPublicProfile(userId), [userId]);
  const summary = person.data && {
    ...person.data,
    role: person.data.profile.role,
    course: person.data.profile.course,
    bio: person.data.profile.bio,
    looking_for: person.data.profile.looking_for,
    skills: person.data.profile.skills,
    interests: person.data.profile.interests,
    has_photo: person.data.profile.has_photo,
    photo_url: person.data.profile.photo_url,
  };
  return <div className="page-stack narrow-page"><PageHeading eyebrow="Cohort profile" title={person.data?.display_name ?? 'Meet a cohort member'} />
    <Feedback loading={person.loading} error={person.error}>{person.data && summary && <div className="form-panel"><PersonCard person={summary} />{summary.bio && <p>{summary.bio}</p>}{summary.looking_for && <p><strong>Looking for:</strong> {summary.looking_for}</p>}</div>}</Feedback>
  </div>;
}

function ConnectionsPage() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState(params.get('tab') ?? 'received');
  const [actionError, setActionError] = useState('');
  useEffect(() => { setParams({ tab }, { replace: true }); }, [tab, setParams]);
  const connections = useLoad(() => api.getConnections(tab), [tab]);
  async function act(connection: api.Connection, action: 'accept' | 'decline' | 'withdraw') {
    setActionError('');
    try {
      if (action === 'withdraw') await api.withdrawConnection(connection.id);
      else await api.answerConnection(connection.id, action);
      await connections.reload();
    } catch (reason) { setActionError(messageOf(reason)); }
  }
  return <div className="page-stack"><PageHeading eyebrow="Your network" title="Connections." />
    <div className="tabs" role="tablist" aria-label="Connection lists">{[['received', 'Received'], ['sent', 'Sent'], ['connected', 'Connected']].map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}</div>
    {actionError && <p className="form-error" role="alert">{actionError}</p>}
    <Feedback loading={connections.loading} error={connections.error} empty={`No ${tab} connections yet.`} isEmpty={!connections.loading && !connections.error && (connections.data?.items.length ?? 0) === 0}><div className="list-stack">{connections.data?.items.map((connection) => <article className="list-card" key={connection.id}><PersonCard person={connection.other} /><div className="request-detail">{connection.message && <p>“{connection.message}”</p>}<span className="status-label">{connection.status}</span>
      {connection.status === 'pending' && connection.viewer_is_sender && <button className="small-button" onClick={() => void act(connection, 'withdraw')}>Withdraw</button>}
      {connection.status === 'pending' && !connection.viewer_is_sender && <><button className="small-primary" onClick={() => void act(connection, 'accept')}>Accept</button><button className="small-button" onClick={() => void act(connection, 'decline')}>Decline</button></>}
      {connection.status === 'accepted' && <Link className="text-link" to={`/messages/${connection.id}`}>Open messages ↗</Link>}
    </div></article>)}</div></Feedback>
  </div>;
}

function ThreadsPage() {
  const threads = useLoad(() => api.getThreads());
  return <div className="page-stack"><PageHeading eyebrow="Conversations" title="Messages." />
    <Feedback loading={threads.loading} error={threads.error} empty="No conversations yet. A chat opens after a connection is accepted." isEmpty={!threads.loading && !threads.error && (threads.data?.items.length ?? 0) === 0}>
      <div className="list-stack">{threads.data?.items.map((thread) => <Link className="thread-card" key={thread.id} to={`/messages/${thread.id}`}><div className="person-avatar">{thread.other.first_name?.slice(0, 1)}</div><div><strong>{thread.other.display_name}</strong><p>{thread.last_message?.body ?? 'Start your conversation'}</p></div>{thread.unread_count > 0 && <span className="badge">{thread.unread_count}</span>}</Link>)}</div>
    </Feedback>
  </div>;
}

function ChatPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const realtime = useRealtime();
  const thread = useLoad(() => api.getThread(id), [id]);
  const history = useLoad(() => api.getMessages(id), [id]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const navigate = useNavigate();
  useEffect(() => {
    const historyItems = history.data?.items;
    if (!historyItems) return;
    setMessages((current) => {
      const merged = [...historyItems];
      current.forEach((message) => {
        if (!merged.some((item) => item.id === message.id || (message.client_id && item.client_id === message.client_id))) {
          merged.push(message);
        }
      });
      return merged;
    });
  }, [history.data]);
  const liveThreadId = messages.find((message) => !message.pending)?.thread_id
    ?? (thread.data?.last_message ? thread.data.id : undefined);
  const subscribed = liveThreadId !== undefined && realtime.subscribedThreads.includes(liveThreadId);
  useEffect(() => liveThreadId ? realtime.subscribe(liveThreadId) : undefined, [realtime.subscribe, liveThreadId]);
  useEffect(() => {
    if (subscribed) void history.reload();
  }, [history.reload, subscribed]);
  useEffect(() => {
    const incoming = realtime.events.filter((event) => event.type.includes('message')).flatMap((event) => {
      const value = event.data.message ?? event.data;
      return value && typeof value === 'object' && 'body' in value && (value as Message).thread_id === id ? [value as Message] : [];
    });
    if (incoming.length) setMessages((current) => {
      const merged = [...current];
      incoming.forEach((message) => { if (!merged.some((item) => item.id === message.id || (message.client_id && item.client_id === message.client_id))) merged.push(message); });
      return merged;
    });
  }, [realtime.events, id]);
  async function send(event: FormEvent) {
    event.preventDefault(); const trimmed = body.trim();
    if (!trimmed || sending) return;
    setSending(true); setError('');
    const clientId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const optimistic: Message = { id: clientId, client_id: clientId, thread_id: id, sender_id: user?.id ?? '', body: trimmed, created_at: new Date().toISOString(), pending: true };
    setMessages((current) => [...current, optimistic]); setBody('');
    try {
      const saved = await api.postMessage(id, trimmed);
      setMessages((current) => {
        const updated = current.map((item) => item.client_id === clientId ? saved : item);
        return updated.filter((item, index) => updated.findIndex((candidate) => candidate.id === item.id) === index);
      });
      if (saved.thread_id !== id) navigate(`/messages/${saved.thread_id}`, { replace: true });
    } catch (reason) {
      setMessages((current) => current.filter((item) => item.client_id !== clientId)); setBody(trimmed); setError(messageOf(reason));
    } finally { setSending(false); }
  }
  const orderedMessages = useMemo(() => [...messages].sort((a, b) => a.created_at.localeCompare(b.created_at)), [messages]);
  return <div className="page-stack chat-page"><PageHeading eyebrow={subscribed ? 'Live connection' : realtime.connected ? 'Joining conversation…' : 'Reconnecting…'} title={thread.data?.other.display_name ?? 'Conversation'}><Link className="text-link" to="/messages">All conversations</Link></PageHeading>
    <section className="chat-window" aria-label="Conversation messages"><Feedback loading={history.loading} error={thread.error || history.error} empty="Say hello to start the conversation." isEmpty={!history.loading && !thread.error && !history.error && messages.length === 0}>
      {orderedMessages.map((message) => <div className={`message-bubble ${message.sender_id === user?.id ? 'mine' : ''}`} key={message.client_id ?? message.id}><p>{message.body}</p><time>{new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}{message.pending ? ' · Sending' : ''}</time></div>)}
    </Feedback></section>
    {error && <p className="form-error" role="alert">{error}</p>}
    <form className="chat-form" onSubmit={(event) => void send(event)}><label className="sr-only" htmlFor="message-body">Your message</label><textarea id="message-body" maxLength={2000} required rows={2} value={body} onChange={(event) => setBody(event.target.value)} placeholder="Write a message…" /><button className="primary-button" disabled={sending || !body.trim()}>Send ↗</button></form>
  </div>;
}

function NotificationsPage() {
  const notifications = useLoad(() => api.getNotifications(50));
  const [actionError, setActionError] = useState('');
  const navigate = useNavigate();
  async function mark(id: string) { setActionError(''); try { await api.markNotificationRead(id); refreshNotificationBadge(); await notifications.reload(); } catch (reason) { setActionError(messageOf(reason)); } }
  async function markAll() { setActionError(''); try { await api.markAllNotificationsRead(); refreshNotificationBadge(); await notifications.reload(); } catch (reason) { setActionError(messageOf(reason)); } }
  async function openNotification(item: NonNullable<typeof notifications.data>['items'][number]) {
    if (!item.read_at) {
      setActionError('');
      try { await api.markNotificationRead(item.id); refreshNotificationBadge(); } catch (reason) { setActionError(messageOf(reason)); return; }
    }
    navigate(item.url);
  }
  return <div className="page-stack"><PageHeading eyebrow="Updates from your cohort" title="Notifications."><button className="small-button" onClick={() => void markAll()}>Mark all as read</button></PageHeading>
    {actionError && <p className="form-error" role="alert">{actionError}</p>}
    <Feedback loading={notifications.loading} error={notifications.error} empty="You’re all caught up." isEmpty={!notifications.loading && !notifications.error && (notifications.data?.items.length ?? 0) === 0}><div className="list-stack">{notifications.data?.items.map((item) => <article className={`notification-card ${item.read_at ? '' : 'unread'}`} key={item.id}><div><p>{item.data.text}</p><time>{new Date(item.created_at).toLocaleString()}</time></div><div>{!item.read_at && <button className="small-button" onClick={() => void mark(item.id)}>Mark read</button>}<button className="text-link notification-open" onClick={() => void openNotification(item)}>Open ↗</button></div></article>)}</div></Feedback>
  </div>;
}

const ideaCategories = [
  ['find_problem', 'Find a problem'], ['build_product', 'Build a product'], ['design_brand', 'Design a brand'], ['run_campaign', 'Run a campaign'], ['other', 'Other'],
];
function IdeaCard({ idea, onChange }: { idea: Idea; onChange: () => void }) {
  const [error, setError] = useState('');
  async function toggleInterest() {
    try { if (idea.viewer_has_interested) await api.withdrawIdeaInterest(idea.id); else await api.interestInIdea(idea.id); onChange(); } catch (reason) { setError(messageOf(reason)); }
  }
  return <article className="idea-card"><div className="idea-meta"><span className="chip">{idea.category.replace(/_/g, ' ')}</span><span>{idea.interest_count} interested</span></div><h3>{idea.title}</h3><p className="clamp-text">{idea.description}</p>{idea.skills_needed.length > 0 && <div className="chip-list">{idea.skills_needed.map((skill) => <span className="chip" key={skill}>{skill}</span>)}</div>}<p className="idea-author">Posted by {idea.author.display_name}</p>
    {idea.viewer_is_author ? <Link className="text-link" to={`/ideas?edit=${idea.id}`}>Edit idea ↗</Link> : <button className="small-primary" disabled={!idea.is_open} onClick={() => void toggleInterest()}>{idea.viewer_has_interested ? 'Withdraw interest' : 'I’m interested'}</button>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </article>;
}

function IdeaForm({ existing, onSaved, onCancel }: { existing?: Idea; onSaved: () => void; onCancel: () => void }) {
  const [title, setTitle] = useState(existing?.title ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [category, setCategory] = useState(existing?.category ?? 'build_product');
  const [skills, setSkills] = useState(existing?.skills_needed.join(', ') ?? '');
  const [open, setOpen] = useState(existing?.is_open ?? true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError('');
    const input = { title, description, category, skills_needed: skills.split(',').map((item) => item.trim()).filter(Boolean), is_open: open };
    try { if (existing) await api.updateIdea(existing.id, input); else await api.saveIdea(input); onSaved(); }
    catch (reason) { setError(messageOf(reason)); } finally { setSaving(false); }
  }
  return <form className="form-panel idea-form" onSubmit={(event) => void save(event)}><h2>{existing ? 'Edit your idea' : 'Post an idea'}</h2>
    <label>Title<input required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
    <label>Description<textarea required minLength={50} maxLength={2000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
    <label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}>{ideaCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label>Skills needed <span className="help-text">Separate skills with commas.</span><input value={skills} onChange={(event) => setSkills(event.target.value)} /></label>
    {existing && <label className="check-option"><input type="checkbox" checked={open} onChange={(event) => setOpen(event.target.checked)} />This idea is open</label>}
    {error && <p className="form-error" role="alert">{error}</p>}<div className="card-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Save idea'}</button><button type="button" className="small-button" onClick={onCancel}>Cancel</button></div>
  </form>;
}

function IdeasPage() {
  const { id: routeIdeaId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(searchParams.get('edit') ?? '');
  const [mine, setMine] = useState(false);
  const isNew = location.pathname === '/ideas/new';
  useEffect(() => { setEditId(searchParams.get('edit') ?? ''); }, [searchParams]);
  const ideas = useLoad(() => api.getIdeas({ limit: '50', open_only: routeIdeaId ? false : !mine, mine: mine || undefined, search: search || undefined, category: category || undefined }), [search, category, refresh, mine, routeIdeaId]);
  const editIdea = ideas.data?.items.find((item) => item.id === editId);
  const routedIdea = ideas.data?.items.find((item) => item.id === routeIdeaId);
  function done() { setShowForm(false); setEditId(''); setSearchParams({}, { replace: true }); setRefresh((value) => value + 1); if (isNew) navigate('/ideas', { replace: true }); }
  return <div className="page-stack"><PageHeading eyebrow="Project ideas" title={routeIdeaId ? 'An idea from your cohort.' : 'What could we build together?'}>{routeIdeaId ? <Link className="text-link" to="/ideas">Back to the board ↗</Link> : !isNew && <Link className="primary-link" to="/ideas/new">Post an idea ↗</Link>}</PageHeading>
    <div className="filters"><label>Search ideas<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search title or description" /></label><label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{ideaCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="check-option"><input type="checkbox" checked={mine} onChange={(event) => setMine(event.target.checked)} />My ideas (include closed)</label></div>
    {(isNew || showForm || (editId && editIdea)) && <IdeaForm existing={editIdea} onSaved={done} onCancel={done} />}
    {routeIdeaId && !ideas.loading && !routedIdea && <p className="state-message" role="status">This idea is no longer available.</p>}
    {editId && !ideas.loading && !editIdea && <p className="state-message" role="status">That idea is unavailable or is not yours to edit.</p>}
    <Feedback loading={ideas.loading} error={ideas.error} empty={mine ? 'You have not posted any ideas yet.' : 'No open ideas match that search.'} isEmpty={!ideas.loading && !ideas.error && ((routeIdeaId ? ideas.data?.items.filter((idea) => idea.id === routeIdeaId) : ideas.data?.items)?.length ?? 0) === 0}><div className="card-grid">{((routeIdeaId ? ideas.data?.items.filter((idea) => idea.id === routeIdeaId) : ideas.data?.items) ?? []).map((idea) => <IdeaCard key={idea.id} idea={idea} onChange={() => setRefresh((value) => value + 1)} />)}</div></Feedback>
  </div>;
}

function SettingsPage() {
  const { user } = useAuth();
  return <div className="page-stack narrow-page">
    <PageHeading eyebrow="Your account" title="Settings." />
    <section className="form-panel settings-panel"><h2>Account details</h2><p><strong>Name</strong><span>{user?.display_name ?? '—'}</span></p><p><strong>Email</strong><span>{user?.email ?? '—'}</span></p><p>These details are used to identify your account. Profile information can be changed from your profile.</p><Link className="text-link" to="/profile/edit">Edit your profile ↗</Link></section>
  </div>;
}

function AdminPage() {
  const [tab, setTab] = useState('overview');
  const tabs = ['overview', 'users', 'courses', 'skills', 'interests', 'audit'];
  return <div className="page-stack"><PageHeading eyebrow="Cohort operations" title="Admin." />
    <div className="tabs admin-tabs" aria-label="Admin sections">{tabs.map((item) => <button className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)}>{item}</button>)}</div>
    {tab === 'overview' && <AdminOverview />}
    {tab === 'users' && <AdminUsers />}
    {(['courses', 'skills', 'interests'].includes(tab)) && <AdminReferences kind={tab as 'courses' | 'skills' | 'interests'} />}
    {tab === 'audit' && <AdminAudit />}
  </div>;
}

function AdminOverview() {
  const overview = useLoad(() => api.getAdminOverview());
  return <Feedback loading={overview.loading} error={overview.error} empty="No overview data available." isEmpty={!overview.loading && !overview.error && Object.keys(overview.data ?? {}).length === 0}><div className="stats-grid">{Object.entries(overview.data ?? {}).map(([key, value]) => <article className="stat-card" key={key}><strong>{value}</strong><span>{key.replace(/_/g, ' ')}</span></article>)}</div></Feedback>;
}

function AdminUsers() {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [actionError, setActionError] = useState('');
  const users = useLoad(() => api.getAdminUsers(query), [query]);
  async function action(id: string, value: string) {
    setActionError('');
    try { await api.adminAction(id, value); await users.reload(); } catch (reason) { setActionError(messageOf(reason)); }
  }
  return <section className="admin-section"><form className="search-row" onSubmit={(event) => { event.preventDefault(); setQuery(search); }}><label htmlFor="admin-search">Search users</label><input id="admin-search" value={search} onChange={(event) => setSearch(event.target.value)} /><button className="small-primary">Search</button></form>{actionError && <p className="form-error" role="alert">{actionError}</p>}
    <Feedback loading={users.loading} error={users.error} empty="No users found." isEmpty={!users.loading && !users.error && (users.data?.items.length ?? 0) === 0}><div className="list-stack">{users.data?.items.map((person) => <article className="admin-user" key={person.id}><div><strong>{person.display_name}</strong><p>{person.email} · {person.role ?? 'No role'} · {person.is_active ? 'Active' : 'Inactive'}{person.is_admin ? ' · Admin' : ''}</p></div><div className="card-actions">
      {person.is_active ? <button className="small-button" onClick={() => void action(person.id, 'deactivate')}>Deactivate</button> : <button className="small-button" onClick={() => void action(person.id, 'reactivate')}>Reactivate</button>}
      {!person.is_admin && <button className="small-button" onClick={() => void action(person.id, 'grant-admin')}>Grant admin</button>}
    </div></article>)}</div></Feedback>
  </section>;
}

function AdminReferences({ kind }: { kind: 'courses' | 'skills' | 'interests' }) {
  const refs = useLoad(() => api.adminReferenceList(kind), [kind]);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [error, setError] = useState('');
  async function create(event: FormEvent) {
    event.preventDefault(); setError('');
    try { await api.adminCreateReference(kind, { name, ...(kind === 'skills' && category ? { category } : {}) }); setName(''); setCategory(''); await refs.reload(); }
    catch (reason) { setError(messageOf(reason)); }
  }
  async function rename(item: Ref) {
    const next = window.prompt('New name', item.name); if (!next || next === item.name) return;
    try { await api.adminRenameReference(kind, item.id, { name: next }); await refs.reload(); } catch (reason) { setError(messageOf(reason)); }
  }
  async function remove(item: Ref) {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    try { await api.adminDeleteReference(kind as 'skills' | 'interests', item.id); await refs.reload(); } catch (reason) { setError(messageOf(reason)); }
  }
  return <section className="admin-section"><form className="search-row" onSubmit={(event) => void create(event)}><label htmlFor="reference-name">Add {kind.slice(0, -1)}</label><input id="reference-name" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />{kind === 'skills' && <label>Category<input value={category} onChange={(event) => setCategory(event.target.value)} /></label>}<button className="small-primary">Add</button></form>
    {error && <p className="form-error" role="alert">{error}</p>}<Feedback loading={refs.loading} error={refs.error} empty={`No ${kind} configured.`} isEmpty={!refs.loading && !refs.error && (refs.data?.items.length ?? 0) === 0}><div className="reference-list">{refs.data?.items.map((item) => <div className="reference-row" key={item.id}><span>{item.name}{item.category ? <small> · {item.category}</small> : null}</span><div><button className="small-button" onClick={() => void rename(item)}>Rename</button>{kind !== 'courses' && <button className="small-button" onClick={() => void remove(item)}>Delete</button>}</div></div>)}</div></Feedback>
  </section>;
}

function AdminAudit() {
  const audit = useLoad(() => api.getAdminAudit());
  return <Feedback loading={audit.loading} error={audit.error} empty="No admin activity recorded." isEmpty={!audit.loading && !audit.error && (audit.data?.items.length ?? 0) === 0}><div className="list-stack">{audit.data?.items.map((item) => <article className="audit-row" key={item.id}><div><strong>{item.action.replace(/_/g, ' ')}</strong><p>{item.admin.display_name} · {item.target_type ?? 'system'}</p></div><time>{new Date(item.created_at).toLocaleString()}</time></article>)}</div></Feedback>;
}

function NotFound() {
  return <main className="not-found"><p className="eyebrow">404 / Not found</p><h1>This page isn’t in the cohort.</h1><Link className="text-link" to="/">Back home ↗</Link></main>;
}

function Authenticated({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  return <Guard admin={admin}><AppLayout>{children}</AppLayout></Guard>;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-loading" role="status">Loading your session…</div>;
  return <Routes>
    <Route path="/" element={user ? <Authenticated><HomePage /></Authenticated> : <PublicLanding />} />
    <Route path="/register" element={<RegisterPage />} /><Route path="/login" element={<LoginPage />} /><Route path="/forgot-password" element={<MagicLinkPage />} />
    <Route path="/profile" element={<Authenticated><ProfilePage /></Authenticated>} />
    <Route path="/profile/edit" element={<Authenticated><ProfilePage /></Authenticated>} />
    <Route path="/users/:userId" element={<Authenticated><PersonPage /></Authenticated>} />
    <Route path="/matches" element={<Authenticated><MatchesPage /></Authenticated>} />
    <Route path="/connections" element={<Authenticated><ConnectionsPage /></Authenticated>} />
    <Route path="/messages" element={<Authenticated><ThreadsPage /></Authenticated>} />
    <Route path="/messages/:id" element={<Authenticated><ChatPage /></Authenticated>} />
    <Route path="/notifications" element={<Authenticated><NotificationsPage /></Authenticated>} />
    <Route path="/ideas" element={<Authenticated><IdeasPage /></Authenticated>} />
    <Route path="/ideas/new" element={<Authenticated><IdeasPage /></Authenticated>} />
    <Route path="/ideas/:id" element={<Authenticated><IdeasPage /></Authenticated>} />
    <Route path="/settings" element={<Authenticated><SettingsPage /></Authenticated>} />
    <Route path="/admin/*" element={<Authenticated admin><AdminPage /></Authenticated>} />
    <Route path="*" element={<NotFound />} />
  </Routes>;
}

export default function App() {
  return <AuthProvider><RealtimeProvider><AppRoutes /></RealtimeProvider></AuthProvider>;
}
