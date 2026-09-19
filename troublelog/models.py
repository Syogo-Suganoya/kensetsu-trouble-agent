"""トラブルログのデータモデル（全業種共通）。

業種ごとに異なる選択肢（ロール・分類・ドラフト種別・対応種別・取引区分）は
industry.Industry から受け取って検証する。
後続フェーズ（協力会社提案・サビ残レポート）は
すべてこの TroubleLog と Partner（取引先）を参照する前提でフィールドを定義している。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .industry import DEFAULT_INDUSTRY, Industry, get_industry

SEVERITIES = ("高", "中", "低")
STATUSES = ("受付", "対応中", "解決")


class ValidationError(ValueError):
    pass


def _check(value: Any, allowed: tuple[str, ...], name: str) -> None:
    if value not in allowed:
        raise ValidationError(f"{name} は {'/'.join(allowed)} のいずれか: {value!r}")


def _industry(industry_id: str) -> Industry:
    try:
        return get_industry(industry_id)
    except ValueError as e:
        raise ValidationError(str(e)) from e


@dataclass
class Reporter:
    role: str
    company: str = ""
    name: str = ""
    tier: int | None = None  # 何次請けか（最上位=0）。意味は Industry.tier_label

    def validate(self, ind: Industry) -> None:
        _check(self.role, ind.roles, "reporter.role")
        if self.tier is not None and (not isinstance(self.tier, int) or self.tier < 0):
            raise ValidationError(f"reporter.tier は0以上の整数: {self.tier!r}")


@dataclass
class Summary:
    what: str
    when: str = ""
    where: str = ""
    impact: str = ""
    stakeholders: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.what.strip():
            raise ValidationError("summary.what は必須")


@dataclass
class Event:
    at: str  # ISO8601
    action: str
    minutes: int
    actor: str = ""
    note: str = ""
    time_band: str = ""  # 所定内/時間外/深夜/休日（timecalc で自動付与）
    off_hours: bool = False

    def validate(self, ind: Industry) -> None:
        _check(self.action, ind.actions, "event.action")
        if not isinstance(self.minutes, int) or self.minutes < 0:
            raise ValidationError(f"event.minutes は0以上の整数: {self.minutes!r}")


@dataclass
class Draft:
    type: str
    text: str
    created_at: str

    def validate(self, ind: Industry) -> None:
        _check(self.type, ind.draft_types, "draft.type")
        if not self.text.strip():
            raise ValidationError("draft.text は必須")


@dataclass
class Partner:
    """取引先（CSVインポート対象）。会社名＋担当者で一意。"""

    company: str
    relation: str
    trade: str = ""
    categories: list[str] = field(default_factory=list)  # 対応できるトラブル分類
    contact: str = ""
    title: str = ""
    phone: str = ""
    email: str = ""
    line: bool | None = None
    address: str = ""
    area: str = ""
    note: str = ""
    industry: str = DEFAULT_INDUSTRY

    def validate(self) -> None:
        ind = _industry(self.industry)
        if not self.company.strip():
            raise ValidationError("会社名 は必須")
        _check(self.relation, ind.relations, "取引区分")
        for c in self.categories:
            _check(c, ind.categories, "対応分類")


@dataclass
class TroubleLog:
    trouble_id: str
    created_at: str
    reporter: Reporter
    site: str
    category: str
    summary: Summary
    industry: str = DEFAULT_INDUSTRY
    subcategory: str = ""
    severity: str = "中"
    status: str = "受付"
    raw_report: str = ""  # 最初の一言報告（原文）
    events: list[Event] = field(default_factory=list)
    drafts: list[Draft] = field(default_factory=list)
    resolved_at: str | None = None

    def validate(self) -> None:
        ind = _industry(self.industry)
        self.reporter.validate(ind)
        self.summary.validate()
        _check(self.category, ind.categories, "category")
        _check(self.severity, SEVERITIES, "severity")
        _check(self.status, STATUSES, "status")
        for e in self.events:
            e.validate(ind)
        for d in self.drafts:
            d.validate(ind)

    @property
    def total_minutes(self) -> int:
        return sum(e.minutes for e in self.events)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total_minutes"] = self.total_minutes
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TroubleLog:
        return cls(
            trouble_id=d["trouble_id"],
            created_at=d["created_at"],
            reporter=Reporter(**d["reporter"]),
            site=d.get("site", ""),
            category=d["category"],
            summary=Summary(**d["summary"]),
            industry=d.get("industry") or DEFAULT_INDUSTRY,  # 業種導入前のログは建設業
            subcategory=d.get("subcategory", ""),
            severity=d.get("severity", "中"),
            status=d.get("status", "受付"),
            raw_report=d.get("raw_report", ""),
            events=[Event(**e) for e in d.get("events", [])],
            drafts=[Draft(**x) for x in d.get("drafts", [])],
            resolved_at=d.get("resolved_at"),
        )
