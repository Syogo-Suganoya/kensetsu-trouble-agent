"""業種パック。

トラブルログのデータモデル・時間集計・取引先管理は全業種共通とし、
業種ごとに差し替えるのは industries/<id>.json の定義
（ロール・取引区分・トラブル分類・ドラフト種別・追加の対応種別・所定時間）と、
Skill 側の references / templates だけにする。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent / "industries"
DEFAULT_INDUSTRY = "construction"
BASE_ACTIONS = ("ヒアリング", "ドラフト生成", "連絡", "調整", "書類作成", "現場対応", "その他")


class UnknownIndustryError(ValueError):
    pass


@dataclass(frozen=True)
class Industry:
    id: str
    name: str
    description: str
    roles: tuple[str, ...]
    tier_label: str
    relations: tuple[str, ...]
    categories: tuple[str, ...]
    draft_types: tuple[str, ...]  # [上位への報告, 取引先への依頼, 対応案] の順
    extra_actions: tuple[str, ...]
    work_hours: tuple[int, int]

    @property
    def actions(self) -> tuple[str, ...]:
        return BASE_ACTIONS[:-1] + self.extra_actions + BASE_ACTIONS[-1:]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "roles": list(self.roles),
            "tier_label": self.tier_label,
            "relations": list(self.relations),
            "categories": list(self.categories),
            "draft_types": list(self.draft_types),
            "actions": list(self.actions),
            "work_hours": list(self.work_hours),
        }


@lru_cache(maxsize=None)
def load_industries() -> dict[str, Industry]:
    packs = {}
    for path in sorted(PACK_DIR.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        packs[d["id"]] = Industry(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            roles=tuple(d["roles"]),
            tier_label=d.get("tier_label", ""),
            relations=tuple(d["relations"]),
            categories=tuple(d["categories"]),
            draft_types=tuple(d["draft_types"]),
            extra_actions=tuple(d.get("extra_actions", [])),
            work_hours=tuple(d.get("work_hours", [8, 17])),
        )
    return packs


def default_industry_id() -> str:
    return os.environ.get("TROUBLELOG_INDUSTRY") or DEFAULT_INDUSTRY


def get_industry(industry_id: str | None = None) -> Industry:
    industry_id = industry_id or default_industry_id()
    packs = load_industries()
    if industry_id not in packs:
        raise UnknownIndustryError(
            f"業種 は {'/'.join(packs)} のいずれか: {industry_id!r}"
        )
    return packs[industry_id]
