import json
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from troublelog.industry import get_industry, load_industries
from troublelog.models import ValidationError
from troublelog.partners import read_partners_csv
from troublelog.store import Store

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"


def table_first_column(md: Path) -> list[str]:
    """categories.md の表の1列目（ヘッダー・区切り行を除く）"""
    rows = [l for l in md.read_text(encoding="utf-8").splitlines() if l.startswith("|")]
    return [r.split("|")[1].strip() for r in rows[2:]]


class PackConsistencyTest(unittest.TestCase):
    """業種パック（JSON）と Skill の references / templates / examples が揃っていること。"""

    def test_expected_packs(self):
        self.assertEqual(set(load_industries()), {"construction", "manufacturing", "logistics"})

    def test_pack_files(self):
        for ind in load_industries().values():
            with self.subTest(industry=ind.id):
                intake = SKILLS / "trouble-intake" / "references" / ind.id
                draft = SKILLS / "trouble-draft"
                for f in (
                    intake / "categories.md",
                    intake / "hearing-items.md",
                    intake / "safety.md",
                    draft / "references" / ind.id / "tone-guide.md",
                    draft / "references" / ind.id / "focus.md",
                    draft / "templates" / ind.id / "upstream_report.md",
                    draft / "templates" / ind.id / "partner_request.md",
                    draft / "templates" / ind.id / "action_plan.md",
                    ROOT / "examples" / ind.id / "intake_sample.json",
                    ROOT / "examples" / ind.id / "partners_sample.csv",
                ):
                    self.assertTrue(f.exists(), f)
                self.assertTrue(list((ROOT / "examples" / ind.id / "cases").glob("*.md")))

    def test_categories_match_skill_reference(self):
        for ind in load_industries().values():
            with self.subTest(industry=ind.id):
                md = SKILLS / "trouble-intake" / "references" / ind.id / "categories.md"
                self.assertEqual(table_first_column(md), list(ind.categories))

    def test_focus_uses_pack_categories_and_draft_types(self):
        for ind in load_industries().values():
            with self.subTest(industry=ind.id):
                focus = SKILLS / "trouble-draft" / "references" / ind.id / "focus.md"
                for c in table_first_column(focus):
                    self.assertIn(c, ind.categories)
                text = focus.read_text(encoding="utf-8")
                for t in ind.draft_types:
                    self.assertIn(f"`{t}`", text)

    def test_roles_in_hearing_items(self):
        for ind in load_industries().values():
            with self.subTest(industry=ind.id):
                text = (SKILLS / "trouble-intake" / "references" / ind.id / "hearing-items.md").read_text(encoding="utf-8")
                for r in ind.roles:
                    self.assertIn(r, text)

    def test_sample_data_is_valid_for_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            try:
                for ind in load_industries().values():
                    with self.subTest(industry=ind.id):
                        partners, ignored = read_partners_csv(
                            ROOT / "examples" / ind.id / "partners_sample.csv", ind.id)
                        self.assertEqual(ignored, [])
                        self.assertGreaterEqual(len(partners), 15)
                        self.assertEqual({p.relation for p in partners} - set(ind.relations), set())
                        payload = json.loads(
                            (ROOT / "examples" / ind.id / "intake_sample.json").read_text(encoding="utf-8"))
                        self.assertEqual(store.create(payload).industry, ind.id)
            finally:
                store.close()

    def test_case_files_use_pack_categories(self):
        for ind in load_industries().values():
            for case in (ROOT / "examples" / ind.id / "cases").glob("*.md"):
                with self.subTest(case=case.name):
                    text = case.read_text(encoding="utf-8")
                    m = re.search(r"## 期待する分類\n(.+?) /", text)
                    self.assertIsNotNone(m)
                    self.assertIn(m.group(1).strip(), ind.categories)


class IndustryBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.logistics = json.loads(
            (ROOT / "examples" / "logistics" / "intake_sample.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_validation_is_per_industry(self):
        with self.assertRaises(ValidationError):  # 運送の分類を建設として登録
            self.store.create({**self.logistics, "industry": "construction"})
        with self.assertRaises(ValidationError):
            self.store.create({**self.logistics, "industry": "unknown"})

    def test_industry_resolution_order(self):
        payload = {k: v for k, v in self.logistics.items() if k != "industry"}
        self.assertEqual(self.store.create(payload, industry="logistics").industry, "logistics")
        with mock.patch.dict(os.environ, {"TROUBLELOG_INDUSTRY": "logistics"}):
            self.assertEqual(self.store.create(payload).industry, "logistics")

    def test_industry_specific_actions_and_drafts(self):
        tid = self.store.create(self.logistics).trouble_id
        log = self.store.add_event(tid, "荷待ち", 130, at="2026-09-15T09:00:00+09:00")
        self.assertEqual(log.events[-1].action, "荷待ち")
        with self.assertRaises(ValidationError):
            self.store.add_event(tid, "選別・手直し", 10)  # 製造業の対応種別
        self.store.add_draft(tid, "荷主・元請報告", "本文")
        with self.assertRaises(ValidationError):
            self.store.add_draft(tid, "元請報告", "本文")  # 建設業のドラフト種別

    def test_summary_by_industry(self):
        construction = json.loads(
            (ROOT / "examples" / "construction" / "intake_sample.json").read_text(encoding="utf-8"))
        t1 = self.store.create(construction).trouble_id
        t2 = self.store.create(self.logistics).trouble_id
        self.store.add_event(t1, "連絡", 30, at="2026-09-15T10:00:00+09:00")
        self.store.add_event(t2, "荷待ち", 120, at="2026-09-15T09:00:00+09:00")
        s = self.store.summary("2026-09", "logistics")
        self.assertEqual((s["trouble_count"], s["total_minutes"]), (1, 120))
        s = self.store.summary("2026-09")
        self.assertEqual(s["by_industry"], {"construction": 1, "logistics": 1})
        self.assertEqual(s["minutes_by_industry"], {"construction": 30, "logistics": 120})

    def test_partners_are_scoped_by_industry(self):
        for ind in ("construction", "logistics"):
            partners, _ = read_partners_csv(ROOT / "examples" / ind / "partners_sample.csv", ind)
            self.store.import_partners(partners, ind)
        self.assertEqual({p.industry for p in self.store.list_partners(industry="logistics")}, {"logistics"})
        # replace はその業種だけを入れ替える
        self.store.import_partners([], "logistics", replace=True)
        self.assertEqual(self.store.list_partners(industry="logistics"), [])
        self.assertEqual(len(self.store.list_partners(industry="construction")), 20)

    def test_work_hours_from_pack(self):
        ind = get_industry("logistics")
        self.assertEqual(ind.work_hours, (8, 17))
        self.assertIn("附帯作業", ind.actions)
        self.assertEqual(ind.actions[-1], "その他")


class MigrationTest(unittest.TestCase):
    def test_legacy_db_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE troubles (trouble_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,"
                         " status TEXT NOT NULL, category TEXT NOT NULL, data TEXT NOT NULL)")
            conn.execute("CREATE TABLE partners (company TEXT NOT NULL, contact TEXT NOT NULL,"
                         " relation TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (company, contact))")
            legacy = json.loads((ROOT / "examples" / "construction" / "intake_sample.json").read_text(encoding="utf-8"))
            legacy.pop("industry")
            legacy.update(trouble_id="TR-20260915-001", status="受付", events=[], drafts=[])
            conn.execute("INSERT INTO troubles VALUES (?, ?, ?, ?, ?)",
                         ("TR-20260915-001", legacy["created_at"], "受付", legacy["category"],
                          json.dumps(legacy, ensure_ascii=False)))
            conn.execute("INSERT INTO partners VALUES (?, ?, ?, ?)",
                         ("山田土木株式会社", "山田 太郎", "協力会社",
                          json.dumps({"company": "山田土木株式会社", "relation": "協力会社", "contact": "山田 太郎"},
                                     ensure_ascii=False)))
            conn.commit()
            conn.close()

            store = Store(db)
            try:
                self.assertEqual(store.get("TR-20260915-001").industry, "construction")
                self.assertEqual(len(store.list(industry="construction")), 1)
                partners = store.list_partners(industry="construction")
                self.assertEqual([p.company for p in partners], ["山田土木株式会社"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
