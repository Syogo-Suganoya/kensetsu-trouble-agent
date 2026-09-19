---
name: trouble-draft
description: 登録済みの現場トラブル（trouble_id）から、①上位（元請／発注元／荷主・元請運送会社）への状況報告文 ②取引先（協力会社／仕入先・外注先／協力運送会社）への相談・依頼文 ③今後の対応案 の3種の一次対応ドラフトを業種に合わせて作成し、ログに保存する。trouble-intake の受付後や、「元請への報告文を作って」「発注元に何て言えばいい？」「荷主に遅延の連絡を書いて」「協力会社に送る文面がほしい」「どう対応すればいい？」と言われたとき、または /trouble-draft で呼ばれたときに使う。
---

# 一次対応ドラフト生成（Skill B）

夜や休日に下請・現場中堅が時間をかけて書いている「報告文・お願い文」を肩代わりする。
**事実ベース・短く・送ればそのまま使える**文面を作ること。

## 手順

1. **ログ読み込み**：`trouble_id` があれば取得する。無ければ直前の受付内容を使う（無ければ `trouble-intake` を先に行う）。

   ```bash
   python3 -m troublelog show <trouble_id>
   python3 -m troublelog industries <industry>
   ```

   ログの `industry` で業種パックが決まる。`industries` の `draft_types` が ①②③ の保存名（例：建設 `元請報告`／`協力会社依頼`／`対応案`）。
   作業開始時刻をメモする（ドラフト作成時間の記録に使う）。

2. **業種パックを読む**（`<industry>` は業種ID）
   - 共通トーン：[references/common-tone.md](references/common-tone.md)
   - 業種トーン：`references/<industry>/tone-guide.md`
   - 分類別の重点と読み替え：`references/<industry>/focus.md`
   - テンプレート：`templates/<industry>/upstream_report.md`（①）、`partner_request.md`（②）、`action_plan.md`（③）

   報告者のロール（`reporter.role` / `tier`）で宛先との力関係を判断し、`focus.md` の「読み替え」に従って①②の宛先を決める。

3. **宛先の特定**：`summary.stakeholders` と報告者の会社を取引先から引き、宛名（会社名・担当者・役職）と連絡手段（LINE可／メール／電話）を埋める。

   ```bash
   python3 -m troublelog partner list --industry <industry> --q "<会社名の一部>"
   ```

   - 見つかった情報はそのまま使い、`【要確認】` にしない。見つからない項目だけ `【要確認】`。
   - ②の依頼先が決まっていない場合（応援・代走・代替手配など）は、分類で候補を出し、対応エリアが現場に合うものを優先して**3件まで**を「会社名／業種／担当者／備考」で見せて選ばせる。備考の条件（「前日17時まで」等）は依頼文に反映する。取引区分は `industries <industry>` の `relations` から、依頼先にあたるものを選ぶ。

     ```bash
     python3 -m troublelog partner list --industry <industry> --category <category> --relation <取引区分>
     ```

   - 取引先が1件も登録されていなければ、`python3 -m troublelog partner import --industry <industry> --csv <ファイル>` で取り込めることを一言案内し、宛名は `【要確認】` のまま進める。

4. **3種を作成**（テンプレートに沿う。不要な見出しは削ってよい）
   - ①② は `focus.md` の表で、その分類の「必ず入れる」項目を漏らさない。
   - ② は LINE用（短文）とメール用の2形式を出す。
   - ③ は `focus.md` の「対応案の要点」を踏まえる。

5. **提示**：3種を見出し付きで続けて表示し、最後に一言だけ聞く。
   「修正したい箇所があれば言ってください（例：『もっと柔らかく』『費用の話は外して』）」
   ログにない事実（台数・数量・時刻・金額）が必要な箇所は `【要確認：〇〇】` と書き、埋めずに残す。

6. **保存**：ユーザーがOK（または修正完了）したら、`draft_types` の名前でそれぞれ保存し、作成時間を記録する。

   ```bash
   python3 -m troublelog draft <trouble_id> --type <draft_types[0]> --file - <<'EOF'
   （①の本文）
   EOF
   python3 -m troublelog draft <trouble_id> --type <draft_types[1]> --file - <<'EOF'
   （②の本文）
   EOF
   python3 -m troublelog draft <trouble_id> --type 対応案 --file - <<'EOF'
   （③の本文）
   EOF
   python3 -m troublelog event <trouble_id> --action ドラフト生成 --minutes <作業開始〜保存までの分> --at <作業開始時刻> --actor "<依頼者名>" --note "AIドラフト3種"
   ```

   コマンドが使えない環境では保存手順を省略し、文面だけ提示する。

7. **次の一手**：「送ったら『〇〇に送った』『〇〇に電話した、15分』のように教えてください。対応時間として記録します（trouble-log）」と伝える。
