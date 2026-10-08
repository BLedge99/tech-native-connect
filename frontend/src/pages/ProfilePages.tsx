/** Profile view and edit. specs/03 §9.
 *
 * The edit form shows profile_complete state live, because the gate is the first
 * thing a new user hits. A progress hint beats a 403 after the fact. */

import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, users as usersApi } from '../api/client'
import type { Course, Me, Ref, UserRole } from '../api/types'
import { Avatar, Button, Field, RoleBadge, inputClass } from '../components/ui'
import { useSession } from '../hooks/session'
import { useQuery } from '../hooks/useQuery'

export function ProfilePage() {
  const { user } = useSession()
  if (!user) return null
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Your profile</h1>
      <div className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="flex items-center gap-4">
          <Avatar
            user={{
              id: user.id,
              display_name: user.display_name,
              has_photo: user.profile.has_photo,
              photo_url: user.profile.photo_url,
            }}
            size={72}
          />
          <div>
            <h2 className="text-xl font-semibold">{user.display_name}</h2>
            <div className="mt-1 flex items-center gap-2 text-sm text-slate-500">
              <RoleBadge role={user.profile.role} />
              {user.profile.course && <span>{user.profile.course.name}</span>}
            </div>
            {!user.profile.profile_complete && (
              <Linkish href="/profile/edit" text="Complete your profile" />
            )}
          </div>
        </div>

        <dl className="mt-6 space-y-4 text-sm">
          <Row label="Bio">{user.profile.bio || <span className="text-slate-400">Not added</span>}</Row>
          <Row label="Looking for">
            {user.profile.looking_for || <span className="text-slate-400">Not added</span>}
          </Row>
          <Row label="Skills">
            {user.profile.skills.length > 0 ? (
              <Chips items={user.profile.skills.map((s) => s.name)} />
            ) : (
              <span className="text-slate-400">None yet</span>
            )}
          </Row>
          <Row label="Interests">
            {user.profile.interests.length > 0 ? (
              <Chips items={user.profile.interests.map((i) => i.name)} />
            ) : (
              <span className="text-slate-400">None yet</span>
            )}
          </Row>
        </dl>

        <div className="mt-6 flex gap-3">
          <Linkish href="/profile/edit" text="Edit profile" primary />
          <a href={usersApi.photoUrl(user.id)} target="_blank" rel="noreferrer" className="text-sm underline">
            View photo
          </a>
        </div>
      </div>
    </div>
  )
}

const ROLES: Array<{ value: UserRole; label: string; blurb: string }> = [
  {
    value: 'software_developer',
    label: 'Software developer',
    blurb: 'You build things.',
  },
  {
    value: 'business_developer',
    label: 'Business developer',
    blurb: 'You find customers and problems worth solving.',
  },
]

