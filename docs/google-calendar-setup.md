# Google Calendar integration: explicit owner setup (Issue #46)

**Current status:** the app has an opt-in Desktop OAuth command and a one-shot
read-only Google Calendar API reader. No real Google authorization was
performed for Assistant Hub; the ChatGPT Google connector has separate access.
Nothing is polling Google Calendar on ru0 by default.

## 1. Independent Google Cloud Desktop OAuth client

Follow Google's official Calendar Python quickstart:
https://developers.google.com/workspace/calendar/api/quickstart/python

Create your Google Cloud project, enable Calendar API, configure Google Auth
consent (include your account as a test user when needed), and create a
Desktop app OAuth client. Save its downloaded JSON outside the Git repository
on the ThinkPad. The private parent directory must be owned by the user,
mode 0700; the Desktop client JSON must have mode 0600.

    mkdir -p "$HOME/.local/share/assistant-hub-private"
    chmod 700 "$HOME/.local/share/assistant-hub-private"
    # Move downloaded Desktop OAuth JSON to:
    # ~/.local/share/assistant-hub-private/google-desktop-client.json
    chmod 600 "$HOME/.local/share/assistant-hub-private/google-desktop-client.json"

The JSON needs the "installed" object, not a web-app OAuth client.
Do not share the downloaded JSON, Google authorization codes or refresh tokens
in chat, GitHub, issues, screenshots or public files.

NOTE: Google External/Testing consent configurations may issue Calendar
refresh tokens that expire after only seven days. Reliable unattended refresh
will require a suitable Google OAuth publishing/verification status and
current policy compliance. No background sync is promised until verified.

## 2. Read-only browser consent, ThinkPad only

Run this locally on the ThinkPad, not over SSH to ru0:

    cd "$HOME/Projects/assistant-hub"
    PYTHONPATH=src python3 -m assistant_hub.google_oauth \
      --client "$HOME/.local/share/assistant-hub-private/google-desktop-client.json" \
      --tokens "$HOME/.local/share/assistant-hub-private/google-grant.json"

This temporarily listens on 127.0.0.1 with an ephemeral port, CSRF state
and S256 PKCE verifier. Open the printed link **on the same ThinkPad**,
review the two Google Calendar read-only permissions and approve only if
intended. The callback closes after completion or a five-minute timeout.
Only the refresh grant is retained on disk (mode 0600); access tokens and
authorization codes are not saved. There are no Google mutations.

To check the local client JSON WITHOUT opening the browser or contacting
Google, use the same command with --check.

To revoke access, use Google's Third-party app access management and then
securely remove grant files from both computers. Deleting local files alone
does not revoke Google's upstream consent.

## 3. Explicit calendar allowlist and one-shot read

After consent, list available calendars in the owner's terminal:

    PYTHONPATH=src python3 -m assistant_hub.google_calendar_api \
      --client "$HOME/.local/share/assistant-hub-private/google-desktop-client.json" \
      --tokens "$HOME/.local/share/assistant-hub-private/google-grant.json" --list

Keep calendar IDs/private event titles out of issue/PR logs. Create a separate
0600 owner-private JSON file named google-allowlist.json containing only
approved calendars, such as:

    {"calendars":[{"id":"primary","timezone":"Asia/Barnaul"}]}

Maximum eight calendars, with valid IANA timezones. A known-stale
university-group subscribed calendar must NOT be treated as fresh source data.

After explicit owner approval, transfer the OAuth client JSON, grant and
allowlist into the existing private directory on ru0 through the trusted
ThinkPad SSH transport, preserving 0600 permissions. From ru0, a one-shot
read-only synchronization command is:

    cd "$HOME/Projects/assistant-hub"
    PYTHONPATH=src python3 -m assistant_hub.google_calendar_api \
      --client "$HOME/.local/share/assistant-hub-private/google-desktop-client.json" \
      --tokens "$HOME/.local/share/assistant-hub-private/google-grant.json" \
      --allowlist "$HOME/.local/share/assistant-hub-private/google-allowlist.json" \
      --db "$HOME/.local/share/assistant-hub-private/hub.sqlite3" --sync

The API client uses only Google HTTPS GET endpoints with bearer authorization
headers, no redirects or ambient proxy. For each explicitly allowed calendar,
the reader fetches a full baseline and subsequent incremental updates and
cancellations with Google's nextSyncToken. Incomplete or invalid responses
cannot advance the private SQLite cursor. At most twelve pages / 1,500
events are accepted per calendar in one pass; larger calendars fail closed.
The selected Google calendar appears in the authenticated Hub inbox after
a successful sync; public pages and health checks do not reveal it.

No real Google account/transport has yet been tested from ru0. The app
does NOT install or enable any Google background timer at this phase.
A separate audited recurring job can be added only after consent, successful
live sync and a review of Google refresh-token lifetimes and quota handling.

## 4. University timetable publication remains separate

The existing Google university subscription contains obsolete data, not a
fresh source. The university's current weekly schedule must come from a
verified, publisher-permitted export/API or a manual current-week import.
Publishing to a chosen owner-writable Google calendar must require a separate
write-scope consent, dry-run and explicit approval. The current read-only
flow contains no methods to create, alter or delete Google events.
