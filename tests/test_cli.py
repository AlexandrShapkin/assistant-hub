from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from assistant_hub.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(list(args)), 0)
        return json.loads(output.getvalue())

    def test_doctor_and_services_do_not_create_requested_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unused.db"
            self.assertEqual(self.invoke("--db", str(path), "doctor")["status"], "ok")
            self.assertEqual(self.invoke("--db", str(path), "services")["label"], "FAKE DEMO")
            self.assertFalse(path.exists())

    def test_local_demo_workflow_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            base = ("--db", str(Path(directory) / "hub.db"))
            self.assertEqual(self.invoke(*base, "collect-demo", "demo-one")["inserted"], 1)
            self.assertEqual(self.invoke(*base, "collect-demo", "demo-one")["inserted"], 0)
            self.assertEqual(len(self.invoke(*base, "inbox")), 1)
            plan = ("plan-demo", "--target", "synthetic-thread", "--payload", "Fake", "--key", "cli-key")
            self.assertEqual(self.invoke(*base, *plan)["status"], "review")
            self.assertEqual(self.invoke(*base, "review", "approve", "cli-key", "--reviewer", "local-user")["dispatch"], "not implemented")
            self.assertEqual(self.invoke(*base, "intents")[0]["decision"]["status"], "review")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([*base, *plan, "--payload", "Different"]), 1)


    def test_bulletin_pages_and_demo_remain_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = ("--db", str(Path(directory) / "hub.db"))
            for count in (2, 1, 0):
                self.assertEqual(self.invoke(*base, "collect-bulletin", "bulletin-alpha")["inserted"], count)
            self.assertEqual(self.invoke(*base, "collect-demo", "demo-one")["inserted"], 1)
            self.assertEqual(len(self.invoke(*base, "inbox")), 4)
