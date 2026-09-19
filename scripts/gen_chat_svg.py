#!/usr/bin/env python3
"""README の会話例（チャット画面風）を SVG で生成する。

使い方: python3 scripts/gen_chat_svg.py
出力先: docs/images/chat-intake.svg / chat-log.svg / chat-summary.svg

セリフを変えるときは下の CHATS を編集する。1要素が1吹き出しで、
("me" | "ai", [行, 行, ...])。行の折り返しは自動では行わないので、
1行はおよそ22文字（全角）までにする。
"""

from pathlib import Path
from xml.sax.saxutils import escape

W = 620              # 画像の幅
PAD = 18             # 外側の余白
GAP = 12             # 吹き出しの間隔
LINE_H = 24          # 行の高さ
FONT = 15            # 文字サイズ
PAD_X, PAD_Y = 14, 11  # 吹き出し内側の余白
RADIUS = 14
CHAR_W = FONT        # 全角1文字の幅の目安
BG = "#EAEFF4"
ME_FILL, ME_STROKE, ME_TEXT = "#A9E36B", "#93CF56", "#13300B"
AI_FILL, AI_STROKE, AI_TEXT = "#FFFFFF", "#D3DBE2", "#17232D"
FONT_FAMILY = (
    "'Hiragino Sans','Hiragino Kaku Gothic ProN','Noto Sans JP','Yu Gothic',"
    "'Meiryo',system-ui,sans-serif"
)


def text_width(line: str) -> float:
    """全角を1文字、半角を0.55文字として幅を見積もる。"""
    n = sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in line)
    return n * CHAR_W


def render(chat: list[tuple[str, list[str]]]) -> str:
    bubbles, y = [], PAD
    for who, lines in chat:
        bw = max(text_width(l) for l in lines) + PAD_X * 2
        bh = LINE_H * len(lines) + PAD_Y * 2
        x = W - PAD - bw if who == "me" else PAD
        bubbles.append((who, lines, x, y, bw, bh))
        y += bh + GAP
    height = y - GAP + PAD

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height:.0f}" '
        f'viewBox="0 0 {W} {height:.0f}" role="img">',
        f'<rect width="{W}" height="{height:.0f}" fill="{BG}"/>',
        f'<style>text{{font-family:{FONT_FAMILY};font-size:{FONT}px}}</style>',
    ]
    for who, lines, x, y, bw, bh in bubbles:
        fill, stroke, color = (
            (ME_FILL, ME_STROKE, ME_TEXT) if who == "me" else (AI_FILL, AI_STROKE, AI_TEXT)
        )
        out.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{bw:.0f}" height="{bh:.0f}" rx="{RADIUS}" '
            f'fill="{fill}" stroke="{stroke}"/>'
        )
        for i, line in enumerate(lines):
            ty = y + PAD_Y + LINE_H * i + FONT
            out.append(
                f'<text x="{x + PAD_X:.0f}" y="{ty:.0f}" fill="{color}">{escape(line)}</text>'
            )
    out.append("</svg>")
    return "\n".join(out) + "\n"


CHATS: dict[str, list[tuple[str, list[str]]]] = {
    "chat-intake": [
        ("me", ["生コン来ない、午後打設無理かも"]),
        ("ai", ["状況を整理します。2点だけ教えてください。",
                "① 場所は何階・どこですか？",
                "② 待機している人数と車両は？"]),
        ("me", ["3階スラブ。6人とポンプ車"]),
        ("ai", ["【トラブル受付内容】",
                "現場：〇〇マンション新築工事",
                "分類：資材遅延・不足（重要度：高）",
                "何が：13時打設予定の生コンが未着",
                "影響：打設班6名・ポンプ車が待機中",
                "この内容で登録してよいですか？"]),
        ("me", ["OK"]),
        ("ai", ["登録しました。TR-20260915-001",
                "ヒアリングの3分も記録しました。"]),
    ],
    "chat-log": [
        ("me", ["元請に電話で20分説明した"]),
        ("ai", ["記録しました。時間外・20分",
                "この件の対応は累計43分です。"]),
        ("me", ["昨日の夜23時から1時間、是正の報告書作った"]),
        ("ai", ["記録しました。深夜・60分"]),
        ("me", ["センターで2時間待って、そのあと棚入れ40分",
                "※運送の場合"]),
        ("ai", ["荷待ち120分と附帯作業40分に分けて",
                "記録しました。"]),
        ("me", ["あの件は解決した"]),
        ("ai", ["ステータスを解決にしました。"]),
    ],
    "chat-summary": [
        ("me", ["今月どれくらい対応に時間使った？"]),
        ("ai", ["9月のトラブル対応サマリ",
                "件数：8件（解決5／対応中3）",
                "対応時間：14時間20分",
                "うち時間外：9時間40分（67%）",
                "気づき：書類作成の7割が休日に発生しています"]),
    ],
}


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent.parent / "docs" / "images"
    for name, chat in CHATS.items():
        path = out_dir / f"{name}.svg"
        path.write_text(render(chat), encoding="utf-8")
        print(path)
