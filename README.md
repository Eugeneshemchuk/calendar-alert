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

1. Create a [Twilio account](https://www.twilio.com/try-twilio) and
   **upgrade it to a paid account** (add a payment method in the console).
   Trial accounts only allow calls to pre-verified numbers, and verification
   itself is restricted to your sign-up country — in practice this makes
   trial unworkable for alerting a number in a different country. Calls
   cost about a cent a minute, so paid is cheap.
2. Complete Twilio's compliance/KYC step: **Console → Trust Hub → Customer
   Profiles**. Paid accounts can't place calls until this is approved —
   budget a few minutes for identity verification.
3. Buy a phone number capable of voice calls (Console → Phone Numbers).
4. Grab your **Account SID** and **Auth Token** from the console dashboard.
5. Note the Twilio number you bought (`TWILIO_FROM_NUMBER`) and your own
   cell number (`ALERT_PHONE_NUMBER`), both in E.164 format, e.g.
   `+31612345678`.

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

## Testing & debugging

All commands assume you're in the repo folder. Commands that hit the Twilio
API read credentials straight out of `twillio_secrets` (local, gitignored —
see [One-time setup](#2-twilio)); adjust the `grep` lines if you keep them
somewhere else.

### 1. Trigger a manual workflow run

```
gh workflow run check-important-events.yml
```

Queues an out-of-schedule run of the whole pipeline (Calendar check → Twilio
call → commit `state.json`), same as clicking "Run workflow" in the Actions
tab. Use this after any code/secret change instead of waiting for the next
5-min cron tick.

### 2. Find the run and watch it live

```
gh run list --workflow=check-important-events.yml --limit 1 --json databaseId -q '.[0].databaseId'
gh run watch <run-id> --exit-status
```

The first command prints the numeric ID of the most recent run (grab it
right after step 1). `gh run watch` streams step-by-step progress
(Checkout → Install deps → Run alert check → Commit state) and exits
non-zero if the run fails — useful in scripts, not just for reading.

### 3. Read the actual script output (the important one)

```
gh run view <run-id> --log | grep -i "flagged\|failed to alert\|Called for event"
```

`gh run watch` only tells you whether steps *ran*, not whether the alert
logic *worked*. This greps the log for the three lines `calendar_alert.py`
actually prints: how many `!important` events it found in the 15-min
window, and whether each call succeeded (`Called for event ... -> Twilio SID
...`) or failed (`Failed to alert for event ...: <reason>`). Read this after
every test run — a green run in step 2 just means no Python exception,
not that a call went out.

### 4. Check what kind of Twilio account you have

```
SID=$(grep ACCOUNT_SID twillio_secrets | cut -d= -f2)
TOKEN=$(grep AUTH_TOKEN twillio_secrets | cut -d= -f2)
curl -s -u "$SID:$TOKEN" "https://api.twilio.com/2010-04-01/Accounts/$SID.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('type:', d['type']); print('status:', d['status'])"
```

`type` is `Trial` or `Full`. Trial accounts have real restrictions (see
below) that produce cryptic 400 errors — check this first whenever a call
fails with "trial accounts have limited parameter access".

### 5. List phone numbers you actually own

```
curl -s -u "$SID:$TOKEN" "https://api.twilio.com/2010-04-01/Accounts/$SID/IncomingPhoneNumbers.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(n['phone_number']) for n in d['incoming_phone_numbers']]"
```

`TWILIO_FROM_NUMBER` must be a number this list contains — it's what you're
allowed to place outbound calls *from*. An empty list means you haven't
claimed/bought a Twilio number yet, which will fail every call regardless
of anything else being correct.

### 6. List verified caller IDs (trial accounts only)

```
curl -s -u "$SID:$TOKEN" "https://api.twilio.com/2010-04-01/Accounts/$SID/OutgoingCallerIds.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(n['phone_number']) for n in d['outgoing_caller_ids']]"
```

On a trial account, `ALERT_PHONE_NUMBER` (the number you're calling *to*)
generally needs to appear here — add it via Console → Phone Numbers →
Verified Caller IDs if it's missing. Not needed on a paid account.

### 7. Check recent call attempts and their error codes

```
curl -s -u "$SID:$TOKEN" "https://api.twilio.com/2010-04-01/Accounts/$SID/Calls.json?PageSize=10" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for c in d['calls']:
    print(c['date_created'], '|', c['from'], '->', c['to'], '|', c['status'], '| error:', c.get('error_code'), c.get('error_message'))
"
```

Shows Twilio's own call log — includes calls made from the console *and*
from the script. Useful to confirm a From/To pair works at all (e.g. via a
manual test call in the console) before suspecting the script's TwiML.
Note: a call that gets rejected at the REST API level (a 400, before Twilio
even attempts to dial) won't show up here at all — only calls that were
accepted for dialing do.

### 8. Reproduce a failing call directly (bypass the script/workflow)

```
FROM=$(grep TWILIO_FROM_NUMBER twillio_secrets | cut -d= -f2)
TO=$(grep ALERT_PHONE_NUMBER twillio_secrets | cut -d= -f2)
TWIML='<Response><Say voice="alice">Test message.</Say></Response>'

curl -s -u "$SID:$TOKEN" -X POST "https://api.twilio.com/2010-04-01/Accounts/$SID/Calls.json" \
  --data-urlencode "To=$TO" \
  --data-urlencode "From=$FROM" \
  --data-urlencode "Twiml=$TWIML"
```

**This places a real phone call — only run it when you intend to.** Isolates
whether a failure is caused by the TwiML content/voice vs. something about
the From/To pair or account state, without waiting on a GitHub Actions run
or burning a `!important` calendar event to trigger one.

## Natural v2 ideas

- Snooze/dismiss by pressing a key during the call (Twilio `<Gather>`)
- Fallback to SMS or push (ntfy/Pushover) if the call isn't answered
- Multi-calendar support
- Smarter "important" detection (specific calendar, attendee-based, or an
  LLM call classifying the event)
