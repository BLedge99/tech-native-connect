#!/usr/bin/env node
/**
 * Fails the build if an end-to-end test mocks the network.
 *
 * `playwright.config.ts` states the policy in a comment:
 *
 *   "No network mocking. A test that mocks the network is not testing the demo,
 *    and the demo is the thing most likely to break."
 *
 * A comment is not a control. A regression suite whose whole value is that it
 * exercises the real server is worthless if someone reaches for `page.route`
 * to make a flaky test green, and that is exactly the shortcut that looks
 * reasonable at 11pm the night before a demo.
 *
 * What is forbidden, and why:
 *
 *   page.route / context.route   Intercepts the request. The response under
 *                                test stops coming from the backend.
 *   route.fulfill                Supplies a hand-written body. This is how a
 *                                test gets "passed by hardcoding a response".
 *   route.continue                Weaker, but still interception.
 *   context.setOffline           Turns the backend off.
 *
 * Run it in CI and before a release:
 *
 *   node scripts/check-no-mocking.mjs
 */

import { readdir, readFile } from 'node:fs/promises'
import { join, relative, extname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))

const DIRS = ['frontend/tests', 'frontend/tests-videos', 'frontend/tests-devtools']

const FORBIDDEN = [
  { pattern: /\bpage\s*\.\s*route\s*\(/, why: 'page.route() intercepts the request under test' },
  { pattern: /\bcontext\s*\.\s*route\s*\(/, why: 'context.route() intercepts the request under test' },
  { pattern: /\broute\s*\.\s*fulfill\s*\(/, why: 'route.fulfill() supplies a hand-written body' },
  { pattern: /\broute\s*\.\s*continue\s*\(/, why: 'route.continue() still intercepts the request' },
  { pattern: /\broute\s*\.\s*abort\s*\(/, why: 'route.abort() makes the network fail artificially' },
  { pattern: /\bcontext\s*\.\s*setOffline\s*\(/, why: 'setOffline() turns the backend off' },
  { pattern: /\bsetContent\s*\(/, why: 'setContent() replaces the app with fixture markup' },
]

const EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.mjs'])

/** Every source file under the given directories. */
async function* sourceFiles(dir) {
  let entries
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return
  }
  for (const entry of entries) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      yield* sourceFiles(full)
    } else if (EXTENSIONS.has(extname(entry.name))) {
      yield full
    }
  }
}

const violations = []

for (const dir of DIRS) {
  const absolute = join(ROOT, dir)
  for await (const file of sourceFiles(absolute)) {
    const source = await readFile(file, 'utf8')
    const lines = source.split('\n')
    lines.forEach((line, index) => {
      // Comments are allowed to mention the API. Only code counts.
      const trimmed = line.trim()
      if (trimmed.startsWith('*') || trimmed.startsWith('//') || trimmed.startsWith('/*')) {
        return
      }
      for (const { pattern, why } of FORBIDDEN) {
        if (pattern.test(line)) {
          violations.push({
            file: relative(ROOT, file).replace(/\\/g, '/'),
            line: index + 1,
            why,
            text: trimmed.slice(0, 100),
          })
        }
      }
    })
  }
}

if (violations.length === 0) {
  console.log(`[guard] no network mocking in ${DIRS.length} test directories`)
  process.exit(0)
}

console.error('[guard] network mocking found in the E2E suites.\n')
for (const violation of violations) {
  console.error(`  ${violation.file}:${violation.line}`)
  console.error(`    ${violation.text}`)
  console.error(`    -> ${violation.why}\n`)
}
console.error(
  'End-to-end tests must exercise the real backend. Assert against a real\n' +
    'response, a direct database read (see frontend/tests/db.ts), or the real\n' +
    'WebSocket object — not a fabricated one.',
)
process.exit(1)