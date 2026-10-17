"""Offline conformance examples. Add fixture factories to exercise another adapter."""
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from assistant_hub.core.contracts import (
    ActionIntent, AuthenticationPollError, Capability, Manifest, PermanentPollError, PollResult,
    RateLimitPollError, TransientPollError,
)
from assistant_hub.core.conformance import validate_poll_result
from assistant_hub.core.demo import BulletinAdapter, DemoAdapter
from assistant_hub.core.hub import Hub
from assistant_hub.core.registry import Binding, Registry
from assistant_hub.core.store import Store


def assert_read_conformance(case, factory, expected_count, pages):
    """Reusable deterministic fixture runner; factory must return a fresh fake."""
    adapter = factory()
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / 'fixture.db')
        try:
            registry = Registry()
            registry.enable(adapter, tuple(Binding(a) for a in adapter.accounts))
            hub = Hub(registry, store)
            for account in adapter.accounts:
                cursor = None
                for _ in range(pages):
                    result = adapter.poll(account, cursor)
                    validate_poll_result(adapter.manifest.service_id, account, result, cursor)
                    # Replaying exactly the same page is safe, even out of timestamp order.
                    hub.collect(adapter.manifest.service_id, account)
                    case.assertEqual(store.ingest(adapter.manifest.service_id, account, result), 0)
                    cursor = result.cursor
                case.assertEqual(hub.collect(adapter.manifest.service_id, account), 0)
            case.assertEqual(len(store.inbox()), expected_count * len(adapter.accounts))
        finally:
            store.close()


