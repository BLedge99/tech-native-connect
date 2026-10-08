/** Public pitch page. Rendered for logged-out visitors. specs/01 §2.
 *  Static content, no backend dependency — a logged-out visitor has no session. */

import { Link } from 'react-router-dom'

export function LandingPage() {
  return (
    <div className="min-h-full bg-transparent">
      <header className="app-header">
        <div className="app-header-inner mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <span className="app-brand text-lg font-bold text-brand-700">Bootcamp Connect</span>
          <nav aria-label="Account" className="flex items-center gap-4 text-sm">
            <Link to="/login" className="text-slate-600 hover:text-slate-900">
              Log in
            </Link>
            <Link
              to="/register"
              className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700"
            >
              Sign up
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4">
        {/* 1. Hero. The one sentence is the most important thing on the page. */}
        <section className="py-24 text-center">
          <span className="inline-flex rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-bold tracking-wide text-brand-700">FOR YOUR BOOTCAMP COHORT</span>
          <h1 className="mx-auto mt-5 max-w-3xl text-5xl font-bold tracking-tight text-slate-900 sm:text-6xl">
            Meet the other half of your bootcamp.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-slate-600">
            Bootcamp Connect introduces you to the software developers and business
            developers on your course who are looking for exactly what you do — and
            tells you why.
          </p>
          <Link
            to="/register"
            className="mt-8 inline-block rounded-xl bg-brand-600 px-6 py-3 font-medium text-white shadow-lg shadow-brand-600/20 transition hover:-translate-y-0.5 hover:bg-brand-700"
          >
            Create your profile
          </Link>
        </section>

        {/* 2. The problem */}
        <section className="rounded-3xl border border-brand-100 bg-white/75 px-7 py-12 shadow-sm sm:px-12">
          <h2 className="text-2xl font-semibold text-slate-900">Two groups, one course, no introductions</h2>
          <p className="mt-3 max-w-2xl text-slate-600">
            Developers want a business partner who can sell what they build. Business
            developers want someone who can build the thing they keep describing.
            Neither group has a way to find the other, so introductions happen by
            luck, in the corridors.
          </p>
        </section>

        {/* 3. How it works — maps exactly onto the demo loop */}
        <section className="py-20">
          <h2 className="text-2xl font-semibold text-slate-900">How it works</h2>
          <ol className="mt-6 grid gap-6 sm:grid-cols-3">
            {[
              {
                n: 1,
                t: 'Complete your profile',
                d: 'Add a role and the skills you have. Takes a minute.',
              },
              {
                n: 2,
                t: 'Get matched',
                d: 'See the people you overlap with, and why we picked them.',
              },
              {
                n: 3,
                t: 'Connect and talk',
                d: 'Send a request. Nothing opens until they say yes.',
              },
            ].map((step) => (
              <li key={step.n} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:border-brand-200 hover:shadow-md">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 font-semibold text-white shadow-sm">
                  {step.n}
                </span>
                <h3 className="mt-3 font-semibold text-slate-900">{step.t}</h3>
                <p className="mt-1 text-sm text-slate-600">{step.d}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* 4. Who it is for */}
        <section className="border-y border-slate-200 py-16">
          <h2 className="text-2xl font-semibold text-slate-900">Built for the two halves of a cohort</h2>
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white/80 p-6 shadow-sm">
              <h3 className="font-semibold text-slate-900">Software developers</h3>
              <p className="mt-1 text-sm text-slate-600">
                List what you can build and find the business developer with the
                problem that needs it.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white/80 p-6 shadow-sm">
              <h3 className="font-semibold text-slate-900">Business developers</h3>
              <p className="mt-1 text-sm text-slate-600">
                Post what you want to build and reach the developers who can build
                it.
              </p>
            </div>
          </div>
        </section>

        {/* 5. Call to action */}
        <section className="py-20 text-center">
          <h2 className="text-2xl font-semibold text-slate-900">Your course is already here</h2>
          <p className="mt-3 text-slate-600">Everyone is a few rows away.</p>
          <Link
            to="/register"
            className="mt-6 inline-block rounded-lg bg-brand-600 px-6 py-3 font-medium text-white hover:bg-brand-700"
          >
            Sign up
          </Link>
          <p className="mt-4 text-sm text-slate-500">
            Already have an account?{' '}
            <Link to="/login" className="text-brand-600 underline">
              Log in
            </Link>
          </p>
        </section>
      </main>
    </div>
  )
}
