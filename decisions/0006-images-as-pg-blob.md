# 0006 — Profile photos as Postgres blobs

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [03](../specs/03_profiles.md), [01](../specs/01_landing_page.md)

## Context

The brief lists profile photos as an essential feature. Every profile, match
card, thread header and notification row shows one, so photos are on the hot
path of the whole app.

The choice was between a local directory served by FastAPI, an object storage
service, and a column in the database.

## Decision

**Store the uploaded image in a `photos` table as `bytea`, keyed by `user_id`,
and serve it from a session-authenticated endpoint.**

- `content_type` and `byte_size` as columns; the image in `data`.
- **2 MB hard cap**, enforced at both the request and the column.
- Type **sniffed from the bytes**, not trusted from the header.
- Re-serving through an endpoint rather than a static directory, so the session
  cookie can be required.

## Rejected

| Option | Why it lost |
|---|---|
| **Local disk, served by FastAPI** | The closest competitor and arguably simpler. Rejected on deployment: it needs a volume in `docker-compose.yml`, a documented path, and separate backup handling — two things to forget that produce confusing failures. It also splits the story: uploads are files, deletes are `unlink` calls, and every delete path needs to remember the filesystem. A database row is deleted by the cascade. |
| **A public static directory** | **Unacceptable.** `/uploads/{uuid}.jpg` with no auth means anyone who guesses or scrapes a UUID sees every user's photo. Photos require a session ([03](../specs/03_profiles.md) §4). Do not do this. |
| **S3 / Cloudflare R2 / MinIO** | The right answer at scale. Rejected because it needs an account, credentials and a network call for every photo — and a demo on hotel wifi fails. It also breaks the "no third-party services" constraint. |
| **Base64 in a JSON column** | Rejected on arithmetic: base64 inflates by 33%, and a JSON column cannot be indexed or streamed. A 2 MB photo becomes 2.7 MB of string in every response that touches a profile. |
| **A data URI in the profile row** | Same 33% inflation, plus the profile response grows by megabytes and cannot be cached usefully. |
| **Storing a path in the profile row** | Same failure mode as the static directory — files outside the database with no transactional delete. |

## Consequences

**Cost, the main one: the database grows.** Every photo is 2 MB at worst,
comfortably under the `bytea` limit of 1 GB per field. Fifteen seeded demo users
at, say, 200 KB each is 3 MB — nothing. But it means **database backups include
photos**, and `bytea` values are read into memory on every query that selects
them. **The mitigation is in [03](../specs/03_profiles.md) §4: never select
`photos.data`.** Only the profile row is selected; the image is fetched from its
own endpoint. If a query ever does `select(Photo)`, a profile list loads every
image into memory.

**This is the one real risk in the decision**, and it is why the two-table split
(`profiles.photo_id` → `photos.id`) matters. It keeps `bytea` out of every
ordinary query.

**Second cost:** there is no CDN and no image resizing pipeline. Downscaling on
upload is specified ([03](../specs/03_profiles.md) §4) but a server-generated
thumbnail is not — that would need Pillow and a second endpoint. At cohort scale
with one photo per user, serving the original is fine.

**Third cost:** it is unusual, and a reviewer will ask. That is what this ADR is
for.

**Gained.** One backup story, one transaction, one delete path — `ON DELETE
CASCADE` removes the photo when the user is deleted
([deferred_privacy_settings](../specs/deferred_privacy_settings.md)). No volume
configuration, no orphaned files, no filesystem permissions, nothing to
configure in a container. And it moves to object storage cleanly if it ever needs
to: `photos.data` becomes a key, one endpoint rewrites, no schema or API change.

**Risk to watch.** Never trust `content_type` or the file extension. A client can
send a shell script labelled `image/png`. **Sniff the magic number**
([03](../specs/03_profiles.md) §4), because this decision puts user-uploaded bytes
inside the database where they are served back to browsers. Sniffing at upload
is the only control point.

**Also:** images are the least compressible thing in the schema. Do not add a
`fetch all profiles with photos` endpoint, and set `Cache-Control` and `ETag`
on the photo endpoint so repeat views are cheap.

## Related

- [0002](0002-postgres-not-sqlite.md) — `bytea` is one of the reasons Postgres is not optional
- [0003](0003-vite-not-nextjs.md) — same-origin photo URLs, no CORS or CDN config