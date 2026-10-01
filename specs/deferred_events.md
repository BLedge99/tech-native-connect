# DEFERRED — Events and meetups

> **STATUS: NOT FOR THE DEMO. DO NOT BUILD.**
>
> This file is a complete spec so the feature can be added later **without
> touching any required code**. It is not a task on the roadmap. See
> [`roadmap.md`](../roadmap.md) §Cut line and [`PRD.md`](../PRD.md) §Out of scope.
>
> Source: the brief's suggested additional features, "Events or meetups: post
> and join pitch nights, hack days or socials."

---

## Why it is deferred

The demo loop is: sign up → profile → matches → request → accept → message →
notification. Events touch none of those steps. They add four tables, three
endpoints' worth of CRUD, a date-picker UI and an RSVP state machine.

While the demo works without them, they are strictly additive: a new feature
that consumes the existing profile, notification and admin reference-data
layers. Nothing in specs 01–09 needs to know they exist.

## Dependency

Requires nothing new. It consumes:

- `users` and `profiles` ([03](03_profiles.md))
- `notifications` ([07](07_notifications.md)) — for RSVP and event notifications
- `get_current_admin` ([09](09_admin.md)) — if admin can create events

## Data model

### `events`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `organizer_id` | `uuid` FK → `users.id` | Who created it |
| `title` | `varchar(120)` | |
| `description` | `text` | Up to 2000 |
| `event_type` | enum | `pitch_night`, `hack_day`, `social`, `workshop`, `other` |
| `starts_at` | `timestamptz` | **With timezone.** Never naive |
| `ends_at` | `timestamptz` nullable | |
| `location` | `varchar(200)` nullable | Free text — "Room 2.14", "The Swan". Not geocoded |
| `capacity` | `integer` nullable | `NULL` = unlimited |
| `is_cancelled` | `boolean` | Default `false` |
| `created_at` | `timestamptz` | |

Indexes: `(starts_at)` for the chronological listing, `(organizer_id)`.

### `event_rsvps`

| Column | Type | Notes |
|---|---|---|
| `event_id` | `uuid` FK | Composite PK with `user_id` |
| `user_id` | `uuid` FK | |
| `created_at` | `timestamptz` | |

Composite PK again — one RSVP per person per event, enforced by the database
([08](08_project_ideas.md) §2 uses the same pattern).

`location` is **not** a `geography` column, a map provider, or an address
lookup. Bootcamp events happen in one building. Free text is correct.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/events` | session | Browse, paginated |
| `GET` | `/api/v1/events?upcoming_only=` | session | Default `true` |
| `GET` | `/api/v1/events/{id}` | session | One, with attendee count |
| `POST` | `/api/v1/events` | session + complete profile | Create |
| `PATCH` | `/api/v1/events/{id}` | organizer only | Edit |
| `DELETE` | `/api/v1/events/{id}` | organizer only | Cancel — soft, `is_cancelled` |
| `POST` | `/api/v1/events/{id}/rsvp` | session | Join |
| `DELETE` | `/api/v1/events/{id}/rsvp` | session | Leave |
| `GET` | `/api/v1/events/{id}/attendees` | session | Who is coming |

Sorting is `starts_at ASC`. Stable tiebreak on `id` for the same pagination
reason as everywhere else ([`00_conventions.md`](00_conventions.md) §5).

## Rules

| Rule | Enforcement |
|---|---|
| Only the organizer edits or cancels | `403 not_event_organizer` |
| A cancelled event accepts no new RSVPs | `409 event_cancelled` |
| A full event accepts no new RSVPs | `409 event_full` |
| Capacity race | **Row lock, or accept oversell.** See below |
| Cancelled events still show, marked | Filtered by `is_cancelled` in the UI, not deleted |
| RSVP and leave are idempotent | `POST` twice → `200`, `DELETE` twice → `204` |

### The capacity race

`SELECT COUNT(*) → if < capacity → INSERT` races. Two people RSVP simultaneously
for the last slot and both succeed.

**Correct fix:** `SELECT … FOR UPDATE` on the event row inside the transaction,
then re-count. **Acceptable fix for a bootcamp app:** let it oversell and show
"N going, capacity N" — nobody minds at this scale.

Pick one and write it in the ADR if you build this. Do not implement the racy
version.

## Notifications

Three new types on the existing enum ([07](07_notifications.md) §3):

| Type | Fires when | Recipient |
|---|---|---|
| `event_rsvp` | Someone RSVPs | Organizer |
| `event_cancelled` | Organiser cancels | Everyone who RSVP'd |
| `event_updated` | Time or location changes | Everyone who RSVP'd |

Same synchronous-insert rule: no queue, insert then push. `event_cancelled`
and `event_updated` batch over attendees — for a 40-person hack day that is 40
inserts in one request, acceptable at this scale, and worth a comment if it
grows.

Adding enum values means a migration. Nothing else in the notification system
needs to change.

## Frontend

| Route | Renders |
|---|---|
| `/events` | Chronological list, upcoming by default |
| `/events/:id` | Detail, RSVP button, attendee avatars |
| `/events/new` | Create form |

A date picker is the one new UI dependency this feature implies. Consider
`<input type="datetime-local">` first — native, no dependency, good enough.
Tailwind plus native inputs, consistent with the no-component-library rule.

Past events in a collapsed "Past events" section, greyed. Cancelled events
struck through with a clear label.

## Tests

### Unit

| Test | Asserts |
|---|---|
| `test_only_organizer_can_edit` | `403` |
| `test_cancelled_event_rejects_rsvp` | `409` |
| `test_full_event_rejects_rsvp` | `409 event_full` |
| `test_rsvp_is_idempotent` | `POST` twice → `200` |
| `test_leave_is_idempotent` | `DELETE` twice → `204` |
| `test_capacity_not_exceeded` | Or oversell, per the chosen rule |
| `test_cancellation_notifies_all_attendees` | One per attendee |

### Integration

| Test | Asserts |
|---|---|
| `test_events_require_session` | `401` |
| `test_create_requires_complete_profile` | `403` |
| `test_organizer_can_edit` | `200` |
| `test_other_user_cannot_edit` | `403` |
| `test_listing_sorts_chronologically` | |
| `test_upcoming_only_default` | |
| `test_cancelled_events_not_deleted` | Still listed, flagged |
| `test_rsvp_flow` | Count increments |
| `test_rsvp_creates_one_notification` | Organizer, once |

### E2E

Create an event → RSVP → organiser sees a notification → cancel → attendee sees
"cancelled" and cannot RSVP.

## Implementation notes

- **Soft cancel, never hard delete.** Attendees were notified about something
  that no longer exists otherwise, and their notification links 404.
- **Timestamps with timezone from the start.** Retrofitting `timestamptz` onto
  naive timestamps is a genuinely painful migration.
- **Reuse `idea_interests`' composite-PK pattern** for RSVPs. Do not invent a
  second approach.
- **This feature will not require changes to specs 01–09.** That is the test of
  whether the layering is right — if it does, something was built too tightly.