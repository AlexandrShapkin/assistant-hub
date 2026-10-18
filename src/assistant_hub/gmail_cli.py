"""Explicit opt-in Gmail metadata OAuth and one-shot read-only inbox synchronization.

No background collection, Gmail sending, archive, delete or Gmail body reads.
The two account identities and grant paths live only in a private 0600 file.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re

from .core.contracts import PollError
from .core.store import Store
from .gmail_metadata import GmailReader, account_for, sync_gmail
from .google_oauth import (
    GMAIL_SCOPES, authorize_with_browser, load_desktop_client,
    load_refresh_grant, read_private, refresh_access_token, _unique,
)

GRANT_NAME = re.compile(r"gmail-[a-z0-9-]{1,36}-grant\.json\Z")


def private_accounts(path):
    obj = json.loads(read_private(path, max_bytes=8192).decode("utf-8"),
                     object_pairs_hook=_unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(obj, dict) or set(obj) != {"accounts"} or not isinstance(obj["accounts"], list):
        raise ValueError("invalid private Gmail account selection")
    accounts = obj["accounts"]
    if not 1 <= len(accounts) <= 2:
        raise ValueError("Gmail supports one or two explicitly approved accounts")
    parsed = []
    for a in accounts:
        if not isinstance(a, dict) or set(a) != {"email", "grant"}:
            raise ValueError("invalid Gmail account record")
        account_for(a["email"])
        if not isinstance(a["grant"], str) or not GRANT_NAME.fullmatch(a["grant"]):
            raise ValueError("Gmail grant name must be a private basename")
        parsed.append((a["email"], Path(path).parent / a["grant"]))
    if (len({email.casefold() for email, _ in parsed}) != len(parsed) or
            len({str(p) for _, p in parsed}) != len(parsed)):
        raise ValueError("duplicate Gmail account identity or grant")
    return tuple(parsed)


def read_once(client_path, accounts_path, db_path):
    client = load_desktop_client(client_path)
    selected = private_accounts(accounts_path)
    db = Path(db_path)
    if not db.is_absolute() or not db.is_file():
        raise ValueError("existing absolute private SQLite database required")
    readers = []
    # Verify the ownership of ALL requested grants before writing any account.
    for expected, grant_path in selected:
        load_refresh_grant(grant_path, client["client_id"], scopes=GMAIL_SCOPES)
        token = refresh_access_token(client, grant_path, scopes=GMAIL_SCOPES)
        reader = GmailReader(token)
        identity, _ = reader.profile()
        if identity.casefold() != expected.casefold():
            raise ValueError("a Gmail grant does not match the explicit account selection")
        readers.append((expected, reader))
    results = []
    for expected, reader in readers:
        with closing(Store(db)) as store:
            results.append(sync_gmail(store, reader, expected))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private, read-only Gmail metadata integration")
    parser.add_argument("--client", required=True, help="private Desktop OAuth client JSON")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--authorize", action="store_true", help="authorize one account locally")
    group.add_argument("--sync", action="store_true", help="one bounded metadata sync pass")
    parser.add_argument("--tokens", help="private, new grant file for --authorize")
    parser.add_argument("--accounts", help="private two-account allowlist JSON")
    parser.add_argument("--db", help="existing private SQLite database")
    args = parser.parse_args(argv)
    if args.authorize and not args.tokens:
        parser.error("--authorize needs --tokens")
    if args.sync and (not args.accounts or not args.db):
        parser.error("--sync needs --accounts and --db")
    try:
        client = load_desktop_client(args.client)
        if args.authorize:
            if Path(args.tokens).exists():
                raise ValueError("grant already exists; no silent reauthorization")
            authorize_with_browser(client, args.tokens, scopes=GMAIL_SCOPES)
            print("Read-only Gmail metadata consent saved privately; no messages sent or changed")
        else:
            for _, counts in read_once(args.client, args.accounts, args.db):
                print("Private Gmail metadata read:", counts)
        return 0
    except (ValueError, OSError, TimeoutError, PollError, json.JSONDecodeError):
        parser.exit(1, "Private Gmail metadata read/authorization failed; no Gmail mutation performed.\n")


if __name__ == "__main__":
    raise SystemExit(main())
