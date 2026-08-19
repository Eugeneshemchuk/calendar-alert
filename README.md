# Calendar Alert — MVP

Calls your phone via Twilio when a Google Calendar event with `!important`
in the title is about to start. Runs as a GitHub Actions cron job every
5 minutes — no server to maintain.

## How it works

1. Every 5 min, a GitHub Actions workflow runs `calendar_alert.py`.
2. The script asks Google Calendar for events starting in the next 15 min.
3. Any event with `!important` (case-insensitive) in the title that hasn't
   already triggered a call gets one, via Twilio's Voice API — it reads
   the event title, start time, and description as TTS.
4. `state.json` tracks which events have already been called for, so you
   don't get called twice. The workflow commits this file back to the repo
   after every run.

## One-time setup

### 1. Google Calendar API access

1. Go to the [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Create a project (or use an existing one), enable the **Google Calendar API**.
3. Create an **OAuth 2.0 Client ID** of type **Desktop app**.
4. Download the credentials JSON, save it as `client_secret.json` in this
   folder (locally — never commit it).
5. Locally: `pip install google-auth-oauthlib` then `python get_refresh_token.py`.
6. This opens a browser, you authorize, and it prints your
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN`.
7. Delete `client_secret.json` afterward — it's not needed again.

### 2. Twilio

1. Create a [Twilio account](https://www.twilio.com/try-twilio), buy a phone number capable of voice calls.
2. Grab your **Account SID** and **Auth Token** from the console dashboard.
3. Note the Twilio number (`TWILIO_FROM_NUMBER`) and your own cell number
   (`ALERT_PHONE_NUMBER`), both in E.164 format, e.g. `+31612345678`.
4. Trial accounts can usually only call verified numbers — verify your own
   number in the Twilio console, or upgrade the account.

### 3. GitHub repo secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add all of:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `ALERT_PHONE_NUMBER`

### 4. Push this repo, enable Actions

Push this folder to a **private** GitHub repo (it touches your calendar and
makes phone calls — keep it private). The workflow starts running on its
own 5-minute schedule once pushed. You can also trigger a manual test run
from the **Actions** tab via "Run workflow" (the `workflow_dispatch` trigger).

## Using it

Add `!important` anywhere in an event title on your primary Google
Calendar, e.g.:

> `!important Client call — contract signing`

You'll get a phone call ~5–15 minutes before it starts (depending on when
the cron tick lands relative to the event time), reading the title and
description.

## Known limitations (fine for v1, worth knowing)

- **GitHub's cron scheduler is best-effort** — it can lag several minutes
  under load, especially at the top of the hour. The 15-min lookahead
  window gives buffer, but don't rely on this for anything with
  sub-5-minute precision.
- **Only checks your primary calendar.** Multi-calendar support is a v2 item.
- **No snooze/dismiss.** The call just plays the message twice and ends.
- **No retry if the call isn't answered.** Twilio will report a status but
  the script doesn't currently act on it.
- **State commits via git** — a slightly hacky persistence mechanism, but
  fine at 1 user / low frequency. Swap for a KV store (e.g. Upstash Redis)
  if this ever bugs you.

## Natural v2 ideas

- Snooze/dismiss by pressing a key during the call (Twilio `<Gather>`)
- Fallback to SMS or push (ntfy/Pushover) if the call isn't answered
- Multi-calendar support
- Smarter "important" detection (specific calendar, attendee-based, or an
  LLM call classifying the event)
