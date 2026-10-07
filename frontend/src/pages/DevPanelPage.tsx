/** Dev panel — developer-only dashboard for accessing services and videos.
 *
 * Not part of the product specs. This is a development tool that gives
 * developers one page to reach every service in the stack.
 */

import { useState } from 'react'

interface Service {
  name: string
  description: string
  url: string
  icon: string
  category: 'app' | 'infra' | 'docs'
}

const SERVICES: Service[] = [
  {
    name: 'Main Site',
    description: 'The frontend app (Vite + React)',
    url: 'http://localhost:5173',
    icon: '🌐',
    category: 'app',
  },
  {
    name: 'API Docs',
    description: 'Swagger / OpenAPI documentation',
    url: 'http://localhost:8000/docs',
    icon: '📖',
    category: 'docs',
  },
  {
    name: 'Mailpit',
    description: 'Fake SMTP inbox — view emails sent by the app',
    url: 'http://localhost:8025',
    icon: '📧',
    category: 'infra',
  },
  {
    name: 'Database',
    description: 'Adminer — web GUI for Postgres',
    url: 'http://localhost:8080',
    icon: '🗄️',
    category: 'infra',
  },
  {
    name: 'Backend API',
    description: 'FastAPI server (health: /api/v1/health)',
    url: 'http://localhost:8000',
    icon: '⚙️',
    category: 'app',
  },
]

interface Video {
  title: string
  filename: string
  description: string
}

const VIDEOS: Video[] = [
  {
    title: 'Landing Page',
    filename: '01-landing-page-the-pitch-logged-out.mp4',
    description: 'The pitch page logged out',
  },
  {
    title: 'Registration & Login',
    filename: '02-registration-login-and-magic-link.mp4',
    description: 'Sign up, login, and magic link flow',
  },
  {
    title: 'Profile Building',
    filename: '03-profile-building-one-from-nothing.mp4',
    description: 'Creating a profile from scratch',
  },
  {
    title: 'Matching & Search',
    filename: '04-matching-and-search.mp4',
    description: 'Browsing matches and filtering',
  },
  {
    title: 'Connection Requests',
    filename: '05-connection-requests-two-windows-side-by-side.mp4',
    description: 'Sending and accepting connections (two windows)',
  },
  {
    title: 'Live Messaging',
    filename: '07-live-messaging-two-windows-side-by-side.mp4',
    description: 'Real-time chat between two users (two windows)',
  },
  {
    title: 'Notifications',
    filename: '08-notifications.mp4',
    description: 'Notification bell and real-time updates',
  },
  {
    title: 'Project Ideas',
    filename: '09-project-ideas-board.mp4',
    description: 'The project ideas board',
  },
  {
    title: 'Admin Screens',
    filename: '10-admin-screens.mp4',
    description: 'Admin dashboard and moderation',
  },
]

function ServiceCard({ service }: { service: Service }) {
  return (
    <a
      href={service.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-xl border border-slate-200 bg-white p-5 transition hover:border-brand-300 hover:shadow-md"
    >
      <div className="flex items-start gap-4">
        <span className="text-3xl" aria-hidden>
          {service.icon}
        </span>
        <div className="min-w-0">
          <h3 className="font-semibold text-slate-900">{service.name}</h3>
          <p className="mt-1 text-sm text-slate-600">{service.description}</p>
          <p className="mt-2 truncate text-xs text-slate-400">{service.url}</p>
        </div>
      </div>
    </a>
  )
}

function VideoCard({ video }: { video: Video }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <video
        controls
        preload="metadata"
        className="w-full bg-black"
        src={`/api/v1/dev/videos/${video.filename}`}
      >
        Your browser does not support the video tag.
      </video>
      <div className="p-4">
        <h3 className="font-semibold text-slate-900">{video.title}</h3>
        <p className="mt-1 text-sm text-slate-600">{video.description}</p>
      </div>
    </div>
  )
}

export function DevPanelPage() {
  const [tab, setTab] = useState<'services' | 'videos'>('services')

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-slate-900">Dev Panel</h1>
              <p className="text-sm text-slate-500">
                Developer tools — not part of the product
              </p>
            </div>
            <a
              href="/"
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              ← Back to app
            </a>
          </div>

          {/* Tabs */}
          <div className="mt-4 flex gap-1">
            <button
              onClick={() => setTab('services')}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                tab === 'services'
                  ? 'bg-brand-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              Services
            </button>
            <button
              onClick={() => setTab('videos')}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                tab === 'videos'
                  ? 'bg-brand-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              Videos
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-6xl px-4 py-6">
        {tab === 'services' && (
          <div className="space-y-6">
            {/* App services */}
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Application
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {SERVICES.filter((s) => s.category === 'app').map((s) => (
                  <ServiceCard key={s.name} service={s} />
                ))}
              </div>
            </section>

            {/* Infrastructure */}
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Infrastructure
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {SERVICES.filter((s) => s.category === 'infra').map((s) => (
                  <ServiceCard key={s.name} service={s} />
                ))}
              </div>
            </section>

            {/* Docs */}
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Documentation
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {SERVICES.filter((s) => s.category === 'docs').map((s) => (
                  <ServiceCard key={s.name} service={s} />
                ))}
              </div>
            </section>

            {/* Quick info */}
            <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
              <h2 className="font-semibold text-amber-900">Quick Info</h2>
              <div className="mt-3 grid gap-3 text-sm text-amber-800 sm:grid-cols-2">
                <div>
                  <strong>Demo logins:</strong>
                  <ul className="mt-1 list-inside list-disc">
                    <li>priya@example.com / demo-password-123</li>
                    <li>ben@bootcamp.example.com / bootcamp-dev-admin</li>
                  </ul>
                </div>
                <div>
                  <strong>Useful commands:</strong>
                  <ul className="mt-1 list-inside list-disc">
                    <li>docker compose logs -f</li>
                    <li>docker compose exec db psql -U bootcamp -d bootcamp_connect</li>
                  </ul>
                </div>
              </div>
            </section>
          </div>
        )}

        {tab === 'videos' && (
          <div>
            <p className="mb-4 text-sm text-slate-600">
              Evidence recordings for each feature spec. These are generated by
              Playwright and composited with ffmpeg.
            </p>
            <div className="grid gap-6 sm:grid-cols-2">
              {VIDEOS.map((v) => (
                <VideoCard key={v.filename} video={v} />
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
