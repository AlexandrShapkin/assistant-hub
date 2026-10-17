"""Local fake-demo CLI. No outgoing dispatch exists."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from .core.contracts import ActionIntent, PollError
from .core.demo import BulletinAdapter, DemoAdapter
from .core.hub import Hub
from .core.registry import Binding, Registry
from .core.store import Store


def registry() -> Registry:
    result = Registry()
    result.enable(DemoAdapter(), tuple(
        Binding(a, ("read", "reply", "exact-template")) for a in DemoAdapter.accounts
    ))
    result.enable(BulletinAdapter(), tuple(Binding(a) for a in BulletinAdapter.accounts))
    return result


def doctor() -> dict:
    with tempfile.TemporaryDirectory(prefix="assistant-hub-doctor-") as directory:
        store = Store(Path(directory) / "check.db")
        try:
            hub = Hub(registry(), store)
            first = hub.collect("demo", "demo-one")
            repeat = hub.collect("demo", "demo-one")
            decision = hub.plan(ActionIntent("demo", "demo-one", "reply", "fake", "fake", "doctor"))
            if (first, repeat, decision.status) != (1, 0, "review"):
                raise ValueError("doctor self-check failed")
        finally:
            store.close()
    return {"status": "ok", "maturity": "pre-alpha", "adapter": "FAKE DEMO", "dispatch": "not implemented"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assistant Hub pre-alpha — FAKE DEMO only")
    parser.add_argument("--db", type=Path, default=Path.home() / ".local/share/assistant-hub/hub.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("services")
    collect = commands.add_parser("collect-demo")
    collect.add_argument("account", choices=DemoAdapter.accounts)
    bulletin = commands.add_parser("collect-bulletin")
    bulletin.add_argument("account", choices=BulletinAdapter.accounts)
    commands.add_parser("inbox")
    plan = commands.add_parser("plan-demo")
    plan.add_argument("--account", default="demo-one", choices=DemoAdapter.accounts)
    plan.add_argument("--operation", choices=("reply", "exact-template"), default="reply")
    for name in ("target", "payload", "key"):
        plan.add_argument("--" + name, required=True)
    commands.add_parser("intents")
    review = commands.add_parser("review")
    review.add_argument("outcome", choices=("approve", "reject"))
    review.add_argument("key")
    review.add_argument("--reviewer", required=True)
    args = parser.parse_args(argv)
    store = None
    try:
        if args.command == "doctor":
            output = doctor()
        elif args.command == "services":
            output = {"label": "FAKE DEMO", "services": [asdict(m) for m in registry().manifests()]}
        else:
            store = Store(args.db)
            hub = Hub(registry(), store)
            if args.command == "collect-demo":
                output = {"label": "FAKE DEMO", "inserted": hub.collect("demo", args.account)}
            elif args.command == "collect-bulletin":
                output = {"label": "FAKE DEMO", "inserted": hub.collect("bulletin", args.account)}
            elif args.command == "inbox":
                output = store.inbox()
            elif args.command == "plan-demo":
                output = asdict(hub.plan(ActionIntent("demo", args.account, args.operation,
                                                     args.target, args.payload, args.key)))
            elif args.command == "intents":
                output = store.intents()
            else:
                store.review(args.key, args.outcome, args.reviewer)
                output = {"recorded": args.outcome, "dispatch": "not implemented"}
        print(json.dumps(output, indent=2))
        return 0
    except (ValueError, KeyError, OSError, sqlite3.Error, PollError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()
