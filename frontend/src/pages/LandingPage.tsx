/** Public pitch page. Rendered for logged-out visitors. specs/01 §2.
 *  Static content, no backend dependency — a logged-out visitor has no session. */

import { Link } from 'react-router-dom'

export function LandingPage() {
  return (
    <div className="min-h-full">
      <header className="terminal-header border-b border-slate-200">
        <div className="terminal-topline" aria-hidden="true">
          <span>BOOTCAMP CONNECT <span aria-hidden="true">/</span> COHORT CONSOLE</span>
          <span><i /> NETWORK READY</span>
        </div>
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <span className="terminal-brand">
            <span className="terminal-brand-mark" aria-hidden="true">BC</span>
            Bootcamp Connect
          </span>
          <nav aria-label="Account" className="flex items-center gap-3 text-sm">
            <Link to="/login" className="terminal-nav-link">
              Log in
            </Link>
            <Link
              to="/register"
              className="rounded-sm border border-brand-500 bg-brand-600 px-4 py-2 font-semibold text-white shadow-[0_0_22px_rgba(213,154,44,0.12)] hover:bg-brand-700"
            >
              Sign up <span aria-hidden="true">↗</span>
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4">
        {/* 1. Hero. The one sentence is the most important thing on the page. */}
        <section className="grid items-center gap-12 py-16 sm:py-24 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="text-left">
            <p className="terminal-kicker mb-5">COHORT NETWORK <span className="text-slate-500">/</span> CONNECTED</p>
            <h1 className="terminal-cursor max-w-3xl text-4xl font-bold leading-tight tracking-tight text-slate-900 sm:text-6xl">
              Meet the other half of your bootcamp.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
              Bootcamp Connect introduces you to the software developers and business
              developers on your course who are looking for exactly what you do — and
              tells you why.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                to="/register"
                className="inline-flex items-center gap-3 rounded-sm border border-brand-500 bg-brand-600 px-5 py-3 font-semibold text-white shadow-[0_0_28px_rgba(213,154,44,0.12)] hover:-translate-y-0.5 hover:bg-brand-700"
              >
                Create your profile <span aria-hidden="true">→</span>
              </Link>
              <span className="text-xs text-slate-500">MATCH REASONS INCLUDED <span className="text-slate-400">·</span> BUILT FOR YOUR COHORT</span>
            </div>
            <div className="mt-12 flex flex-wrap gap-x-8 gap-y-3 border-t border-slate-200 pt-5 text-xs text-slate-500">
              <span><b className="text-brand-500">01</b> / FIND YOUR MATCH</span>
              <span><b className="text-brand-500">02</b> / BOTH SAY YES</span>
              <span><b className="text-brand-500">03</b> / BUILD TOGETHER</span>
            </div>
          </div>

          <div className="terminal-window mx-auto w-full max-w-xl">
            <div className="terminal-window-bar justify-between">
              <span>COHORT OVERVIEW</span>
              <span className="!text-brand-500">DEMO MODE</span>
            </div>
            <div className="space-y-5 p-5 sm:p-7">
              <div className="flex items-center justify-between gap-4 text-xs">
                <span className="text-slate-500">YOUR BOOTCAMP NETWORK</span>
                <span className="rounded-sm border border-brand-300/40 bg-brand-50 px-2 py-1 text-brand-500">● READY</span>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-4 sm:p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs tracking-[0.12em] text-slate-500">SUGGESTED CONNECTION <span className="text-brand-500">/ 01</span></p>
                    <h2 className="mt-2 text-lg font-semibold text-slate-900">A useful overlap.</h2>
                  </div>
                  <span className="rounded-sm border border-brand-300/40 bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-500">STRONG FIT</span>
                </div>
                <div className="my-4 h-px bg-slate-200" />
                <p className="text-sm leading-6 text-slate-600">
                  You bring the product thinking. They bring the Python and API skills.
                  Both are looking for a small team project.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {['shared goal', 'Python', 'product strategy'].map((tag) => (
                    <span key={tag} className="rounded border border-slate-300 bg-slate-100 px-2 py-1 text-[0.68rem] text-slate-600">{tag}</span>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-[0.66rem]">
                {[
                  ['01', 'PROFILE'],
                  ['02', 'MATCHES'],
                  ['03', 'PROJECTS'],
                ].map(([n, label], i) => (
                  <div key={n} className="rounded-sm border border-slate-200 bg-slate-50/40 px-2 py-3">
                    <span className={i === 1 ? 'text-brand-500' : 'text-slate-500'}>{n}</span>
                    <span className="ml-2 text-slate-600">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* 2. The problem */}
        <section className="border-t border-slate-200 py-16 sm:py-20">
          <p className="terminal-kicker">// THE GAP</p>
          <h2 className="mt-3 text-2xl font-semibold text-slate-900">Two groups, one course, no introductions</h2>
          <p className="mt-3 max-w-2xl leading-7 text-slate-600">
            Developers want a business partner who can sell what they build. Business
            developers want someone who can build the thing they keep describing.
            Neither group has a way to find the other, so introductions happen by
            luck, in the corridors.
          </p>
        </section>

        {/* 3. How it works — maps exactly onto the demo loop */}
        <section className="border-t border-slate-200 py-16 sm:py-20">
          <p className="terminal-kicker">// THREE STEPS</p>
          <h2 className="mt-3 text-2xl font-semibold text-slate-900">How it works</h2>
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
              <li key={step.n} className="rounded-lg border border-slate-200 bg-white/70 p-5 transition duration-200 hover:-translate-y-1 hover:border-brand-300/60">
                <span className="flex h-9 w-9 items-center justify-center rounded border border-brand-300/40 bg-brand-50 font-semibold text-brand-500">
                  0{step.n}
                </span>
                <h3 className="mt-3 font-semibold text-slate-900">{step.t}</h3>
                <p className="mt-1 text-sm text-slate-600">{step.d}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* 4. Who it is for */}
        <section className="border-t border-slate-200 py-16 sm:py-20">
          <p className="terminal-kicker">// YOUR COHORT</p>
          <h2 className="mt-3 text-2xl font-semibold text-slate-900">Built for the two halves of a cohort</h2>
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white/70 p-5 transition duration-200 hover:border-brand-300/60">
              <h3 className="font-semibold text-slate-900">Software developers</h3>
              <p className="mt-1 text-sm text-slate-600">
                List what you can build and find the business developer with the
                problem that needs it.
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white/70 p-5 transition duration-200 hover:border-brand-300/60">
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
          <p className="terminal-kicker">// YOUR NEXT BUILD STARTS HERE</p>
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
