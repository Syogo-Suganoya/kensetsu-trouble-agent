import tempfile
import unittest
from pathlib import Path

from troublelog.models import ValidationError
from troublelog.store import NotFoundError, Store

PAYLOAD = {
    "created_at": "2026-09-15T13:10:00+09:00",
    "raw_report": "生コン来ない、午後打設無理かも",
    "reporter": {"role": "協力会社", "company": "山田土木", "name": "山田", "tier": 2},
    "site": "〇〇マンション新築工事",
    "category": "資材遅延・不足",
    "subcategory": "生コン未着",
    "severity": "高",
    "summary": {
        "what": "午後打設予定の生コンが未着",
        "when": "2026-09-15 13:00",
        "where": "3階スラブ",
        "impact": "午後の打設中止の可能性、ポンプ車・打設班の待機",
        "stakeholders": ["元請 工事主任", "生コンプラント", "ポンプ業者"],
    },
}


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_create_and_sequential_ids(self):
        a = self.store.create(PAYLOAD)
        b = self.store.create(PAYLOAD)
        c = self.store.create({**PAYLOAD, "created_at": "2026-09-16T09:00:00+09:00"})
        self.assertEqual(a.trouble_id, "TR-20260915-001")
        self.assertEqual(b.trouble_id, "TR-20260915-002")
        self.assertEqual(c.trouble_id, "TR-20260916-001")
        self.assertEqual(self.store.get(a.trouble_id).summary.stakeholders[0], "元請 工事主任")

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self.store.create({**PAYLOAD, "category": "謎"})
        with self.assertRaises(ValidationError):
            self.store.create({k: v for k, v in PAYLOAD.items() if k != "summary"})
        with self.assertRaises(NotFoundError):
            self.store.get("TR-00000000-001")

    def test_events_drafts_status(self):
        tid = self.store.create(PAYLOAD).trouble_id
        log = self.store.add_event(tid, "ヒアリング", 3, at="2026-09-15T13:10:00+09:00")
        self.assertEqual(log.status, "受付")
        log = self.store.add_event(tid, "連絡", 20, at="2026-09-15T22:30:00+09:00", actor="山田")
        self.assertEqual(log.status, "対応中")
        self.assertEqual(log.events[-1].time_band, "深夜")
        self.assertTrue(log.events[-1].off_hours)
        self.assertEqual(log.total_minutes, 23)

        log = self.store.add_draft(tid, "元請報告", "工事主任 様\n…")
        self.assertEqual(len(log.drafts), 1)
        with self.assertRaises(ValidationError):
            self.store.add_draft(tid, "謎", "x")

        log = self.store.set_status(tid, "解決")
        self.assertIsNotNone(log.resolved_at)

    def test_summary(self):
        t1 = self.store.create(PAYLOAD).trouble_id
        t2 = self.store.create({**PAYLOAD, "category": "検査指摘・品質"}).trouble_id
        self.store.add_event(t1, "連絡", 30, at="2026-09-15T10:00:00+09:00", actor="山田")
        self.store.add_event(t1, "調整", 45, at="2026-09-15T19:00:00+09:00", actor="山田")
        self.store.add_event(t2, "書類作成", 60, at="2026-09-19T09:00:00+09:00")  # 土曜
        self.store.add_event(t2, "連絡", 10, at="2026-10-01T10:00:00+09:00")  # 翌月

        s = self.store.summary("2026-09")
        self.assertEqual(s["trouble_count"], 2)
        self.assertEqual(s["total_minutes"], 135)
        self.assertEqual(s["off_hours_minutes"], 105)
        self.assertEqual(s["minutes_by_band"], {"所定内": 30, "時間外": 45, "深夜": 0, "休日": 60})
        self.assertEqual(s["minutes_by_actor"]["(未記入)"], 60)
        self.assertEqual(self.store.summary("2026-10")["trouble_count"], 0)
        self.assertEqual(self.store.summary()["total_minutes"], 145)


if __name__ == "__main__":
    unittest.main()
