import os
import unittest
from datetime import date, datetime
from unittest import mock

from troublelog.timecalc import is_off_hours, jp_holidays, time_band


class HolidayTest(unittest.TestCase):
    def test_2026_holidays(self):
        h = jp_holidays(2026)
        expected = [
            date(2026, 1, 1), date(2026, 1, 12), date(2026, 2, 11), date(2026, 2, 23),
            date(2026, 3, 20), date(2026, 4, 29), date(2026, 5, 3), date(2026, 5, 4),
            date(2026, 5, 5), date(2026, 5, 6),  # 5/3(日)の振替
            date(2026, 7, 20), date(2026, 8, 11), date(2026, 9, 21),
            date(2026, 9, 22),  # 国民の休日（敬老の日と秋分の日に挟まれる）
            date(2026, 9, 23), date(2026, 10, 12), date(2026, 11, 3), date(2026, 11, 23),
        ]
        for d in expected:
            self.assertIn(d, h, d)
        self.assertEqual(len(h), len(expected))

    def test_substitute_holiday(self):
        # 2023-01-01 は日曜 → 1/2 が振替休日
        self.assertIn(date(2023, 1, 2), jp_holidays(2023))


class TimeBandTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("TROUBLELOG_WORK_START", None)
        os.environ.pop("TROUBLELOG_WORK_END", None)
        self.addCleanup(patcher.stop)

    def test_weekday_bands(self):
        # 2026-09-15 は火曜
        self.assertEqual(time_band(datetime(2026, 9, 15, 7, 59)), "時間外")
        self.assertEqual(time_band(datetime(2026, 9, 15, 8, 0)), "所定内")
        self.assertEqual(time_band(datetime(2026, 9, 15, 16, 59)), "所定内")
        self.assertEqual(time_band(datetime(2026, 9, 15, 17, 0)), "時間外")
        self.assertEqual(time_band(datetime(2026, 9, 15, 21, 59)), "時間外")
        self.assertEqual(time_band(datetime(2026, 9, 15, 22, 0)), "深夜")
        self.assertEqual(time_band(datetime(2026, 9, 16, 4, 59)), "深夜")
        self.assertEqual(time_band(datetime(2026, 9, 16, 5, 0)), "時間外")

    def test_holidays(self):
        self.assertEqual(time_band(datetime(2026, 9, 19, 10, 0)), "休日")  # 土曜
        self.assertEqual(time_band(datetime(2026, 9, 21, 10, 0)), "休日")  # 敬老の日
        self.assertTrue(is_off_hours(datetime(2026, 9, 20, 10, 0)))
        self.assertFalse(is_off_hours(datetime(2026, 9, 15, 10, 0)))

    def test_work_hours_env(self):
        os.environ["TROUBLELOG_WORK_END"] = "18"
        self.assertEqual(time_band(datetime(2026, 9, 15, 17, 30)), "所定内")


if __name__ == "__main__":
    unittest.main()
