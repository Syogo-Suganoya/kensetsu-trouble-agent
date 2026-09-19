"""取引先CSVの読み込み。

Excel で管理している取引先リストをそのまま取り込めるよう、
ヘッダーは日本語、文字コードは UTF-8（BOM有無）／Shift_JIS(cp932) を自動判定する。
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from .industry import DEFAULT_INDUSTRY
from .models import Partner, ValidationError

# CSVヘッダー → Partner のフィールド
COLUMNS = {
    "会社名": "company",
    "取引区分": "relation",
    "業種": "trade",
    "対応分類": "categories",
    "担当者": "contact",
    "役職": "title",
    "電話": "phone",
    "メール": "email",
    "LINE可": "line",
    "所在地": "address",
    "対応エリア": "area",
    "備考": "note",
}
REQUIRED = ("会社名", "取引区分")
_SPLIT = re.compile(r"[;；、,，|/／]")
_TRUE = {"可", "○", "〇", "はい", "yes", "true", "1"}
_FALSE = {"不可", "×", "いいえ", "no", "false", "0"}


class CsvImportError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__(f"CSVに{len(errors)}件のエラーがあります")
        self.errors = errors


def decode(raw: bytes, encoding: str = "auto") -> str:
    if encoding != "auto":
        return raw.decode(encoding)
    for enc in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise CsvImportError(["文字コードを判定できません（UTF-8 か Shift_JIS で保存してください）"])


def _parse_line(value: str) -> bool | None:
    v = value.strip().lower()
    if not v:
        return None
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValidationError(f"LINE可 は 可/不可 のいずれか: {value!r}")


def parse_partners(text: str, industry: str = DEFAULT_INDUSTRY) -> list[Partner]:
    """CSVテキストを Partner のリストに変換する。取引区分・対応分類は industry の定義で検証する。
    1件でも不正なら全件エラーを集めて送出。"""
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers

    missing = [h for h in REQUIRED if h not in headers]
    if missing:
        raise CsvImportError([f"必須列がありません: {', '.join(missing)}（ヘッダー: {', '.join(headers)}）"])

    partners: list[Partner] = []
    errors: list[str] = []
    seen: dict[tuple[str, str], int] = {}
    for lineno, row in enumerate(reader, start=2):  # 1行目はヘッダー
        values = {k: (v or "").strip() for k, v in row.items() if k in COLUMNS}
        if not any(values.values()):
            continue  # 空行
        try:
            p = Partner(
                company=values.get("会社名", ""),
                relation=values.get("取引区分", ""),
                trade=values.get("業種", ""),
                categories=[c.strip() for c in _SPLIT.split(values.get("対応分類", "")) if c.strip()],
                contact=values.get("担当者", ""),
                title=values.get("役職", ""),
                phone=values.get("電話", ""),
                email=values.get("メール", ""),
                line=_parse_line(values.get("LINE可", "")),
                address=values.get("所在地", ""),
                area=values.get("対応エリア", ""),
                note=values.get("備考", ""),
                industry=industry,
            )
            p.validate()
        except ValidationError as e:
            errors.append(f"{lineno}行目: {e}")
            continue
        key = (p.company, p.contact)
        if key in seen:
            errors.append(f"{lineno}行目: 会社名＋担当者が{seen[key]}行目と重複: {p.company} {p.contact}")
            continue
        seen[key] = lineno
        partners.append(p)

    if errors:
        raise CsvImportError(errors)
    return partners


def unknown_columns(text: str) -> list[str]:
    """取り込み対象外の列（無視される列）。"""
    headers = next(csv.reader(io.StringIO(text)), [])
    return [h.strip() for h in headers if h.strip() and h.strip() not in COLUMNS]


def read_partners_csv(
    path: str | Path, industry: str = DEFAULT_INDUSTRY, encoding: str = "auto"
) -> tuple[list[Partner], list[str]]:
    text = decode(Path(path).read_bytes(), encoding)
    return parse_partners(text, industry), unknown_columns(text)
