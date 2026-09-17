#!/usr/bin/env python3
"""docs/archive/*.html をスキャンし、日付ごとに選べる一覧ページ docs/index.html を再生成する。

使い方: 新しいページを生成したら、
  1. output/page_YYYY-MM-DD_slot.html を docs/archive/YYYY-MM-DD_slot.html にコピー
  2. このスクリプトを実行して docs/index.html を更新
"""
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = BASE_DIR / "docs" / "archive"
INDEX_PATH = BASE_DIR / "docs" / "index.html"

SLOT_LABEL = {"morning": "朝", "night": "夜"}
FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(morning|night)\.html$")


def collect_entries():
    entries = []
    for f in ARCHIVE_DIR.glob("*.html"):
        m = FILENAME_RE.match(f.name)
        if not m:
            continue
        date, slot = m.group(1), m.group(2)
        entries.append((date, slot, f.name))
    # 新しい日付が先、同じ日付なら夜が先
    entries.sort(key=lambda e: (e[0], e[1]), reverse=True)
    return entries


def build_html(entries):
    if not entries:
        rows = "<p>まだ選定履歴がありません。</p>"
    else:
        latest_date, latest_slot, latest_file = entries[0]
        items = []
        for date, slot, fname in entries:
            label = f"{date[5:7]}/{date[8:10]} {SLOT_LABEL.get(slot, slot)}の選定"
            is_latest = (date, slot) == (latest_date, latest_slot)
            badge = ' <span class="badge">最新</span>' if is_latest else ""
            items.append(
                f'<li><a href="archive/{fname}">{label}</a>{badge}</li>'
            )
        rows = "<ul class=\"archive-list\">\n" + "\n".join(items) + "\n</ul>"

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>楽天ROOM投稿リスト - 選定履歴一覧</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", sans-serif;
         background: #f6f3ee; color: #23211d; margin: 0; padding: 24px 16px; }}
  h1 {{ font-size: 1.2rem; margin: 0 0 16px; }}
  .archive-list {{ list-style: none; padding: 0; margin: 0; max-width: 480px; }}
  .archive-list li {{ margin-bottom: 10px; }}
  .archive-list a {{ display: block; padding: 14px 16px; background: #fff; border-radius: 10px;
                     color: #23211d; text-decoration: none; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .badge {{ display: inline-block; margin-left: 8px; padding: 2px 8px; background: #e0562c;
            color: #fff; border-radius: 999px; font-size: 0.75rem; }}
  p.note {{ color: #6b6459; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>🛍️ 楽天ROOM投稿リスト — 選定履歴一覧</h1>
<p class="note">日付/枠を選んでください。</p>
{rows}
</body>
</html>
"""


def main():
    entries = collect_entries()
    INDEX_PATH.write_text(build_html(entries), encoding="utf-8")
    print(f"docs/index.html を再生成しました({len(entries)}件)")


if __name__ == "__main__":
    main()
