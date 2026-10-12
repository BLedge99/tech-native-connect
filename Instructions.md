# Bootcamp Connect — User Guide

Bootcamp Connect helps software developers and business developers from the
same bootcamp cohort find people with complementary skills, share project ideas,
and collaborate. This guide explains how to start the demo and how to use each
part of the application.

## Contents

- [What you need](#what-you-need)
- [Start the application](#start-the-application)
- [Create an account and sign in](#create-an-account-and-sign-in)
- [Complete your profile](#complete-your-profile)
- [Use the main navigation](#use-the-main-navigation)
- [Find and filter matches](#find-and-filter-matches)
- [Send and manage connection requests](#send-and-manage-connection-requests)
- [Message a connection](#message-a-connection)
- [Read notifications](#read-notifications)
- [Share project ideas](#share-project-ideas)
- [Account settings](#account-settings)
- [Administrator tools](#administrator-tools)
- [Suggested demo walkthrough](#suggested-demo-walkthrough)
- [Troubleshooting](#troubleshooting)
- [Privacy and product rules](#privacy-and-product-rules)

## What you need

To use the running local demo, you need a current desktop or mobile browser and
the Bootcamp Connect frontend URL. When running locally with Docker Compose,
open:

- **App:** <http://localhost:5173>
- **API documentation:** <http://localhost:8000/docs>
- **Development email inbox (Mailpit):** <http://localhost:8025>

For developers running the project for the first time, Docker Desktop with
Docker Compose is the simplest option. The app uses PostgreSQL for persistent
data. Registration and profile data are stored in the local demo database; they
are not shared with a hosted production service.

## Start the application

From the repository root, copy `.env.example` to `.env`, then review the
development-only values before starting the services.

PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

macOS, Linux, or Git Bash:

```bash
cp .env.example .env
docker compose up --build
```

The first startup builds the backend and frontend images and starts PostgreSQL
and Mailpit. The backend applies database migrations before serving requests.
Once the services are running, visit <http://localhost:5173>.

To stop the services, press **Ctrl+C**, or run:

```bash
docker compose down
```

This stops the containers but keeps the database volume and its data. To
completely reset the local database and remove all local accounts, profiles,
messages, and ideas, run:

```bash
docker compose down -v
```

**Warning:** `down -v` permanently deletes the local database data. Do not use
it if you want to keep demo accounts or activity.

### Optional demo seed data

An administrator or developer can seed the reference lists (courses, skills,
and interests), five configured administrator accounts, and optional Sam and
Priya sample users:

```bash
docker compose exec backend python -m app.seed
```

Before seeding, configure `ADMIN_EMAILS` with the five team email addresses and
set a private `SEED_ADMIN_PASSWORD` in `.env`. Set `DEMO_SEED_PASSWORD` if you
want the optional demo users. The selected seed password is the password for
those demo accounts. Do not use a real personal password in a shared demo
environment or commit `.env` to source control.

The reference lists may be empty until seed data has been added. If you are
using the hosted/tutor-provided demo, ask its administrator for access rather
than attempting to seed its database.

## Create an account and sign in

### Register

1. Open the app and choose **Join your cohort** or **Create your profile**.
2. Enter your name, a valid email address, and a password.
3. Choose **Create account**. The app signs you in and opens your home page.
4. Complete your profile before trying to browse matches.

Names must be 2–80 characters. Passwords must be at least 8 characters. The
registration form reports invalid email addresses, duplicate accounts, and
other validation errors next to the relevant field or form.

### Sign in with a password

1. Choose **Sign in** from the landing page.
2. Enter the email and password used to register.
3. Select **Sign in**.

### Sign in with a magic link

1. On the sign-in page, choose **Sign in with a magic link**.
2. Enter the email address for your account and request a link.
3. In the local development setup, open Mailpit at <http://localhost:8025> and
   select the new email. Follow its one-time link.

Magic links expire after 15 minutes and can only be used once. In development,
the confirmation page may also provide a shortcut link. Do not share that link:
anyone who has it can sign in as the account that requested it.

### Sign out

Choose **Sign out** in the header. The session is removed and protected pages
will require you to sign in again.

## Complete your profile

Your profile is how cohort members learn what you can contribute. Open **Your
profile** from the header, then choose **Edit profile**.

You can provide:

- **About you:** a short bio (up to 500 characters).
- **Your role:** Software developer or Business developer.
- **Your course:** select a course if one is available.
- **What are you looking for?:** describe the skills or collaboration you want
  (up to 300 characters).
- **Skills:** select all relevant skills. At least one skill is required for
  matching.
- **Interests:** select topics you care about.
- **Profile photo:** upload a JPEG, PNG, or WebP image up to 2 MB. You can
  replace or remove your photo later.

Choose **Save profile** when you are done. A profile is complete for matching
when you have selected a role and at least one skill. A course, bio, interests,
and photo are useful but are not required for that gate. Until the required role
and skill are set, the home page explains what is missing and matching remains
locked.

The **Your profile** page is the read-only view of your profile. Other users
can open your public profile from a match or connection card. You can edit only
your own profile.

## Use the main navigation

After sign-in, the header provides these main areas:

| Navigation item | What it does |
| --- | --- |
| **Home** | Shows a greeting, suggested matches, recent activity, or your next profile-completion step. |
| **Matches** | Finds cohort members and lets you filter the results. |
| **Connections** | Shows requests you received, requests you sent, and accepted connections. |
| **Messages** | Opens existing conversation threads. |
| **Ideas** | Browse, search, and post project ideas. |
| **Updates** | Opens notifications and shows the unread count. |
| **Your name** | Opens your own profile. |
| **Admin** | Visible only to administrator accounts. |

The site works on narrow/mobile screens as well as desktop. If a page reports an
error, use its **Retry** control if present; a non-essential feed failing should
not prevent access to the rest of the app.

## Find and filter matches

1. Complete your profile with a role and at least one skill.
2. Open **Matches**.
3. Optionally narrow results by role, course, skill, or interest.
4. Review each match card. It includes the person's profile, a match score, and
   short reasons that explain the overlap.
5. Open the person's name to see their public profile, or select **Connect** to
   send a request.

Filters can be combined. If no one appears, clear or broaden the filters and
check that your role and skills are accurate. Results can change as cohort
members join and complete their profiles. A match is a suggestion, not an
existing connection.

## Send and manage connection requests

Selecting **Connect** sends a request to the other person. It does not open a
chat by itself.

Open **Connections** to use the three lists:

- **Received:** requests other people sent you. Choose **Accept** to connect,
  or **Decline** to reject the request.
- **Sent:** requests you have sent that are awaiting a response. Choose
  **Withdraw** if you no longer want the request to remain pending.
- **Connected:** requests both people accepted. The **Open messages** link
  takes you to the conversation.

Only the receiver can accept or decline an incoming request. Once accepted, the
connection becomes mutual and messaging is available to both people. Requests
cannot be accepted or declined more than once.

## Message a connection

You can open a conversation from an accepted connection or from **Messages**.
A chat thread is available only after both people have accepted the connection.
If a chat was opened from the connection before any messages were sent, it may
not appear in the conversation list until a message is sent.

To send a message:

1. Open the conversation.
2. Enter a message in **Your message**.
3. Choose **Send**.

Messages can contain up to 2,000 characters. When both people are online in the
conversation, new messages appear live without refreshing the page. The heading
shows **Live connection** when that conversation's WebSocket subscription is
ready. If it says **Joining conversation…** or **Reconnecting…**, wait briefly;
the app attempts to reconnect. Messages are saved so they can be viewed later
even if the other person was offline.

## Read notifications

The **Updates** link shows an unread badge. The notifications page can include
connection requests, new messages, and other cohort activity.

- Choose **Open** on an item to mark it read and follow its relevant page.
- Choose **Mark read** to clear just that notification.
- Choose **Mark all as read** to clear all unread notifications.

Opening a notification does not bypass permissions. For example, a message
notification can only take you to a conversation you are allowed to access.

## Share project ideas

Open **Ideas** to explore the cohort board. Search by words in a title or
description and filter by category. The **My ideas** filter shows your own
ideas, including closed ones.

To post an idea:

1. Choose **Post an idea**.
2. Add a title (up to 120 characters) and a description (50–2,000 characters).
3. Choose a category: Find a problem, Build a product, Design a brand, Run a
   campaign, or Other.
4. Optionally list skills needed, separated by commas.
5. Choose **Save idea**.

Other cohort members can select **I’m interested** on an open idea. Select
**Withdraw interest** to change your response. You can edit your own ideas and
close or reopen them. Other members cannot edit your post.

## Account settings

Open **Settings** if linked from your account. The current settings page shows
your account name and email address and links to profile editing. To change
profile details, use **Your profile → Edit profile**. Password change, account
deletion, data export, and privacy controls are not available in this demo.

## Administrator tools

Only accounts designated as administrators can open **Admin**. The demo
administrator accounts are configured by the team; ordinary registration does
not grant administrator access.

The Admin page contains:

- **Overview:** summary counts for cohort activity.
- **Users:** search accounts, deactivate or reactivate users, and grant
  administrator access where permitted.
- **Courses:** view, add, and rename course entries used in profiles.
- **Skills:** view, add, rename, or delete skill entries; a category can also
  be set when adding a skill.
- **Interests:** view, add, rename, or delete interest entries.
- **Audit:** review recorded administrator actions.

Administrator access is powerful. Use it only for legitimate cohort
administration. Deactivation prevents an account from continuing to use the
application; reactivation restores access. Avoid deleting reference entries
that people currently use unless you understand the effect on their profiles.

## Suggested demo walkthrough

For the complete collaboration path, use two separate browser profiles or
incognito windows so each participant has a distinct session:

1. Register **Person A** and **Person B** with different email addresses.
2. In both sessions, edit each profile: select different complementary roles
   and add at least one shared skill (for example, Python).
3. In Person A's session, open **Matches**, find Person B, and choose
   **Connect**.
4. In Person B's session, open **Connections → Received** and choose
   **Accept**.
5. In Person A's session, open **Connections → Connected**, then choose
   **Open messages**.
6. Send an opening message. It creates the conversation thread.
7. In Person B's session, open **Messages**, open the conversation, and reply.
   Demonstrate the reply appearing live in Person A's session.
8. Open **Updates** to show the notification generated by the message.
9. Optionally visit **Ideas** to post an idea and express interest from the
   second account.

If starting with a clean local database, seed reference data first; otherwise
there may be no course, skill, or interest options to select.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| The app does not load | Confirm Docker Desktop is running and `docker compose up --build` completed. Open <http://localhost:5173> again. |
| A page says it cannot load data | Check that the backend and database containers are running. Retry the page. For local development, API docs are at <http://localhost:8000/docs>. |
| Sign-in fails | Check the email and password. Passwords are case-sensitive. If this is a new local database, create a new account or configure and run the seed command. |
| A magic link does not arrive | In the local demo, check Mailpit at <http://localhost:8025>, not a real email inbox. The link expires after 15 minutes. |
| Matches are locked | Edit your profile and select both a role and at least one skill, then save. |
| There are no matches | Clear filters, confirm the other account has a complete profile, and ensure the accounts are using the same cohort/course data. |
| There are no course/skill/interest choices | Seed the local reference data with `docker compose exec backend python -m app.seed`. |
| Chat is unavailable | Confirm the connection is accepted by both people. A pending request does not grant message access. |
| Messages are not updating live | Wait for **Live connection** to appear. Keep both browser sessions open and check that the backend container is running. Saved messages can still be loaded from chat history. |
| An admin page shows an access error | Sign in to a configured administrator account. Registering a normal user does not make it an admin. |
| You want to start over | `docker compose down -v` removes all local database data; use it only if a full reset is intended. |

## Privacy and product rules

- Sign-in is required to access user-specific information.
- A connection request alone does not permit messaging; both people must accept.
- Matching requires a completed role-and-skill profile.
- Your private account information and profile editing are limited to you;
  designated administrators are the exception, and their access is audited.
- Profile photos accept JPEG, PNG, or WebP files up to 2 MB.
- Validate what you share in a profile, message, or project idea. This demo does
  not include the deferred block/report, moderation, export, or account-deletion
  features.
- This is a local/demo application, not a production service. Do not put
  sensitive personal information or real credentials into demo content.

