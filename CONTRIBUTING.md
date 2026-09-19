# 開発者向け情報

このドキュメントは開発・カスタマイズ向け。使い方は [README.md](README.md) を参照。

## 構成

| パス | 内容 |
|---|---|
| `.claude/skills/trouble-intake/` | Skill A：業種特定→安全確認→分類→不足項目だけヒアリング→ログ登録 |
| `.claude/skills/trouble-draft/` | Skill B：3種の一次対応ドラフト生成（共通トーン＋業種別トーン・テンプレート） |
| `.claude/skills/trouble-log/` | Skill C：自然文から対応時間を記録、ステータス更新、月次集計 |
| `troublelog/` | トラブルログCLI（標準ライブラリのみ、出力はJSON） |
| `troublelog/industries/*.json` | 業種パック定義 |
| `schema/trouble_log.schema.json` | トラブルログのJSON Schema |
| `examples/<業種ID>/cases/` | 検証用の架空トラブル事例（期待分類・確認ポイント付き）建設8件・製造6件・運送6件 |
| `examples/<業種ID>/partners_sample.csv` | 取引先CSVのダミー（建設20件・製造15件・運送15件） |
| `examples/<業種ID>/intake_sample.json` | 登録JSONのサンプル |
| `scripts/package_skills.sh` | Claude.ai アップロード用に Skill を zip 化 |
| `scripts/gen_chat_svg.py` | README の会話例（チャット風SVG）を生成。セリフはこのファイル内の `CHATS` を編集して再実行する |
| `docs/illustration-prompts.md` | README 挿絵の画像生成プロンプト（生成画像は `docs/images/` に置く） |

## 業種パック

| 業種ID | 業種 | ロール | ドラフト種別 | 業種固有の対応種別 |
|---|---|---|---|---|
| `construction` | 建設業 | 職人 / 協力会社 / 元請 | 元請報告 / 協力会社依頼 / 対応案 | ― |
| `manufacturing` | 中小製造業サプライヤー | 作業者 / サプライヤー / 発注元 | 発注元報告 / 仕入先・外注先依頼 / 対応案 | 選別・手直し |
| `logistics` | 物流（トラック運送） | ドライバー / 運送会社 / 荷主・元請 | 荷主・元請報告 / 協力運送会社依頼 / 対応案 | 荷待ち / 附帯作業 |

分類・取引区分の一覧は `python3 -m troublelog industries <業種ID>` で確認できる。

**共通化している部分**：トラブルログのデータモデル、対応時間・時間帯（所定内/時間外/深夜/休日）の集計、取引先CSV、Skill の手順（受付→ドラフト→記録）、共通トーンルール（謝りすぎない・記録を残す・無償の帳尻合わせを約束しない）。
**業種ごとに差し替える部分**：

| 差し替え対象 | 場所 |
|---|---|
| ロール・取引区分・トラブル分類・ドラフト種別・追加の対応種別・所定時間 | `troublelog/industries/<業種ID>.json` |
| 分類表・ヒアリング項目・安全確認 | `.claude/skills/trouble-intake/references/<業種ID>/` |
| 業種トーン・分類別の重点 | `.claude/skills/trouble-draft/references/<業種ID>/` |
| ①上位報告 ②取引先依頼 ③対応案 のテンプレート | `.claude/skills/trouble-draft/templates/<業種ID>/` |
| 事例・取引先CSV・登録サンプル | `examples/<業種ID>/` |

### 業種を追加するには

1. `troublelog/industries/<新ID>.json` を既存パックをコピーして作る。
2. 上表の references / templates / examples を `<新ID>` フォルダで用意する。
3. `python3 -m unittest discover -s tests -t .` を実行する。`tests/test_industry.py` の `test_expected_packs` に新IDを足すと、ファイルの欠け・分類名の不一致（JSON と `categories.md`／`focus.md`）・サンプルデータの不正を検出する。

## セットアップと実行（詳細）

