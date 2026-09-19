import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from troublelog.cli import run

from .test_store import PAYLOAD


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run(["--db", self.db, *argv])
        return code, json.loads(buf.getvalue())

    def test_flow(self):
        intake = Path(self.tmp.name) / "intake.json"
        intake.write_text(json.dumps(PAYLOAD, ensure_ascii=False), encoding="utf-8")
        draft = Path(self.tmp.name) / "draft.md"
        draft.write_text("工事主任 様\n状況をご報告します。", encoding="utf-8")

        code, out = self.call("new", "--json", str(intake))
        self.assertEqual(code, 0)
        tid = out["trouble_id"]

        code, out = self.call("event", tid, "--action", "連絡", "--minutes", "15",
                              "--at", "2026-09-15T23:00:00+09:00", "--actor", "山田")
        self.assertEqual((code, out["event"]["time_band"], out["status"]), (0, "深夜", "対応中"))

        code, out = self.call("draft", tid, "--type", "元請報告", "--file", str(draft))
        self.assertEqual((code, out["drafts"]), (0, 1))

        code, out = self.call("list", "--status", "対応中")
        self.assertEqual([x["trouble_id"] for x in out], [tid])

        code, out = self.call("summary", "--month", "2026-09")
        self.assertEqual(out["off_hours_minutes"], 15)

        code, out = self.call("status", tid, "--set", "解決")
        self.assertEqual(out["status"], "解決")

    def test_errors_are_json(self):
        code, out = self.call("show", "TR-00000000-999")
        self.assertEqual(code, 1)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
