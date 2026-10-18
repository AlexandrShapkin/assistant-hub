"""Synthetic-only verification for two-account Gmail metadata read-only integration."""
from contextlib import closing
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from assistant_hub.core.contracts import AuthenticationPollError, PermanentPollError, RateLimitPollError
from assistant_hub.core.store import Store
from assistant_hub.gmail_metadata import (
    BASE, SERVICE, GmailReader, HistoryExpired, MessageGone,
    account_for, get_json, message_event, sync_gmail,
)
from assistant_hub.gmail_cli import private_accounts
from assistant_hub.google_oauth import (
    GMAIL_SCOPES, SCOPES, authorized_tokens, load_refresh_grant,
    refresh_access_token, write_private,
)

TOKEN = "synthetic-gmail-metadata-bearer"
EMAIL_A = "first@example.invalid"
EMAIL_B = "second@example.invalid"
CLIENT = "1234567890123-fake.apps.googleusercontent.com"


def msg(ident, *, label_ids=("INBOX", "UNREAD"), subject="Synthetic letter", thread="thread1"):
    return {"id": ident, "threadId": thread, "labelIds": list(label_ids),
            "internalDate": "1792396800000",
            "payload": {"headers": [
                {"name": "From", "value": "Fictional <sender@example.invalid>"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 19 Oct 2026 00:00:00 +0000"},
            ]},
            "snippet": "SENSITIVE_BUT_UNRETAINED",
            "raw": "NEVER_INCLUDE_RAW_BODY",
            "textPlain": "NEVER_INCLUDE_CONTENT"}


class FakeInbox:
    def __init__(self, address):
        self.address = address
        self.initial = ["m1", "m2"]
        self.data = {"m1": msg("m1"), "m2": msg("m2", subject="Second")}
        self.cursor = "100"
        self.delta = ([], "101")
        self.expired = False

    def profile(self):
        return self.address, self.cursor

    def recent(self):
        return list(self.initial)

    def changed(self, previous):
        if self.expired:
            raise HistoryExpired()
        return self.delta

    def message(self, ident):
        if ident not in self.data:
            raise MessageGone()
        return self.data[ident]


class GmailTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        os.chmod(self.root, 0o700)
        self.db = self.root / "hub.sqlite3"

    def test_oauth_scope_is_separate_from_existing_calendar_authorization(self):
        response = {"token_type": "Bearer", "access_token": TOKEN,
                    "refresh_token": "synthetic-grant-for-metadata",
                    "scope": " ".join(GMAIL_SCOPES)}
        grant = authorized_tokens(response, CLIENT, scopes=GMAIL_SCOPES)
        self.assertNotIn("access_token", grant)
        self.assertEqual(grant["scopes"], list(GMAIL_SCOPES))
        file = self.root / "gmail-first-grant.json"
        write_private(file, json.dumps(grant).encode())
        self.assertEqual(load_refresh_grant(file, CLIENT, scopes=GMAIL_SCOPES), grant)
        with self.assertRaises(ValueError):
            load_refresh_grant(file, CLIENT)  # cannot use Gmail grant as Calendar
        with self.assertRaises(ValueError):
            authorized_tokens(response, CLIENT, scopes=SCOPES)
        with self.assertRaises(ValueError):
            authorized_tokens(response, CLIENT, scopes=("https://www.googleapis.com/auth/gmail.send",))
        client = {"client_id": CLIENT, "client_secret": None}
        self.assertEqual(refresh_access_token(client, file, scopes=GMAIL_SCOPES,
                         exchange=lambda _: {"token_type": "Bearer", "access_token": TOKEN,
                                             "scope": " ".join(GMAIL_SCOPES)}), TOKEN)

    def test_private_two_account_selection_and_symlink_rejection(self):
        file = self.root / "gmail-accounts.json"
        records = [{"email": EMAIL_A, "grant": "gmail-one-grant.json"},
                   {"email": EMAIL_B, "grant": "gmail-two-grant.json"}]
        write_private(file, json.dumps({"accounts": records}).encode())
        self.assertEqual(private_accounts(file), (
            (EMAIL_A, self.root / "gmail-one-grant.json"),
            (EMAIL_B, self.root / "gmail-two-grant.json")))
        for bad in (
            {"accounts": []},
            {"accounts": records + records[:1]},
            {"accounts": records * 1 + [records[0]]},
            {"accounts": [records[0], dict(records[1], grant="../escape")]},
            {"accounts": [records[0], dict(records[1], grant=records[0]["grant"])]},
            {"accounts": [records[0], dict(records[1], email=EMAIL_A)]},
            {"accounts": [dict(records[0], extra="bad")]},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                write_private(file, json.dumps(bad).encode())
                private_accounts(file)
        file.unlink()
        file.symlink_to(self.root / "external")
        with self.assertRaises(OSError):
            private_accounts(file)

    def test_two_accounts_are_isolated_with_stable_ids_and_without_bodies(self):
        a, b = FakeInbox(EMAIL_A), FakeInbox(EMAIL_B)
        with closing(Store(self.db)) as store:
            first_account, counts = sync_gmail(store, a, EMAIL_A)
            second_account, counts_b = sync_gmail(store, b, EMAIL_B)
            self.assertEqual(counts["added"], 2)
            self.assertEqual(counts_b["added"], 2)
            self.assertNotEqual(first_account, second_account)
            self.assertEqual(store.cursor(SERVICE, first_account), "100")
            self.assertEqual(len(store.inbox()), 4)
            self.assertNotIn("SENSITIVE_BUT_UNRETAINED", str(store.inbox()))
            self.assertNotIn("NEVER_INCLUDE_RAW_BODY", str(store.inbox()))
            self.assertNotIn(EMAIL_A, str(store.inbox()))
            self.assertEqual(store.inbox()[0]["body"], "")
            self.assertTrue(all(x["service_id"] == "gmail" for x in store.inbox()))
            first_id = message_event(msg("m1"), first_account)[1].external_id
            store.set_status(SERVICE, first_account, first_id, "done", "owner")
            a.data["m1"] = msg("m1", label_ids=("INBOX",), subject="Changed")
            a.data["m2"] = msg("m2", label_ids=())
            a.data["m3"] = msg("m3", subject="Third")
            a.delta = (["m1", "m2", "m3"], "110")
            a.cursor = "110"
            _, new = sync_gmail(store, a, EMAIL_A)
            self.assertEqual((new["added"], new["updated"], new["removed"]), (1, 1, 1))
            self.assertEqual(store.cursor(SERVICE, first_account), "110")
            self.assertEqual(len([x for x in store.inbox() if x["account_id"] == second_account]), 2)
            updated = next(x for x in store.inbox_with_status() if x["account_id"] == first_account and x["title"] == "Changed")
            self.assertEqual(updated["status"], "done")
            self.assertEqual(updated["attributes"]["unread"], "false")
            _, again = sync_gmail(store, a, EMAIL_A)
            self.assertEqual([again[k] for k in ("added", "updated", "removed")], [0, 0, 0])
            self.assertTrue(all(EMAIL_A not in str(x) for x in store.audit()))

    def test_failing_fetch_does_not_move_cursor_or_mutate_db(self):
        a = FakeInbox(EMAIL_A)
        with closing(Store(self.db)) as store:
            sync_gmail(store, a, EMAIL_A)
            previous = (store.inbox(), store.cursor(SERVICE, account_for(EMAIL_A)), store.audit())
            a.delta = (["m1", "m_invalid"], "130")
            a.data["m_invalid"] = dict(msg("m_invalid"), internalDate="invalid")
            with self.assertRaises(PermanentPollError):
                sync_gmail(store, a, EMAIL_A)
            self.assertEqual((store.inbox(), store.cursor(SERVICE, account_for(EMAIL_A)), store.audit()),
                             previous)
            with self.assertRaises(AuthenticationPollError):
                sync_gmail(store, a, EMAIL_B)
            self.assertIsNone(store.cursor(SERVICE, account_for(EMAIL_B)))

    def test_expired_history_rebases_only_recent_without_deleting_old_records(self):
        a = FakeInbox(EMAIL_A)
        with closing(Store(self.db)) as store:
            sync_gmail(store, a, EMAIL_A)
            a.initial = ["m3"]
            a.data["m3"] = msg("m3")
            a.cursor = "200"
            a.expired = True
            _, result = sync_gmail(store, a, EMAIL_A)
            self.assertTrue(result["rebased"])
            self.assertEqual(result["removed"], 0)
            self.assertEqual(result["added"], 1)
            self.assertEqual(len(store.inbox()), 3)
            self.assertEqual(store.cursor(SERVICE, account_for(EMAIL_A)), "200")

    def test_history_pagination_and_validation(self):
        observations = []
        def transport(url, token, **kwargs):
            observations.append((url, token, kwargs))
            args = parse_qs(urlsplit(url).query)
            if url.endswith("/profile"):
                return {"emailAddress": EMAIL_A, "historyId": "123"}
            if "/history?" in url:
                if "pageToken" not in args:
                    return {"history": [{"messagesAdded": [{"message": {"id": "abc"}}]}],
                            "nextPageToken": "other"}
                return {"history": [{"labelsRemoved": [{"message": {"id": "def"}}]}],
                        "historyId": "126"}
            if "/messages?" in url:
                return {"messages": [{"id": "abc"}], "nextPageToken": "next-page"}
            return msg("abc")
        reader = GmailReader(TOKEN, transport=transport)
        self.assertEqual(reader.profile(), (EMAIL_A, "123"))
        self.assertEqual(reader.recent(), ["abc"])
        self.assertEqual(reader.changed("123"), (["abc", "def"], "126"))
        self.assertEqual(message_event(reader.message("abc"), account_for(EMAIL_A))[1].body, "")
        self.assertTrue(all(token == TOKEN for _, token, _ in observations))
        self.assertTrue(all(TOKEN not in url for url, _, _ in observations))
        self.assertTrue(all(url.startswith(BASE) for url, _, _ in observations))
        queries = [parse_qs(urlsplit(url).query) for url, _, _ in observations]
        self.assertEqual(queries[-1]["format"], ["metadata"])
        self.assertEqual(queries[-1]["metadataHeaders"], ["From", "Subject", "Date"])
        self.assertNotIn("q", str(queries))
        fail = GmailReader(TOKEN, transport=lambda *_a, **_k: {
            "history": [{"messagesAdded": [{"message": {"id": "abc"}}]}],
            "nextPageToken": "same",
        })
        with self.assertRaises(PermanentPollError):
            fail.changed("1")
        malformed = GmailReader(TOKEN, transport=lambda *_a, **_k: {
            "historyId": "0", "history": [], "nextPageToken": None
        })
        with self.assertRaises(PermanentPollError):
            malformed.changed("100")

    def test_transport_get_only_token_in_header_and_error_categorization(self):
        class Response:
            status = 200
            class Headers:
                def get_content_type(self):
                    return "application/json"
            headers = Headers()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, _n):
                return b'{"emailAddress":"first@example.invalid","historyId":"123"}'
        class Opener:
            failure = None
            request = None
            def open(self, request, timeout):
                self.request = request
                if self.failure:
                    raise HTTPError(request.full_url, self.failure, "private upstream body", {}, None)
                return Response()
        fake = Opener()
        with patch("assistant_hub.gmail_metadata.build_opener", return_value=fake):
            self.assertEqual(get_json(BASE + "/profile", TOKEN)["historyId"], "123")
            self.assertEqual(fake.request.get_method(), "GET")
            self.assertEqual(fake.request.get_header("Authorization"), "Bearer " + TOKEN)
            self.assertNotIn(TOKEN, fake.request.full_url)
            for status, typ in [(401, AuthenticationPollError), (429, RateLimitPollError),
                                (404, HistoryExpired), (503, Exception)]:
                fake.failure = status
                with self.subTest(status=status), self.assertRaises(typ) as exc:
                    get_json(BASE + "/history", TOKEN, missing="history")
                self.assertNotIn("private upstream body", str(exc.exception))
        with self.assertRaises(ValueError):
            get_json("https://another-provider.example.invalid/profile", TOKEN)
        with self.assertRaises(ValueError):
            get_json(BASE + "/profile", "bad")


if __name__ == "__main__":
    unittest.main()