export function ProfileEditPage() {
  const { user, setUser } = useSession()
  const [params] = useSearchParams()
  const [form, setForm] = useState({
    bio: user?.profile.bio ?? '',
    role: (user?.profile.role ?? '') as UserRole | '',
    course_id: user?.profile.course?.id ?? '',
    looking_for: user?.profile.looking_for ?? '',
  })
  const [skills, setSkills] = useState<Ref[]>(user?.profile.skills ?? [])
  const [interests, setInterests] = useState<Ref[]>(user?.profile.interests ?? [])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [banner, setBanner] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const skillsQuery = useQuery(() => usersApi.skills(), [])
  const interestsQuery = useQuery(() => usersApi.interests(), [])
  const coursesQuery = useQuery(() => usersApi.courses(), [])

  const focus = params.get('focus')

  useEffect(() => {
    if (!focus) return
    const el = document.getElementById(`section-${focus}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('ring-2', 'ring-brand-500', 'rounded-xl')
    }
  }, [focus])

  // Live gate preview: mirrors the backend rule but never replaces it.
  const willComplete = Boolean(form.role) && skills.length > 0
  const currentlyComplete = user?.profile.profile_complete ?? false

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    setBanner(null)
    try {
      const me: Me = await usersApi.updateMe({
        bio: form.bio || null,
        role: form.role || null,
        course_id: form.course_id || null,
        looking_for: form.looking_for || null,
        skill_ids: skills.map((s) => s.id),
        interest_ids: interests.map((i) => i.id),
      })
      setUser(me)
      setBanner({
        kind: 'ok',
        text: me.profile.profile_complete
          ? 'Saved. Matching is unlocked.'
          : 'Saved. Add a role and one skill to unlock matching.',
      })
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setErrors(err.fields)
        setBanner({ kind: 'error', text: 'Some fields need attention.' })
      } else {
        setBanner({ kind: 'error', text: 'Could not save. Try again.' })
      }
    } finally {
      setBusy(false)
    }
  }

  const uploadPhoto = async (file: File) => {
    try {
      await usersApi.uploadPhoto(file)
      const me = await usersApi.me()
      setUser(me)
      setBanner({ kind: 'ok', text: 'Photo updated.' })
    } catch (err) {
      setBanner({
        kind: 'error',
        text: err instanceof ApiError ? err.message : 'Upload failed.',
      })
    }
  }

  const courses = (coursesQuery.data ?? []) as Course[]

  return (
    <form onSubmit={save} className="space-y-8">
      <h1 className="text-2xl font-bold text-slate-900">Edit profile</h1>

      {banner && (
        <p
          role="status"
          className={`rounded-lg p-3 text-sm ${
            banner.kind === 'ok' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-700'
          }`}
        >
          {banner.text}
        </p>
      )}

      <div
        className={`rounded-lg p-3 text-sm ${
          willComplete
            ? 'bg-green-50 text-green-800'
            : 'bg-amber-50 text-amber-800'
        }`}
      >
        {willComplete
          ? 'Your profile is complete — matching is unlocked.'
          : currentlyComplete
            ? 'Careful: removing your role or last skill will lock matching again.'
            : 'Matching needs a role and at least one skill. Add both to unlock it.'}
      </div>

      <section id="section-photo" className="space-y-3">
        <h2 className="text-lg font-semibold">Photo</h2>
        <div className="flex items-center gap-4">
          <Avatar
            user={{
              id: user!.id,
              display_name: user!.display_name,
              has_photo: user!.profile.has_photo,
              photo_url: user!.profile.photo_url,
            }}
            size={64}
          />
          <div className="space-y-2 text-sm">
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void uploadPhoto(file)
              }}
              className="block text-sm"
            />
            <p className="text-xs text-slate-500">JPEG, PNG or WebP. Up to 2 MB.</p>
            {user?.profile.has_photo && (
              <button
                type="button"
                className="text-xs text-red-600 underline"
                onClick={async () => {
                  await usersApi.deletePhoto()
                  setUser(await usersApi.me())
                }}
              >
                Remove photo
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Role is a pair of cards, not a dropdown: it is a defining choice and
          should feel like one. */}
      <section id="section-role" className="space-y-3">
        <h2 className="text-lg font-semibold">Your role</h2>
        <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Role">
          {ROLES.map((role) => (
            <button
              key={role.value}
              type="button"
              role="radio"
              aria-checked={form.role === role.value}
              onClick={() => setForm({ ...form, role: role.value })}
              className={`rounded-xl border p-4 text-left ${
                form.role === role.value
                  ? 'border-brand-500 bg-brand-50'
                  : 'border-slate-300 hover:border-slate-400'
              }`}
            >
              <span className="block font-medium text-slate-900">{role.label}</span>
              <span className="mt-1 block text-sm text-slate-600">{role.blurb}</span>
            </button>
          ))}
        </div>
      </section>

      <section id="section-skills" className="space-y-3">
        <h2 className="text-lg font-semibold">Skills</h2>
        <p className="text-sm text-slate-600">At least one is required for matching.</p>
        <MultiSelect
          options={(skillsQuery.data ?? []) as Ref[]}
          selected={skills}
          onChange={setSkills}
          loading={skillsQuery.loading}
          label="Skills"
        />
        {errors.skill_ids && <p className="text-xs text-red-600">{errors.skill_ids}</p>}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Course</h2>
        <Field label="Course" hint="Optional.">
          <select
            className={inputClass}
            value={form.course_id}
            onChange={(e) => setForm({ ...form, course_id: e.target.value })}
          >
            <option value="">Not set</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
      </section>

      <section id="section-interests" className="space-y-3">
        <h2 className="text-lg font-semibold">Interests</h2>
        <MultiSelect
          options={(interestsQuery.data ?? []) as Ref[]}
          selected={interests}
          onChange={setInterests}
          loading={interestsQuery.loading}
          label="Interests"
        />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Bio</h2>
        <Field label="Bio" hint={`${form.bio.length}/500`} error={errors.bio}>
          <textarea
            className={`${inputClass} min-h-28`}
            value={form.bio}
            maxLength={500}
            onChange={(e) => setForm({ ...form, bio: e.target.value })}
          />
        </Field>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">What are you looking for?</h2>
        <Field
          label="Looking for"
          hint="Optional. Feeds the reasons people see on your matches."
          error={errors.looking_for}
        >
          <textarea
            className={`${inputClass} min-h-20`}
            value={form.looking_for}
            maxLength={300}
            onChange={(e) => setForm({ ...form, looking_for: e.target.value })}
          />
        </Field>
      </section>

      <Button type="submit" disabled={busy}>
        {busy ? 'Saving…' : 'Save profile'}
      </Button>
    </form>
  )
}

function MultiSelect({
  options,
  selected,
  onChange,
  loading,
  label,
}: {
  options: Ref[]
  selected: Ref[]
  onChange: (next: Ref[]) => void
  loading: boolean
  /** Distinguishes the two multi-selects. Two inputs with the same
   *  placeholder is an accessibility problem as well as a test problem: a
   *  screen-reader user cannot tell which list they are in. */
  label: string
}) {
  const toggle = (ref: Ref) => {
    onChange(
      selected.some((s) => s.id === ref.id)
        ? selected.filter((s) => s.id !== ref.id)
        : [...selected, ref],
    )
  }
  const [filter, setFilter] = useState('')
  const visible = useMemo(
    () =>
      options.filter((o) => o.name.toLowerCase().includes(filter.toLowerCase())).slice(0, 60),
    [options, filter],
  )

  return (
    <div>
      {selected.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {selected.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => toggle(s)}
              className="rounded-full bg-brand-100 px-3 py-1 text-sm text-brand-700"
            >
              {s.name} ×
            </button>
          ))}
        </div>
      )}
      <input
        className={inputClass}
        placeholder={`Search ${label.toLowerCase()}…`}
        aria-label={`Search ${label.toLowerCase()}`}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="mt-2 max-h-40 overflow-auto rounded-lg border border-slate-200 p-2">
        {loading && <p className="px-2 py-2 text-sm text-slate-400">Loading…</p>}
        {!loading && visible.length === 0 && (
          <p className="px-2 py-2 text-sm text-slate-400">Nothing found.</p>
        )}
        {visible.map((o) => (
          <label key={o.id} className="flex cursor-pointer items-center gap-2 px-2 py-1 text-sm hover:bg-slate-50">
            <input
              type="checkbox"
              checked={selected.some((s) => s.id === o.id)}
              onChange={() => toggle(o)}
            />
            {o.name}
          </label>
        ))}
      </div>
    </div>
  )
}

function Chips({ items }: { items: string[] }) {
  return (
    <span className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span key={item} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs">
          {item}
        </span>
      ))}
    </span>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3">
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="text-slate-900">{children}</dd>
    </div>
  )
}

function Linkish({ href, text, primary }: { href: string; text: string; primary?: boolean }) {
  return (
    <a
      href={href}
      className={
        primary
          ? 'mt-4 inline-block rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white'
          : 'mt-2 inline-block text-sm text-brand-600 underline'
      }
    >
      {text}
    </a>
  )
}