Skill は `.claude/skills/` にあり、このディレクトリで Claude Code を開くと自動で認識される。明示的に呼ぶ場合は `/trouble-intake` `/trouble-draft` `/trouble-log`。利用者向けの手順は [README の使い方](README.md#使い方) を参照。

### CLI を直接使う

```bash
python3 -m troublelog industries                       # 業種パック一覧
python3 -m troublelog industries logistics             # 分類・ロール・ドラフト種別など
python3 -m troublelog new --json examples/logistics/intake_sample.json
python3 -m troublelog event TR-20260915-001 --action 荷待ち --minutes 130 --at 2026-09-15T09:00:00+09:00 --actor 佐々木
python3 -m troublelog draft TR-20260915-001 --type 荷主・元請報告 --file draft.md
python3 -m troublelog status TR-20260915-001 --set 解決
python3 -m troublelog show TR-20260915-001
python3 -m troublelog list --status 対応中 --industry logistics
python3 -m troublelog summary --month 2026-09 --industry logistics   # --industry 省略で全業種合算
```

業種は、登録JSONの `industry` → `--industry` → 環境変数 `TROUBLELOG_INDUSTRY` → `construction` の順で決まる。
業種導入前に作ったDB（`data/troubles.db`）は初回起動時に自動で移行され、既存データは `construction` になる。

### 取引先データのCSVインポート

取り込んだ取引先は、ドラフトの宛名・連絡先の補完と、依頼先候補の提示（分類で絞り込み）に使われる。取引先は業種ごとに管理する。

```bash
python3 -m troublelog partner import --industry construction --csv examples/construction/partners_sample.csv   # 追加・上書き
python3 -m troublelog partner import --industry logistics --csv 取引先.csv --replace                           # その業種だけ全件入れ替え
python3 -m troublelog partner list --industry construction --category 資材遅延・不足 --relation メーカー・商社
python3 -m troublelog partner list --industry logistics --q 冷凍
```

- 文字コードは UTF-8（BOM有無）／Shift_JIS を自動判定（Excel の「CSV UTF-8」「CSV（コンマ区切り）」どちらでも可）。
- 1行目はヘッダー。同じ業種で**会社名＋担当者**が同じ行は上書き。1件でも不正な行があれば何も取り込まず、行番号付きでエラーを返す。
- 下表以外の列は無視される（結果の `ignored_columns` に表示）。列構成は全業種共通。

| 列名 | 必須 | 値 |
|---|---|---|
| 会社名 | ○ | |
| 取引区分 | ○ | 建設：`元請` / `協力会社` / `メーカー・商社` / `その他`<br>製造：`発注元` / `仕入先・外注先` / `物流業者` / `その他`<br>運送：`荷主` / `元請運送会社` / `協力運送会社` / `着荷主・倉庫` / `その他` |
| 業種 | | 取引先の業種・工種（例：鉄筋工事、表面処理、冷凍冷蔵車） |
| 対応分類 | | その業種のトラブル分類（`references/<業種ID>/categories.md`）を `;` や `、` 区切りで複数可 |
| 担当者 / 役職 | | 同じ会社で担当者が複数なら行を分ける |
| 電話 / メール | | |
| LINE可 | | `可` / `不可`（`○` `×` も可）、空欄は不明 |
| 所在地 / 対応エリア | | |
| 備考 | | 依頼の締切・条件など（依頼文に反映される） |

| 環境変数 | 既定 | 説明 |
|---|---|---|
| `TROUBLELOG_DB` | `data/troubles.db` | SQLite ファイル |
| `TROUBLELOG_INDUSTRY` | `construction` | 既定の業種 |
| `TROUBLELOG_WORK_START` / `TROUBLELOG_WORK_END` | 業種パックの `work_hours`（全業種 `8` / `17`） | 所定時間（時）。設定すると業種パックより優先 |

### 時間帯の区分

イベント開始時刻で判定：`休日`（土日・祝日・振替休日・国民の休日）／`深夜`（平日22〜5時）／`時間外`（平日の所定外）／`所定内`。
`所定内` 以外を「時間外（サビ残相当の候補）」として集計する。

## テスト

```bash
python3 -m unittest discover -s tests -t .
```
