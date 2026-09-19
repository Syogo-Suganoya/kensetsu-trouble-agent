import tempfile
import unittest
from pathlib import Path

from troublelog.partners import CsvImportError, decode, parse_partners, read_partners_csv
from troublelog.store import Store

ROOT = Path(__file__).resolve().parent.parent
HEADER = "会社名,取引区分,業種,対応分類,担当者,役職,電話,メール,LINE可,所在地,対応エリア,備考\n"


class ParseTest(unittest.TestCase):
    def test_sample_csv(self):
        partners, ignored = read_partners_csv(ROOT / "examples" / "construction" / "partners_sample.csv")
        self.assertEqual(len(partners), 20)
        self.assertEqual(ignored, [])
        yamada = next(p for p in partners if p.company == "山田土木株式会社")
        self.assertEqual(yamada.categories, ["工期遅延", "協力会社・人員", "天候・災害"])
        self.assertTrue(yamada.line)

    def test_encodings(self):
        text = HEADER + "テスト工業,協力会社,鉄筋工事,資材遅延・不足、工期遅延,田中,,,,不可,,,\n"
        for enc in ("utf-8", "utf-8-sig", "cp932"):
            p = parse_partners(decode(text.encode(enc)))[0]
            self.assertEqual((p.company, p.categories, p.line),
                             ("テスト工業", ["資材遅延・不足", "工期遅延"], False))

    def test_minimal_columns_and_blank_lines(self):
        partners = parse_partners("会社名,取引区分\nA社,その他\n,\n\nB社,元請\n")
        self.assertEqual([p.company for p in partners], ["A社", "B社"])

    def test_errors_collected_with_line_numbers(self):
        text = (HEADER
                + "A社,謎区分,,,,,,,,,,\n"
                + ",協力会社,,,,,,,,,,\n"
                + "B社,協力会社,,存在しない分類,,,,,,,,\n"
                + "C社,協力会社,,,田中,,,,たぶん,,,\n"
                + "D社,協力会社,,,佐藤,,,,,,,\n"
                + "D社,協力会社,,,佐藤,,,,,,,\n")
        with self.assertRaises(CsvImportError) as cm:
            parse_partners(text)
        errors = cm.exception.errors
        self.assertEqual(len(errors), 5)
        self.assertTrue(errors[0].startswith("2行目"))
        self.assertIn("7行目", errors[4])

    def test_missing_required_column(self):
        with self.assertRaises(CsvImportError):
            parse_partners("会社名,業種\nA社,鉄筋\n")


class StorePartnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.partners, _ = read_partners_csv(ROOT / "examples" / "construction" / "partners_sample.csv")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_import_upsert_replace(self):
        self.assertEqual(self.store.import_partners(self.partners, "construction"),
                         {"industry": "construction", "inserted": 20, "updated": 0, "total": 20})
        self.assertEqual(self.store.import_partners(self.partners[:3], "construction"),
                         {"industry": "construction", "inserted": 0, "updated": 3, "total": 20})
        self.assertEqual(self.store.import_partners(self.partners[:3], "construction", replace=True),
                         {"industry": "construction", "inserted": 3, "updated": 0, "total": 3})

    def test_list_filters(self):
        self.store.import_partners(self.partners, "construction")
        materials = self.store.list_partners(category="資材遅延・不足")
        self.assertIn("〇〇生コン株式会社", [p.company for p in materials])
        self.assertTrue(all("資材遅延・不足" in p.categories for p in materials))
        self.assertEqual({p.relation for p in self.store.list_partners(relation="元請")}, {"元請"})
        self.assertEqual(len(self.store.list_partners(q="青葉")), 2)
        self.assertEqual(
            [p.company for p in self.store.list_partners(category="協力会社・人員", q="川口")],
            ["山田土木株式会社"],
        )


if __name__ == "__main__":
    unittest.main()
