/** Public pitch page. Rendered for logged-out visitors. specs/01 §2.
 *  Static content, no backend dependency — a logged-out visitor has no session. */

import { Link } from 'react-router-dom'

export function LandingPage() {
  return (
    <div className="min-h-full bg-white">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <span className="text-lg font-bold text-brand-700">Bootcamp Connect</span>
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

      <main className="mx-auto max-w-4xl px-4">
        {/* 1. Hero. The one sentence is the most important thing on the page. */}
        <section className="py-20 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            Meet the other half of your bootcamp.
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-600">
            Bootcamp Connect introduces you to the software developers and business
            developers on your course who are looking for exactly what you do — and
            tells you why.
          </p>
          <Link
            to="/register"
            className="mt-8 inline-block rounded-lg bg-brand-600 px-6 py-3 font-medium text-white hover:bg-brand-700"
          >
            Create your profile
          </Link>
        </section>

        {/* 2. The problem */}
        <section className="border-t border-slate-200 py-16">
          <h2 className="text-2xl font-semibold text-slate-900">Two groups, one course, no introductions</h2>
          <p className="mt-3 max-w-2xl text-slate-600">
            Developers want a business partner who can sell what they build. Business
            developers want someone who can build the thing they keep describing.
            Neither group has a way to find the other, so introductions happen by
            luck, in the corridors.
          </p>
        </section>

        {/* 3. How it works — maps exactly onto the demo loop */}
        <section className="border-t border-slate-200 py-16">
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
              <li key={step.n} className="rounded-xl border border-slate-200 p-5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 font-semibold text-white">
                  {step.n}
                </span>
                <h3 className="mt-3 font-semibold text-slate-900">{step.t}</h3>
                <p className="mt-1 text-sm text-slate-600">{step.d}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* 4. Who it is for */}
        <section className="border-t border-slate-200 py-16">
          <h2 className="text-2xl font-semibold text-slate-900">Built for the two halves of a cohort</h2>
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 p-5">
              <h3 className="font-semibold text-slate-900">Software developers</h3>
              <p className="mt-1 text-sm text-slate-600">
                List what you can build and find the business developer with the
                problem that needs it.
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 p-5">
              <h3 className="font-semibold text-slate-900">Business developers</h3>
              <p className="mt-1 text-sm text-slate-600">
                Post what you want to build and reach the developers who can build
                it.
              </p>
            </div>
          </div>
        </section>

        {/* 5. Call to action */}
        <section className="border-t border-slate-200 py-20 text-center">
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