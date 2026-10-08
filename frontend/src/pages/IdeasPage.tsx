/** Project ideas board. specs/08 §5. */

import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ideas as ideasApi } from '../api/client'
import { ApiError } from '../api/client'
import type { Idea, IdeaCategory } from '../api/types'
import { Avatar, Button, EmptyState, ErrorState, Field, Spinner, inputClass } from '../components/ui'
import { useQuery } from '../hooks/useQuery'
import { useSession } from '../hooks/session'

const CATEGORIES: Array<{ value: IdeaCategory; label: string; blurb: string }> = [
  { value: 'find_problem', label: 'Find a problem', blurb: 'Research and validation' },
  { value: 'build_product', label: 'Build a product', blurb: 'Something working' },
  { value: 'design_brand', label: 'Design a brand', blurb: 'Identity and story' },
  { value: 'run_campaign', label: 'Run a campaign', blurb: 'Marketing and growth' },
  { value: 'other', label: 'Something else', blurb: 'Anything that fits' },
]

export function IdeasPage() {
  const [params, setParams] = useSearchParams()
  const [reloadKey, bumpReload] = useState(0)
  const { user } = useSession()
  const category = params.get('category') ?? ''
  const search = params.get('search') ?? ''
  const mine = params.get('mine') === 'true'

  const query = useQuery(
    () =>
      ideasApi.list({
        category: category || undefined,
        search: search || undefined,
        mine: mine || undefined,
        limit: 50,
      }),
    [category, search, mine, reloadKey],
  )

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const items = query.data?.items ?? []
  const filtered = Boolean(category || search)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Project ideas</h1>
        {user?.profile.role === 'business_developer' ? (
          <Link
            to="/ideas/new"
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white"
          >
            Post an idea
          </Link>
        ) : (
          <Link to="/matches" className="text-sm text-brand-600 underline">
            Browse people to build with
          </Link>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-4">
        {[{ value: '', label: 'All' }, ...CATEGORIES].map((c) => (
          <button
            key={c.value}
            onClick={() => setParam('category', c.value)}
            aria-pressed={category === c.value}
            className={`rounded-full px-3 py-1 text-sm ${
              category === c.value
                ? 'bg-brand-600 text-white'
                : 'border border-slate-300 text-slate-700'
            }`}
          >
            {c.label}
          </button>
        ))}
        <input
          defaultValue={search}
          onBlur={(e) => setParam('search', e.target.value)}
          placeholder="Search ideas…"
          aria-label="Search ideas"
          className="ml-auto rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => setParam('mine', e.target.checked ? 'true' : '')}
          />
          My ideas
        </label>
      </div>

      {query.loading && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      )}
      {query.error && <ErrorState message="Couldn't load ideas." onRetry={query.refetch} />}

      {!query.loading && !query.error && items.length === 0 && (
        <EmptyState
          title={
            filtered
              ? 'No ideas match these filters.'
              : mine
                ? "You haven't posted an idea yet."
                : 'No ideas yet. Be the first.'
          }
          action={
            filtered ? (
              <button onClick={() => setParams({}, { replace: true })} className="text-brand-600 underline">
                Clear filters
              </button>
            ) : user?.profile.role === 'business_developer' ? (
              <Link to="/ideas/new" className="text-brand-600 underline">
                Post an idea
              </Link>
            ) : undefined
          }
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((idea) => (
          <IdeaCard key={idea.id} idea={idea} onChange={() => bumpReload((n) => n + 1)} />
        ))}
      </div>
    </div>
  )
}

function IdeaCard({ idea, onChange }: { idea: Idea; onChange: () => void }) {
  const [busy, setBusy] = useState(false)

  const toggleInterest = async () => {
    setBusy(true)
    try {
      // Optimistic in both directions — expressing and withdrawing are
      // equal-and-opposite and a failed one just flips the button back.
      if (idea.viewer_has_interested) await ideasApi.withdrawInterest(idea.id)
      else await ideasApi.expressInterest(idea.id)
      onChange()
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="flex flex-col rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-semibold text-slate-900">
          <Link to={`/ideas/${idea.id}`} className="hover:underline">
            {idea.title}
          </Link>
        </h2>
        {!idea.is_open && (
          <span className="shrink-0 rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600">
            Closed
          </span>
        )}
      </div>

      <p className="mt-1 text-xs text-slate-500">
        {CATEGORIES.find((c) => c.value === idea.category)?.label}
        {idea.course ? ` · ${idea.course.name}` : ''}
      </p>

      <p className="mt-2 line-clamp-3 flex-1 text-sm text-slate-600">{idea.description}</p>

      {idea.skills_needed.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">
          Needs: {idea.skills_needed.join(' · ')}
        </p>
      )}

      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <Avatar user={idea.author} size={28} />
        <Link to={`/users/${idea.author.id}`} className="flex-1 text-sm text-slate-600 hover:underline">
          {idea.author.display_name}
        </Link>
        <span className="text-xs text-slate-400">{idea.interest_count} interested</span>
        <button
          onClick={toggleInterest}
          disabled={busy || !idea.is_open}
          className={`rounded-lg px-3 py-1.5 text-sm ${
            idea.viewer_has_interested
              ? 'bg-brand-100 text-brand-700'
              : 'border border-brand-300 text-brand-700 disabled:opacity-50'
          }`}
        >
          {idea.viewer_has_interested ? "I'm interested" : 'Interested'}
        </button>
      </div>
    </article>
  )
}

export function IdeaFormPage({ ideaId }: { ideaId?: string }) {
  const editing = Boolean(ideaId)
  const existing = useQuery(() => ideasApi.list({ mine: true, limit: 50 }), [ideaId], {
    skip: !editing,
  })
  const [form, setForm] = useState({
    title: '',
    description: '',
    category: 'build_product' as IdeaCategory,
    skills: [] as string[],
    skillDraft: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [banner, setBanner] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const found = editing
    ? (existing.data?.items ?? []).find((i) => i.id === ideaId)
    : undefined

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    setBanner(null)
    const body = {
      title: form.title,
      description: form.description,
      category: form.category,
      skills_needed: form.skills,
    }
    try {
      if (editing) await ideasApi.update(ideaId!, body)
      else await ideasApi.create(body)
      window.location.href = '/ideas'
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setErrors(err.fields)
        setBanner({ kind: 'error', text: 'Some fields need attention.' })
      } else {
        setBanner({ kind: 'error', text: err instanceof ApiError ? err.message : 'Could not save.' })
      }
    } finally {
      setBusy(false)
    }
  }

  const addSkill = () => {
    const value = form.skillDraft.trim()
    if (value && !form.skills.includes(value) && form.skills.length < 8) {
      setForm({ ...form, skills: [...form.skills, value], skillDraft: '' })
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">
        {editing ? 'Edit your idea' : 'Post a project idea'}
      </h1>

      {banner && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {banner.text}
        </p>
      )}

      <Field label="Title" error={errors.title}>
        <input
          className={inputClass}
          value={form.title}
          maxLength={120}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          required
        />
      </Field>

      <Field
        label="What is it?"
        hint={`${form.description.length}/2000 — at least 50 characters.`}
        error={errors.description}
      >
        <textarea
          className={`${inputClass} min-h-32`}
          value={form.description}
          maxLength={2000}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          required
        />
      </Field>

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-slate-700">Category</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={form.category === c.value}
              onClick={() => setForm({ ...form, category: c.value })}
              className={`rounded-lg border p-3 text-left ${
                form.category === c.value
                  ? 'border-brand-500 bg-brand-50'
                  : 'border-slate-300'
              }`}
            >
              <span className="block text-sm font-medium">{c.label}</span>
              <span className="block text-xs text-slate-500">{c.blurb}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <Field
        label="Skills needed"
        hint="Free text — a specific ask works better than a generic one. Enter to add."
      >
        <div className="rounded-lg border border-slate-300 p-2">
          <div className="mb-2 flex flex-wrap gap-2">
            {(editing && found ? found.skills_needed : form.skills).map((s) => (
              <span key={s} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-sm">
                {s}
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              className={inputClass}
              value={form.skillDraft}
              onChange={(e) => setForm({ ...form, skillDraft: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addSkill()
                }
              }}
              placeholder="e.g. Python, Figma"
            />
            <Button type="button" variant="secondary" onClick={addSkill}>
              Add
            </Button>
          </div>
        </div>
      </Field>

      <div className="flex gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? 'Saving…' : editing ? 'Save changes' : 'Post idea'}
        </Button>
        <Link to="/ideas" className="py-2 text-sm text-slate-600 underline">
          Cancel
        </Link>
      </div>
    </form>
  )
}

export function IdeaDetailPage({ ideaId }: { ideaId: string }) {
  const { user } = useSession()
  const [reloadKey, bumpReload] = useState(0)
  const query = useQuery(() => ideasApi.list({ open_only: false, limit: 50 }), [reloadKey])
  const idea = (query.data?.items ?? []).find((i) => i.id === ideaId)

  if (query.loading) return <Spinner />
  if (!idea) return <ErrorState message="That idea does not exist." onRetry={query.refetch} />

  const mine = idea.author.id === user?.id

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link to="/ideas" className="text-sm text-slate-500 underline">
        ← All ideas
      </Link>

      <div className="rounded-xl border border-slate-200 bg-white p-6">
        <h1 className="text-2xl font-bold text-slate-900">{idea.title}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {CATEGORIES.find((c) => c.value === idea.category)?.label} · posted by{' '}
          <Link to={`/users/${idea.author.id}`} className="underline">
            {idea.author.display_name}
          </Link>
          {' · '}
          {new Date(idea.created_at).toLocaleDateString()}
        </p>

        <p className="mt-4 whitespace-pre-wrap text-slate-700">{idea.description}</p>

        {idea.skills_needed.length > 0 && (
          <div className="mt-4">
            <h2 className="text-sm font-medium text-slate-500">Needs</h2>
            <div className="mt-1 flex flex-wrap gap-2">
              {idea.skills_needed.map((s) => (
                <span key={s} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6 flex items-center gap-3 border-t border-slate-100 pt-4">
          <span className="text-sm text-slate-500">{idea.interest_count} interested</span>
          <button
            onClick={async () => {
              if (idea.viewer_has_interested) await ideasApi.withdrawInterest(idea.id)
              else await ideasApi.expressInterest(idea.id)
              bumpReload((n) => n + 1)
            }}
            disabled={!idea.is_open || mine}
            className={`ml-auto rounded-lg px-4 py-2 text-sm ${
              idea.viewer_has_interested
                ? 'bg-brand-100 text-brand-700'
                : 'border border-brand-300 text-brand-700 disabled:opacity-50'
            }`}
          >
            {idea.viewer_has_interested ? "I'm interested" : 'Express interest'}
          </button>
        </div>

        {/* Author tools render only when the viewer is the author — the server
            decides, the client follows. */}
        {mine && (
          <div className="mt-4 flex gap-3 border-t border-slate-100 pt-4 text-sm">
            <Link to={`/ideas/${idea.id}/edit`} className="text-brand-600 underline">
              Edit
            </Link>
            <button
              onClick={async () => {
                if (!confirm('Delete this idea? This cannot be undone.')) return
                await ideasApi.remove(idea.id)
                window.location.href = '/ideas'
              }}
              className="text-red-600 underline"
            >
              Delete
            </button>
            <button
              onClick={async () => {
                await ideasApi.update(idea.id, { is_open: !idea.is_open })
                bumpReload((n) => n + 1)
              }}
              className="text-slate-600 underline"
            >
              {idea.is_open ? 'Mark closed' : 'Reopen'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}