class ScriptedAdapter:
    manifest = DemoAdapter.manifest
    accounts = DemoAdapter.accounts

    def __init__(self):
        self.calls = []
        self.response = DemoAdapter().poll('demo-one', None)

    def poll(self, account_id, cursor):
        self.calls.append((account_id, cursor))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class AdapterSdkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'fixture.db')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.adapter = ScriptedAdapter()
        self.registry = Registry()
        self.registry.enable(self.adapter, (Binding('demo-one'),))
        self.hub = Hub(self.registry, self.store)

    def test_fixture_conformance(self):
        for factory, count, pages in ((DemoAdapter, 1, 2), (BulletinAdapter, 3, 3)):
            with self.subTest(adapter=factory.__name__):
                assert_read_conformance(self, factory, count, pages)

    def test_same_external_id_across_services_and_accounts(self):
        registry = Registry()
        for adapter in (DemoAdapter(), BulletinAdapter()):
            registry.enable(adapter, tuple(Binding(a) for a in adapter.accounts))
            for account in adapter.accounts:
                Hub(registry, self.store).collect(adapter.manifest.service_id, account)
        events = [e for e in self.store.inbox() if e['external_id'] == 'synthetic-1']
        self.assertEqual(len(events), 4)

    def test_disabled_unknown_account_and_capability_fail_before_poll(self):
        for service, account in (('demo', 'demo-two'), ('demo', 'unknown'), ('unknown', 'demo-one')):
            with self.assertRaises((ValueError, KeyError)):
                self.hub.collect(service, account)
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.store.audit(), [])
        registry = Registry()
        registry.enable(self.adapter, (Binding('demo-one', ('reply',)),))
        with self.assertRaises(ValueError):
            Hub(registry, self.store).collect('demo', 'demo-one')
        self.assertEqual(self.adapter.calls, [])
        registry = Registry()
        registry.enable(self.adapter)  # Default activation authorizes no account.
        with self.assertRaises(ValueError):
            Hub(registry, self.store).collect('demo', 'demo-one')

    def test_typed_failures_preserve_cursor_without_retry(self):
        self.hub.collect('demo', 'demo-one')
        before = self.store.audit()
        for error in (TransientPollError, PermanentPollError, AuthenticationPollError, RateLimitPollError):
            self.adapter.response = error('synthetic failure')
            calls = len(self.adapter.calls)
            with self.assertRaises(error):
                self.hub.collect('demo', 'demo-one')
            self.assertEqual(len(self.adapter.calls), calls + 1)
            self.assertEqual(self.adapter.calls[-1], ('demo-one', 'done'))
            self.assertEqual(self.store.cursor('demo', 'demo-one'), 'done')
            self.assertEqual(self.store.audit(), before)
        self.adapter.response = PollResult((), 'done')
        self.assertEqual(self.hub.collect('demo', 'demo-one'), 0)

    def test_invalid_pages_preserve_whole_batch_and_existing_cursor(self):
        self.hub.collect('demo', 'demo-one')
        event = replace(self.adapter.response.events[0], external_id='new')
        before = self.store.audit()
        for result in (PollResult((event,), None), PollResult((event,), ''),
                       PollResult((event,), 7), PollResult((event,), 'x' * 4097),
                       PollResult([event], 'next'), PollResult((event, object()), 'next'),
                       PollResult((event, replace(event, account_id='demo-two')), 'next'),
                       PollResult((event, replace(event, service_id='bulletin')), 'next')):
            self.adapter.response = result
            with self.assertRaises(ValueError):
                self.hub.collect('demo', 'demo-one')
            self.assertEqual(len(self.store.inbox()), 1)
            self.assertEqual(self.store.cursor('demo', 'demo-one'), 'done')
            self.assertEqual(self.store.audit(), before)

    def test_database_failure_rolls_back_events_cursor_and_audit(self):
        self.hub.collect('demo', 'demo-one')
        self.adapter.response = PollResult((replace(self.adapter.response.events[0], external_id='new'),), 'next')
        self.store.db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.hub.collect('demo', 'demo-one')
        self.assertEqual(len(self.store.inbox()), 1)
        self.assertEqual(self.store.cursor('demo', 'demo-one'), 'done')
        self.assertEqual(len(self.store.audit()), 1)

    def test_custom_namespaced_provider_operations(self):
        class GenericAdapter:
            accounts = ("service-account",)
            manifest = Manifest("generic-service", "1", (
                Capability("read", False, "low"),
                Capability("issues.create", True, "high"),
                Capability("device.status", False, "low"),
                Capability("draft.prepare", True, "low"),
            ))

            def poll(self, account_id, cursor):
                return PollResult((), "done")

        registry = Registry()
        registry.enable(GenericAdapter(), (
            Binding("service-account", (
                "read", "issues.create", "device.status", "draft.prepare",
            )),
        ))
        hub = Hub(registry, self.store)
        self.assertEqual(hub.collect("generic-service", "service-account"), 0)
        for operation, expected in (
            ("issues.create", "review"),
            ("device.status", "allowed"),
            ("draft.prepare", "review"),
            ("not.declared", "deny"),
        ):
            intent = ActionIntent(
                "generic-service", "service-account", operation,
                "stable-target", "synthetic", "custom-" + operation,
            )
            self.assertEqual(hub.plan(intent).status, expected)
        self.assertEqual(len(self.store.inbox()), 0)
        self.assertEqual(len(self.store.intents()), 4)

        for name in ("bad space", "UPPER.case", "unknown", "x..y"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                Capability(name, False, "low")

    def test_invalid_manifests_bindings_and_identity_changes(self):
        for kwargs in ({'sdk_version': 2}, {'sdk_version': True}, {'version': ''},
                       {'capabilities': ()}):
            with self.assertRaises(ValueError):
                replace(DemoAdapter.manifest, **kwargs)
        for args in (('unknown', False, 'low'), ('read', True, 'high'), ('reply', True, 'low')):
            with self.assertRaises(ValueError):
                Capability(*args)
        for bindings in ((Binding('unknown'),), (Binding('demo-one', ('unknown',)),),
                         (Binding('demo-one'), Binding('demo-one'))):
            with self.assertRaises(ValueError):
                Registry().enable(DemoAdapter(), bindings)
        self.adapter.manifest = replace(self.adapter.manifest, version='2')
        with self.assertRaises(ValueError):
            self.hub.collect('demo', 'demo-one')
        self.assertEqual(self.adapter.calls, [])
        self.adapter.manifest = DemoAdapter.manifest
        self.adapter.accounts = ('demo-one',)
        with self.assertRaises(ValueError):
            self.hub.collect('demo', 'demo-one')


    def test_unbound_planning_is_denied(self):
        for account, operation in (("demo-two", "read"), ("demo-one", "reply")):
            intent = ActionIntent("demo", account, operation, "fixture", "", account)
            self.assertEqual(self.hub.plan(intent).status, "deny")
        self.assertEqual(self.adapter.calls, [])

    def test_corrupt_saved_cursor_fails_before_poll(self):
        self.store.db.execute("INSERT INTO cursors VALUES ('demo', 'demo-one', '')")
        self.store.db.commit()
        with self.assertRaises(ValueError):
            self.hub.collect('demo', 'demo-one')
        self.assertEqual(self.adapter.calls, [])

    def test_first_event_wins_and_mutable_attributes_are_revalidated(self):
        self.hub.collect('demo', 'demo-one')
        original = self.store.inbox()
        event = replace(self.adapter.response.events[0], body='changed fixture')
        self.adapter.response = PollResult((event,), 'done')
        self.assertEqual(self.hub.collect('demo', 'demo-one'), 0)
        self.assertEqual(self.store.inbox(), original)
        event.attributes['invalid'] = 7
        with self.assertRaises(ValueError):
            self.hub.collect('demo', 'demo-one')
        self.assertEqual(self.store.inbox(), original)

    def test_registration_failure_is_atomic_and_accounts_are_validated(self):
        for accounts in ((), ('same', 'same'), ('',), ['demo-one']):
            adapter = ScriptedAdapter()
            adapter.accounts = accounts
            registry = Registry()
            with self.assertRaises(ValueError):
                registry.enable(adapter)
            self.assertEqual(registry.manifests(), ())
        registry = Registry()
        with self.assertRaises(ValueError):
            registry.enable(DemoAdapter(), (Binding('demo-one'), Binding('unknown')))
        self.assertEqual(registry.manifests(), ())
        registry.enable(DemoAdapter(), (Binding('demo-one'),))
        self.assertIsNotNone(registry.require('demo', 'demo-one', 'read'))
        with self.assertRaises(ValueError):
            registry.require('demo', 'demo-two', 'read')

    def test_failure_does_not_change_another_accounts_cursor(self):
        registry = Registry()
        adapter = ScriptedAdapter()
        registry.enable(adapter, tuple(Binding(a) for a in adapter.accounts))
        hub = Hub(registry, self.store)
        hub.collect('demo', 'demo-one')
        adapter.response = DemoAdapter().poll('demo-two', None)
        hub.collect('demo', 'demo-two')
        before = (self.store.inbox(), self.store.audit())
        adapter.response = TransientPollError('synthetic failure')
        with self.assertRaises(TransientPollError):
            hub.collect('demo', 'demo-one')
        self.assertEqual((self.store.inbox(), self.store.audit()), before)
        for account in adapter.accounts:
            self.assertEqual(self.store.cursor('demo', account), 'done')
