"""SQLite によるトラブルログ保存。

1トラブル=1行・1取引先=1行。検索に使う列だけ正規化し、本体は JSON で保持する。
全業種で同じテーブルを使い、industry 列で区別する。
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .industry import DEFAULT_INDUSTRY, default_industry_id, get_industry
from .models import Draft, Event, Partner, TroubleLog, ValidationError
from .timecalc import BANDS, time_band

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "troubles.db"


class NotFoundError(LookupError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Store:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path or os.environ.get("TROUBLELOG_DB") or DEFAULT_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self._migrate()

    def _columns(self, table: str) -> list[str]:
        return [r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")]

    def _migrate(self) -> None:
        with self.conn:
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS troubles (
                    trouble_id TEXT PRIMARY KEY,
                    industry TEXT NOT NULL DEFAULT 'construction',
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    category TEXT NOT NULL,
                    data TEXT NOT NULL
                )"""
            )
            if "industry" not in self._columns("troubles"):  # 業種導入前のDB
                self.conn.execute(
                    "ALTER TABLE troubles ADD COLUMN industry TEXT NOT NULL DEFAULT 'construction'"
                )

            legacy_partners = self._columns("partners")
            if legacy_partners and "industry" not in legacy_partners:
                self.conn.execute("ALTER TABLE partners RENAME TO partners_legacy")
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS partners (
                    industry TEXT NOT NULL,
                    company TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (industry, company, contact)
                )"""
            )
            if legacy_partners and "industry" not in legacy_partners:
                self.conn.execute(
                    f"""INSERT INTO partners (industry, company, contact, relation, data)
                        SELECT '{DEFAULT_INDUSTRY}', company, contact, relation, data FROM partners_legacy"""
                )
                self.conn.execute("DROP TABLE partners_legacy")

    def close(self) -> None:
        self.conn.close()

    # --- 基本操作 ---------------------------------------------------------

    def _next_id(self, created: datetime) -> str:
        prefix = f"TR-{created:%Y%m%d}-"
        row = self.conn.execute(
            "SELECT MAX(trouble_id) FROM troubles WHERE trouble_id LIKE ?", (prefix + "%",)
        ).fetchone()
        seq = int(row[0].rsplit("-", 1)[1]) + 1 if row[0] else 1
        return f"{prefix}{seq:03d}"

    def _save(self, log: TroubleLog) -> None:
        log.validate()
        self.conn.execute(
            """INSERT INTO troubles (trouble_id, industry, created_at, status, category, data)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(trouble_id) DO UPDATE SET
                 status=excluded.status, category=excluded.category, data=excluded.data""",
            (
                log.trouble_id,
                log.industry,
                log.created_at,
                log.status,
                log.category,
                json.dumps(log.to_dict(), ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def create(self, payload: dict, industry: str | None = None) -> TroubleLog:
        """industry の優先順位: 入力JSONの industry > 引数 > 環境変数 TROUBLELOG_INDUSTRY > 建設業"""
        created_at = payload.get("created_at") or now_iso()
        data = {
            **payload,
            "industry": payload.get("industry") or industry or default_industry_id(),
            "trouble_id": self._next_id(parse_dt(created_at)),
            "created_at": created_at,
            "status": payload.get("status", "受付"),
            "events": [],
            "drafts": [],
        }
        try:
            log = TroubleLog.from_dict(data)
        except (KeyError, TypeError) as e:
            raise ValidationError(f"入力JSONの形式が不正: {e}") from e
        self._save(log)
        return log

    def get(self, trouble_id: str) -> TroubleLog:
        row = self.conn.execute(
            "SELECT data FROM troubles WHERE trouble_id = ?", (trouble_id,)
        ).fetchone()
        if not row:
            raise NotFoundError(f"トラブルIDが見つかりません: {trouble_id}")
        return TroubleLog.from_dict(json.loads(row[0]))

    def list(
        self, status: str | None = None, since: str | None = None, industry: str | None = None
    ) -> list[TroubleLog]:
        sql, args = "SELECT data FROM troubles WHERE 1=1", []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if since:
            sql += " AND created_at >= ?"
            args.append(since)
        if industry:
            sql += " AND industry = ?"
            args.append(industry)
        sql += " ORDER BY created_at, trouble_id"
        return [TroubleLog.from_dict(json.loads(r[0])) for r in self.conn.execute(sql, args)]

    # --- 更新 -------------------------------------------------------------

    def add_event(
        self,
        trouble_id: str,
        action: str,
        minutes: int,
        at: str | None = None,
        actor: str = "",
        note: str = "",
    ) -> TroubleLog:
        log = self.get(trouble_id)
        at = at or now_iso()
        band = time_band(parse_dt(at), get_industry(log.industry).work_hours)
        log.events.append(
            Event(
                at=at,
                action=action,
                minutes=minutes,
                actor=actor,
                note=note,
                time_band=band,
                off_hours=band != "所定内",
            )
        )
        if log.status == "受付" and action != "ヒアリング":
            log.status = "対応中"
        self._save(log)
        return log

    def add_draft(self, trouble_id: str, draft_type: str, text: str) -> TroubleLog:
        log = self.get(trouble_id)
        log.drafts.append(Draft(type=draft_type, text=text, created_at=now_iso()))
        self._save(log)
        return log

    def set_status(self, trouble_id: str, status: str) -> TroubleLog:
        log = self.get(trouble_id)
        log.status = status
        log.resolved_at = now_iso() if status == "解決" else None
        self._save(log)
        return log

    # --- 取引先 -----------------------------------------------------------

    def import_partners(
        self, partners: list[Partner], industry: str, replace: bool = False
    ) -> dict:
        """業種＋会社名＋担当者をキーに追加・上書きする。replace=True ならその業種の既存分を全削除してから取り込む。"""
        with self.conn:  # 1トランザクション（途中で失敗したら全件ロールバック）
            if replace:
                self.conn.execute("DELETE FROM partners WHERE industry = ?", (industry,))
            existing = {
                tuple(r)
                for r in self.conn.execute(
                    "SELECT company, contact FROM partners WHERE industry = ?", (industry,)
                )
            }
            inserted = updated = 0
            for p in partners:
                p.industry = industry
                p.validate()
                if (p.company, p.contact) in existing:
                    updated += 1
                else:
                    inserted += 1
                self.conn.execute(
                    """INSERT INTO partners (industry, company, contact, relation, data)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(industry, company, contact) DO UPDATE SET
                         relation=excluded.relation, data=excluded.data""",
                    (industry, p.company, p.contact, p.relation,
                     json.dumps(asdict(p), ensure_ascii=False)),
                )
        total = self.conn.execute(
            "SELECT COUNT(*) FROM partners WHERE industry = ?", (industry,)
        ).fetchone()[0]
        return {"industry": industry, "inserted": inserted, "updated": updated, "total": total}

    def list_partners(
        self,
        category: str | None = None,
        relation: str | None = None,
        q: str | None = None,
        industry: str | None = None,
    ) -> list[Partner]:
        sql, args = "SELECT industry, data FROM partners WHERE 1=1", []
        if industry:
            sql += " AND industry = ?"
            args.append(industry)
        if relation:
            sql += " AND relation = ?"
            args.append(relation)
        sql += " ORDER BY industry, relation, company, contact"
        partners = [
            Partner(**{**json.loads(data), "industry": ind})
            for ind, data in self.conn.execute(sql, args)
        ]
        if category:
            partners = [p for p in partners if category in p.categories]
        if q:
            fields = ("company", "contact", "trade", "area", "address", "note")
            partners = [p for p in partners if any(q in getattr(p, f) for f in fields)]
        return partners

    # --- 集計 -------------------------------------------------------------

    def summary(self, month: str | None = None, industry: str | None = None) -> dict:
        """件数は created_at の月、対応時間はイベント `at` の月で集計する。"""
        logs = self.list(industry=industry)
        in_month = (lambda s: s[:7] == month) if month else (lambda s: True)

        created = [l for l in logs if in_month(l.created_at)]
        events = [(l, e) for l in logs for e in l.events if in_month(e.at)]

        by_band = {b: 0 for b in BANDS}
        by_action: Counter[str] = Counter()
        by_actor: Counter[str] = Counter()
        by_category_minutes: Counter[str] = Counter()
        by_industry_minutes: Counter[str] = Counter()
        for l, e in events:
            by_band[e.time_band] += e.minutes
            by_action[e.action] += e.minutes
            by_actor[e.actor or "(未記入)"] += e.minutes
            by_category_minutes[l.category] += e.minutes
            by_industry_minutes[l.industry] += e.minutes

        total = sum(by_band.values())
        off = total - by_band["所定内"]
        return {
            "month": month or "all",
            "industry": industry or "all",
            "trouble_count": len(created),
            "by_industry": dict(Counter(l.industry for l in created)),
            "by_category": dict(Counter(l.category for l in created)),
            "by_status": dict(Counter(l.status for l in created)),
            "total_minutes": total,
            "off_hours_minutes": off,
            "off_hours_ratio": round(off / total, 3) if total else 0.0,
            "minutes_by_band": by_band,
            "minutes_by_action": dict(by_action),
            "minutes_by_actor": dict(by_actor),
            "minutes_by_category": dict(by_category_minutes),
            "minutes_by_industry": dict(by_industry_minutes),
        }
