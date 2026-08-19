"""
Polls Google Calendar for events starting soon whose title contains the
"!important" flag, and places a Twilio phone call for any that haven't
been alerted yet. Designed to run every 5 minutes via GitHub Actions cron.

State (which events have already triggered a call) is persisted to
state.json, which the GitHub Actions workflow commits back to the repo
after each run.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from twilio.rest import Client as TwilioClient

# ---- Config ----------------------------------------------------------

FLAG = "!important"           # substring to look for in the event title (case-insensitive)
LOOKAHEAD_MINUTES = 15         # how far ahead to look for upcoming events
STATE_FILE = Path(__file__).parent / "state.json"
STATE_RETENTION_HOURS = 48     # prune alerted entries older than this

# ---- Google Calendar ---------------------------------------------------

def get_calendar_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    creds.refresh(GoogleAuthRequest())
    return build("calendar", "v3", credentials=creds)


def get_upcoming_flagged_events(service):
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=LOOKAHEAD_MINUTES)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=window_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    flagged = [
        e for e in events
        if FLAG.lower() in e.get("summary", "").lower()
    ]
    return flagged


# ---- State (dedup so we don't call twice for the same event) ----------

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def prune_state(state):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STATE_RETENTION_HOURS)
    kept = {}
    for event_id, alerted_at_str in state.items():
        try:
            alerted_at = datetime.fromisoformat(alerted_at_str)
        except ValueError:
            continue
        if alerted_at > cutoff:
            kept[event_id] = alerted_at_str
    return kept


# ---- Twilio call --------------------------------------------------------

def make_alert_call(event):
    client = TwilioClient(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )

    title = event.get("summary", "Untitled event").replace(FLAG, "", 1).strip(" -:")
    description = event.get("description", "").strip()
    start = event["start"].get("dateTime", event["start"].get("date"))

    start_dt = datetime.fromisoformat(start)
    start_local_str = start_dt.strftime("%H:%M")

    message = f"Important calendar alert. {title}, starting at {start_local_str}."
    if description:
        # Keep it short for TTS; truncate long descriptions.
        message += f" Details: {description[:300]}"

    twiml = f"""
    <Response>
        <Say voice="alice">{escape_for_twiml(message)}</Say>
        <Pause length="1"/>
        <Say voice="alice">Repeating. {escape_for_twiml(message)}</Say>
    </Response>
    """

    call = client.calls.create(
        to=os.environ["ALERT_PHONE_NUMBER"],
        from_=os.environ["TWILIO_FROM_NUMBER"],
        twiml=twiml,
    )
    return call.sid


def escape_for_twiml(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---- Main ----------------------------------------------------------------

def main():
    service = get_calendar_service()
    flagged_events = get_upcoming_flagged_events(service)

    state = prune_state(load_state())
    now_iso = datetime.now(timezone.utc).isoformat()

    new_alerts = 0
    for event in flagged_events:
        event_id = event["id"]
        if event_id in state:
            continue  # already alerted for this event

        try:
            call_sid = make_alert_call(event)
            print(f"Called for event '{event.get('summary')}' -> Twilio SID {call_sid}")
            state[event_id] = now_iso
            new_alerts += 1
        except Exception as exc:
            # Don't let one failed call crash the whole run / block other events.
            print(f"Failed to alert for event '{event.get('summary')}': {exc}", file=sys.stderr)

    save_state(state)
    print(f"Checked {len(flagged_events)} flagged event(s) in window, sent {new_alerts} new alert(s).")


if __name__ == "__main__":
    main()
