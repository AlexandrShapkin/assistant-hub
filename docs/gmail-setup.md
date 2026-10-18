# Private Gmail metadata integration (Issue #4)

**Status:** opt-in, owner-invoked, read-only prototype. Synthetic tests pass.
The new code does not run in the default localhost service, public preview or
on a timer. No user's actual Gmail account has been enrolled or read through
Assistant Hub. ChatGPT's Gmail connection is separate from this app's OAuth
authorization and cannot supply its tokens.

## Permissions and data boundary

Only `https://www.googleapis.com/auth/gmail.metadata` is requested. It
supports listing inbox message IDs, Gmail history deltas, and selected message
headers. The adapter does **not** read message bodies, MIME attachments, raw
messages, snippets, or outgoing content, and has no Gmail sending, draft,
archive, mark-as-read, delete, or label mutation code.

The authenticated private SQLite database stores the subject and From header,
message timestamp, unread flag, hashed message/thread IDs and a stable hash of
the Gmail account identity. Headers are personal data, **not encrypted at
rest**. There is no retention or automatic cleanup policy yet. Do not sync
personal Gmail until you approve local retention and backup handling.

Initial enrollment samples up to the latest **75 inbox messages per account**.
It is not a complete archive of old email. Subsequent `historyId` deltas
refresh added, removed, and relabelled messages without storing bodies.
A 404 history cursor expiration triggers a bounded recent rebaseline, retaining
older local rows rather than incorrectly deleting them. No asynchronous
background job is created at this stage. Google API quota and scope
restrictions, including Google's restricted-scope verification rules and
External/Testing refresh-token expiry, must be reviewed before unattended use.

## Enroll accounts privately (not yet performed)

Use a local, trusted ThinkPad browser with a Desktop OAuth client, the same
private Google Cloud Desktop JSON already used for Google Calendar (if the
Gmail API is enabled for that project and consent includes Gmail metadata).
Do **not** copy Google authorization URLs, codes, tokens, email addresses,
or private JSON into chat or GitHub. Obtain consent separately per account.

For the first account:

```sh
cd ~/Projects/assistant-hub
PYTHONPATH=src python3 -m assistant_hub.gmail_cli \
  --client ~/.local/share/assistant-hub-private/google-desktop-client.json \
  --authorize \
  --tokens ~/.local/share/assistant-hub-private/gmail-one-grant.json
```

Run again for the second account, changing only `--tokens` to
`gmail-two-grant.json` and selecting the other Google login. Both grants are
owner-only 0600 files under the existing owner-only 0700 directory. Existing
grants are not silently overwritten.

Create `gmail-accounts.json` **outside the repository**, owned by the
local user, mode 0600, in the same private directory. Supply the *actual*
Google profile email corresponding to each separately granted account:

```json
{
  "accounts": [
    {"email": "first-account@example.invalid", "grant": "gmail-one-grant.json"},
    {"email": "second-account@example.invalid", "grant": "gmail-two-grant.json"}
  ]
}
```

The placeholder emails above are fictional. Maximum two records; the sync
rejects duplicate or mismatched accounts before writing any data. Do not use
shell history for OAuth codes or tokens.

After separately approving transfer of the Gmail metadata-only grants and
private allowlist to the service host, a manual, bounded read may be run
there (the database must already exist):

```sh
cd ~/Projects/assistant-hub
PYTHONPATH=src python3 -m assistant_hub.gmail_cli \
  --client ~/.local/share/assistant-hub-private/google-desktop-client.json \
  --accounts ~/.local/share/assistant-hub-private/gmail-accounts.json \
  --db ~/.local/share/assistant-hub-private/hub.sqlite3 --sync
```

Do **not** set a background timer until successful live validation,
documented handling of access expiry and quota, a personal-data retention
decision, and user approval for persistent collection.

## Failure and revocation

Failed API/authentication calls do not advance a Gmail history cursor. Each
account is isolated in the database. An invalid message or an incomplete
history page aborts the entire account transaction; transient/rate-limit
failures propagate for later manual retry. Outbound HTTP uses fixed Google
HTTPS endpoints, explicit bearer headers, TLS validation and no redirects or
ambient proxies. Audit entries contain counts and hashed account keys, never
message titles, raw IDs, codes or tokens.

Revoke the application in your Google Account third-party access settings
and delete the corresponding private grant to disconnect an account. Removing
only the local file does not revoke Google's server-side consent. Deleting
previously stored local metadata is a separate explicit data-removal action.
