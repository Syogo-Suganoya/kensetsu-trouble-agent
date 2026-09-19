"""トラブルログCLI。Skill から呼び出しやすいよう、出力はすべて JSON。

使用例:
  python -m troublelog industries
  python -m troublelog new --json intake.json --industry logistics
  echo '{...}' | python -m troublelog new --json -
  python -m troublelog event TR-20260915-001 --action 連絡 --minutes 15 --actor 田中 --note "元請に電話"
  python -m troublelog draft TR-20260915-001 --type 元請報告 --file draft.md
  python -m troublelog status TR-20260915-001 --set 解決
  python -m troublelog show TR-20260915-001
  python -m troublelog list --status 対応中
  python -m troublelog summary --month 2026-09
  python -m troublelog partner import --csv examples/construction/partners_sample.csv --industry construction
  python -m troublelog partner list --category 資材遅延・不足 --industry construction
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .industry import default_industry_id, get_industry, load_industries
from .models import STATUSES, ValidationError
from .partners import CsvImportError, read_partners_csv
from .store import NotFoundError, Store


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _add_industry(s: argparse.ArgumentParser, help_text: str) -> None:
    s.add_argument("--industry", help=f"{help_text}（{'/'.join(load_industries())}）")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="troublelog", description="現場トラブル対応ログ（業種パック対応）")
    p.add_argument("--db", help="SQLiteファイルのパス（既定: data/troubles.db / 環境変数 TROUBLELOG_DB）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("industries", help="業種パックの一覧／定義（分類・ロール・ドラフト種別など）")
    s.add_argument("industry_id", nargs="?")

    s = sub.add_parser("new", help="ヒアリング結果からトラブルを登録")
    s.add_argument("--json", required=True, help="入力JSONファイル（- で標準入力）")
    _add_industry(s, "業種。入力JSONの industry が優先、省略時は環境変数 TROUBLELOG_INDUSTRY → construction")

    s = sub.add_parser("event", help="対応履歴を追加")
    s.add_argument("trouble_id")
    s.add_argument("--action", required=True, help="対応種別（業種ごとの一覧は industries で確認）")
    s.add_argument("--minutes", required=True, type=int)
    s.add_argument("--at", help="開始日時 ISO8601（省略時は現在時刻）")
    s.add_argument("--actor", default="")
    s.add_argument("--note", default="")

    s = sub.add_parser("draft", help="生成した文面を保存")
    s.add_argument("trouble_id")
    s.add_argument("--type", required=True, help="ドラフト種別（業種ごとの一覧は industries で確認）")
    s.add_argument("--file", required=True, help="文面ファイル（- で標準入力）")

    s = sub.add_parser("status", help="ステータス変更")
    s.add_argument("trouble_id")
    s.add_argument("--set", required=True, choices=STATUSES, dest="value")

    s = sub.add_parser("show", help="1件表示")
    s.add_argument("trouble_id")

    s = sub.add_parser("list", help="一覧")
    s.add_argument("--status", choices=STATUSES)
    s.add_argument("--since", help="この日時以降に登録されたもの（例: 2026-09-01）")
    _add_industry(s, "業種で絞り込み")

    s = sub.add_parser("summary", help="集計（件数・対応時間・時間外時間）")
    s.add_argument("--month", help="YYYY-MM")
    _add_industry(s, "業種で絞り込み（省略時は全業種合算）")

    s = sub.add_parser("partner", help="取引先（CSVインポート・検索）")
    psub = s.add_subparsers(dest="partner_cmd", required=True)
    ps = psub.add_parser("import", help="取引先CSVを取り込む")
    ps.add_argument("--csv", required=True)
    ps.add_argument("--encoding", default="auto", help="auto（UTF-8/Shift_JIS自動判定）/ utf-8 / cp932")
    ps.add_argument("--replace", action="store_true", help="その業種の既存の取引先を全削除してから取り込む")
    _add_industry(ps, "取り込む業種。取引区分・対応分類はこの業種の定義で検証（省略時は TROUBLELOG_INDUSTRY → construction）")
    ps = psub.add_parser("list", help="取引先を検索")
    ps.add_argument("--category", help="対応できるトラブル分類")
    ps.add_argument("--relation", help="取引区分")
    ps.add_argument("--q", help="会社名・担当者・業種・エリア・所在地・備考の部分一致")
    _add_industry(ps, "業種で絞り込み")

    return p


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(args.db)
    try:
        if args.cmd == "industries":
            if args.industry_id:
                _print(get_industry(args.industry_id).to_dict())
            else:
                _print({"default": default_industry_id(),
                        "industries": [{"id": i.id, "name": i.name, "description": i.description}
                                       for i in load_industries().values()]})
        elif args.cmd == "new":
            _print(store.create(json.loads(_read_text(args.json)), args.industry).to_dict())
        elif args.cmd == "event":
            log = store.add_event(
                args.trouble_id, args.action, args.minutes, args.at, args.actor, args.note
            )
            _print({"trouble_id": log.trouble_id, "status": log.status,
                    "event": vars(log.events[-1]), "total_minutes": log.total_minutes})
        elif args.cmd == "draft":
            log = store.add_draft(args.trouble_id, args.type, _read_text(args.file))
            _print({"trouble_id": log.trouble_id, "drafts": len(log.drafts),
                    "saved": vars(log.drafts[-1])})
        elif args.cmd == "status":
            log = store.set_status(args.trouble_id, args.value)
            _print({"trouble_id": log.trouble_id, "status": log.status,
                    "resolved_at": log.resolved_at})
        elif args.cmd == "show":
            _print(store.get(args.trouble_id).to_dict())
        elif args.cmd == "list":
            _print([
                {"trouble_id": l.trouble_id, "industry": l.industry,
                 "created_at": l.created_at, "site": l.site,
                 "category": l.category, "severity": l.severity, "status": l.status,
                 "what": l.summary.what, "total_minutes": l.total_minutes}
                for l in store.list(args.status, args.since, args.industry)
            ])
        elif args.cmd == "summary":
            _print(store.summary(args.month, args.industry))
        elif args.cmd == "partner" and args.partner_cmd == "import":
            industry = get_industry(args.industry).id
            partners, ignored = read_partners_csv(args.csv, industry, args.encoding)
            result = store.import_partners(partners, industry, replace=args.replace)
            _print({**result, "ignored_columns": ignored})
        elif args.cmd == "partner" and args.partner_cmd == "list":
            _print([asdict(p) for p in store.list_partners(
                args.category, args.relation, args.q, args.industry)])
    except CsvImportError as e:
        _print({"error": str(e), "details": e.errors})
        return 1
    except FileNotFoundError as e:
        _print({"error": f"ファイルが見つかりません: {e.filename}"})
        return 1
    except (ValidationError, NotFoundError, json.JSONDecodeError, ValueError) as e:
        _print({"error": str(e)})
        return 1
    finally:
        store.close()
    return 0


def main() -> None:
    sys.exit(run())
