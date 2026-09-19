"""対応時間の時間帯判定（サビ残相当時間の可視化の基礎）。

時間帯区分:
- 休日  : 土日・国民の祝日（振替休日・国民の休日を含む）
- 深夜  : 平日 22:00〜翌5:00
- 時間外: 平日の所定時間外（深夜を除く）
- 所定内: 平日の所定時間内

所定時間は業種パックの work_hours（既定 8:00〜17:00）を使い、
環境変数 TROUBLELOG_WORK_START / TROUBLELOG_WORK_END（時, 整数）があればそちらを優先する。
判定はイベントの開始時刻 `at` で行う（跨ぎは按分しない）。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from functools import lru_cache

BANDS = ("所定内", "時間外", "深夜", "休日")
NIGHT_START = 22
NIGHT_END = 5


def _work_hours(default: tuple[int, int] | None = None) -> tuple[int, int]:
    start, end = default or (8, 17)
    return (
        int(os.environ.get("TROUBLELOG_WORK_START", start)),
        int(os.environ.get("TROUBLELOG_WORK_END", end)),
    )


def _nth_monday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (7 - first.weekday()) % 7  # 最初の月曜まで
    return first + timedelta(days=offset + 7 * (n - 1))


def _equinox_day(year: int, base: float) -> int:
    # 1980〜2099年で有効な近似式
    return int(base + 0.242194 * (year - 1980) - int((year - 1980) / 4))


@lru_cache(maxsize=64)
def jp_holidays(year: int) -> frozenset[date]:
    """現行の祝日法（2020年以降の日付ルール）に基づく祝日集合。"""
    days = {
        date(year, 1, 1),
        _nth_monday(year, 1, 2),  # 成人の日
        date(year, 2, 11),
        date(year, 2, 23),
        date(year, 3, _equinox_day(year, 20.8431)),  # 春分の日
        date(year, 4, 29),
        date(year, 5, 3),
        date(year, 5, 4),
        date(year, 5, 5),
        _nth_monday(year, 7, 3),  # 海の日
        date(year, 8, 11),
        _nth_monday(year, 9, 3),  # 敬老の日
        date(year, 9, _equinox_day(year, 23.2488)),  # 秋分の日
        _nth_monday(year, 10, 2),  # スポーツの日
        date(year, 11, 3),
        date(year, 11, 23),
    }
    # 国民の休日: 祝日に挟まれた平日
    for d in sorted(days):
        mid = d + timedelta(days=1)
        if mid not in days and (d + timedelta(days=2)) in days and mid.weekday() != 6:
            days.add(mid)
    # 振替休日: 日曜の祝日の後の最初の非祝日
    for d in sorted(days):
        if d.weekday() == 6:
            sub = d + timedelta(days=1)
            while sub in days:
                sub += timedelta(days=1)
            days.add(sub)
    return frozenset(days)


def is_holiday(d: date) -> bool:
    return d.weekday() >= 5 or d in jp_holidays(d.year)


def time_band(dt: datetime, work_hours: tuple[int, int] | None = None) -> str:
    if is_holiday(dt.date()):
        return "休日"
    if dt.hour >= NIGHT_START or dt.hour < NIGHT_END:
        return "深夜"
    start, end = _work_hours(work_hours)
    if start <= dt.hour < end:
        return "所定内"
    return "時間外"


def is_off_hours(dt: datetime, work_hours: tuple[int, int] | None = None) -> bool:
    return time_band(dt, work_hours) != "所定内"
