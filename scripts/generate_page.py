#!/usr/bin/env python3
"""
選定商品+投稿文から、スマホで見やすい一覧HTMLページを生成する。

captions JSONの構造(copywriterが出力):
{
  "products": [ {itemCode, itemName, price, roomCaption}, ... 5件 ],
  "featured": {itemCode, itemName, reason, threadsCaption, xCaption},
  "dailyLifePosts": ["投稿文1", ... 5個]
}

使い方:
    python generate_page.py --selected ../output/selected_2026-08-31_morning.json \
                             --captions ../output/captions_2026-08-31_morning.json \
                             --out ../output/page_2026-08-31_morning.html \
                             --label "8/31 朝の選定"
"""
import argparse
import html
import json
import urllib.parse
from pathlib import Path


def product_url_of(item):
    """素の楽天商品ページURL(item.rakuten.co.jp/...)を返す。
    selectedに productUrl があればそれを、無ければ affiliateUrl の pc= から復元する。"""
    direct = item.get("productUrl")
    if direct:
        return direct
    aff = item.get("affiliateUrl") or item.get("itemUrl") or ""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(aff).query)
        pc = qs.get("pc", [""])[0]
        if pc.startswith("http"):
            return pc
    except Exception:
        pass
    return aff

TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{label} - 楽天ROOM投稿リスト</title>
<style>
:root {{
  --bg: #f6f3ee;
  --surface: #ffffff;
  --ink: #23211d;
  --ink-soft: #6b6459;
  --accent: #a8382c;
  --accent-ink: #fff6f2;
  --good: #3f7d58;
  --border: #e4ddd2;
  --chip-bg: #efe8db;
  color-scheme: light dark;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16140f;
    --surface: #211f1a;
    --ink: #ece7dc;
    --ink-soft: #a89e8d;
    --accent: #e0685a;
    --accent-ink: #1c0f0c;
    --good: #6fb98a;
    --border: #35322a;
    --chip-bg: #2a2721;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #16140f; --surface: #211f1a; --ink: #ece7dc; --ink-soft: #a89e8d;
  --accent: #e0685a; --accent-ink: #1c0f0c; --good: #6fb98a; --border: #35322a; --chip-bg: #2a2721;
}}
:root[data-theme="light"] {{
  --bg: #f6f3ee; --surface: #ffffff; --ink: #23211d; --ink-soft: #6b6459;
  --accent: #a8382c; --accent-ink: #fff6f2; --good: #3f7d58; --border: #e4ddd2; --chip-bg: #efe8db;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic Medium", "Noto Sans JP", sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 640px; margin: 0 auto; padding: 0 16px 40px; }}
header.top {{
  position: sticky; top: 0; z-index: 5; background: var(--bg);
  padding: 18px 16px 12px; border-bottom: 1px solid var(--border);
  display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
}}
header.top .eyebrow {{
  font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-soft);
  font-weight: 600; margin: 0 0 2px;
}}
header.top h1 {{ font-size: 1.25rem; margin: 0; font-weight: 700; letter-spacing: -0.01em; }}
header.top .count {{
  background: var(--chip-bg); color: var(--ink-soft); font-size: 0.78rem; font-weight: 600;
  padding: 5px 10px; border-radius: 999px; white-space: nowrap;
}}
h2.section-title {{ font-size: 0.95rem; font-weight: 700; margin: 24px 0 12px; }}
.cards {{ display: flex; flex-direction: column; gap: 16px; margin-top: 18px; }}
.card {{
  background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  padding: 16px; display: flex; flex-direction: column; gap: 12px;
}}
.card.featured {{ border-color: var(--accent); border-width: 2px; }}
.featured-badge {{
  align-self: flex-start; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.03em;
  color: var(--accent-ink); background: var(--accent); padding: 3px 9px; border-radius: 999px;
}}
.card-head {{ display: flex; gap: 12px; }}
.card-head img {{
  width: 76px; height: 76px; object-fit: cover; border-radius: 10px;
  border: 1px solid var(--border); background: var(--chip-bg); flex-shrink: 0;
}}
.card-head .info {{ min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4px; }}
.genre-chip {{
  align-self: flex-start; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.03em;
  color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent);
  padding: 2px 8px; border-radius: 999px;
}}
.name {{
  font-weight: 600; font-size: 0.94rem; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}}
.meta-row {{ display: flex; align-items: baseline; gap: 8px; font-size: 0.82rem; color: var(--ink-soft); }}
.price {{ font-variant-numeric: tabular-nums; color: var(--ink); font-weight: 700; font-size: 1.05rem; }}
.stars {{ letter-spacing: -1px; color: var(--accent); }}
.btn-open {{
  display: flex; align-items: center; justify-content: center; gap: 6px;
  background: var(--accent); color: var(--accent-ink); border: none; border-radius: 11px;
  padding: 12px; font-weight: 700; font-size: 0.92rem; text-decoration: none;
}}
.btn-open:active {{ opacity: 0.85; }}
.url-row {{
  display: flex; align-items: center; gap: 8px;
  background: var(--chip-bg); border-radius: 9px; padding: 8px 10px;
}}
.url-row a {{
  flex: 1; min-width: 0; font-size: 0.76rem; color: var(--accent);
  word-break: break-all; line-height: 1.45; text-decoration: none;
}}
.url-row a:active {{ text-decoration: underline; }}
.reason {{ font-size: 0.8rem; color: var(--ink-soft); }}
.caption-box {{ border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }}
.caption-head {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 10px; background: var(--chip-bg);
}}
.caption-head span {{
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-soft);
}}
.copy-btn {{
  background: var(--surface); border: 1px solid var(--border); color: var(--ink);
  border-radius: 7px; padding: 5px 11px; font-size: 0.76rem; font-weight: 600; cursor: pointer;
}}
.copy-btn:focus-visible, .btn-open:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.copy-btn.copied {{ background: var(--good); border-color: var(--good); color: #fff; }}
textarea {{
  width: 100%; display: block; border: none; padding: 10px; font-size: 0.85rem; line-height: 1.55;
  resize: vertical; min-height: 108px; font-family: inherit; background: var(--surface); color: var(--ink);
}}
textarea.short {{ min-height: 60px; }}
textarea:focus-visible {{ outline: 2px solid var(--accent); outline-offset: -2px; }}
footer.note {{ margin-top: 22px; font-size: 0.76rem; color: var(--ink-soft); text-align: center; line-height: 1.6; }}
@media (prefers-reduced-motion: no-preference) {{
  .copy-btn {{ transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease; }}
}}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div>
    <p class="eyebrow">楽天ROOM 投稿リスト</p>
    <h1>{label}</h1>
  </div>
  <span class="count">{count}件</span>
</header>

<h2 class="section-title">📦 商品(ROOM用、全{count}件)</h2>
<div class="cards">
{cards}
</div>

<h2 class="section-title">💬 今日のあるある投稿ネタ(商品リンクなし)</h2>
<div class="cards">
{daily_cards}
</div>

<footer class="note">商品ページを確認し、投稿文をコピーして手動で投稿してください。<br>Threads/Xの商品紹介は1日1件・あるある投稿と織り交ぜてスパム判定を避けてください。<br>価格・レビューは選定時点の実データです。</footer>
</div>
{script}
</body>
</html>
"""

CARD_TEMPLATE = """<div class="card{featured_class}">
  <div class="card-head">
    <img src="{image_url}" alt="{name_esc}" loading="lazy">
    <div class="info">
      {featured_badge}
      <span class="genre-chip">{genre_esc}</span>
      <div class="name">{name_esc}</div>
      <div class="meta-row">
        <span class="price">¥{price:,}</span>
        <span class="stars">{stars}</span>
        <span>{review_avg}({review_count}件)</span>
      </div>
    </div>
  </div>
  <a class="btn-open" href="{aff_url}" target="_blank" rel="noopener">商品ページを開く ↗</a>
  <div class="url-row">
    <a href="{product_url}" target="_blank" rel="noopener">{product_url}</a>
    <button class="copy-btn" onclick="copyPlain(this, '{product_url}')" type="button">URLコピー</button>
  </div>
  <div class="caption-box">
    <div class="caption-head">
      <span>楽天ROOM用</span>
      <button class="copy-btn" onclick="copyText(this, 'room-{idx}')" type="button">コピー</button>
    </div>
    <textarea id="room-{idx}" readonly>{room_caption}</textarea>
  </div>
{featured_captions}</div>"""

FEATURED_CAPTIONS_TEMPLATE = """  <p class="reason">🔥 今日のピックアップ理由: {reason_esc}</p>
  <div class="caption-box">
    <div class="caption-head">
      <span>Threads用</span>
      <button class="copy-btn" onclick="copyText(this, 'threads-0')" type="button">コピー</button>
    </div>
    <textarea id="threads-0" readonly>{threads_caption}</textarea>
  </div>
  <div class="caption-box">
    <div class="caption-head">
      <span>X用</span>
      <button class="copy-btn" onclick="copyText(this, 'x-0')" type="button">コピー</button>
    </div>
    <textarea id="x-0" readonly>{x_caption}</textarea>
  </div>
"""

DAILY_CARD_TEMPLATE = """<div class="card">
  <div class="caption-box">
    <div class="caption-head">
      <span>あるある投稿 #{num}</span>
      <button class="copy-btn" onclick="copyText(this, 'daily-{idx}')" type="button">コピー</button>
    </div>
    <textarea id="daily-{idx}" class="short" readonly>{text}</textarea>
  </div>
</div>"""

SCRIPT = """<script>
function flash(btn) {
  const original = btn.textContent;
  btn.textContent = 'コピーしました';
  btn.classList.add('copied');
  setTimeout(() => { btn.textContent = original; btn.classList.remove('copied'); }, 1500);
}
function copyText(btn, id) {
  const el = document.getElementById(id);
  el.select();
  el.setSelectionRange(0, 999999);
  navigator.clipboard.writeText(el.value).then(() => flash(btn)).catch(() => {
    try { document.execCommand('copy'); flash(btn); } catch (e) {}
  });
}
function copyPlain(btn, text) {
  navigator.clipboard.writeText(text).then(() => flash(btn)).catch(() => {
    const t = document.createElement('textarea');
    t.value = text; document.body.appendChild(t); t.select();
    try { document.execCommand('copy'); flash(btn); } catch (e) {}
    document.body.removeChild(t);
  });
}
</script>"""


def star_string(avg):
    full = int(round(avg))
    full = max(0, min(5, full))
    return "★" * full + "☆" * (5 - full)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", required=True)
    parser.add_argument("--captions", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="本日の選定")
    args = parser.parse_args()

    selected = json.load(open(args.selected, encoding="utf-8"))
    caption_data = json.load(open(args.captions, encoding="utf-8"))
    products_cap = caption_data.get("products", [])
    featured = caption_data.get("featured", {})
    daily_posts = caption_data.get("dailyLifePosts", [])

    cap_by_code = {c["itemCode"]: c for c in products_cap}
    featured_code = featured.get("itemCode")

    cards_html = []
    for idx, item in enumerate(selected):
        cap = cap_by_code.get(item["itemCode"], {})
        is_featured = item["itemCode"] == featured_code
        featured_captions = ""
        if is_featured:
            featured_captions = FEATURED_CAPTIONS_TEMPLATE.format(
                reason_esc=html.escape(featured.get("reason", "")),
                threads_caption=html.escape(featured.get("threadsCaption", "")),
                x_caption=html.escape(featured.get("xCaption", "")),
            )
        cards_html.append(CARD_TEMPLATE.format(
            featured_class=" featured" if is_featured else "",
            featured_badge='<span class="featured-badge">🔥 本日のThreads/Xピックアップ</span>' if is_featured else "",
            image_url=item.get("imageUrl", ""),
            name_esc=html.escape(item["itemName"]),
            genre_esc=html.escape(item.get("genreGroup", "")),
            price=item["price"],
            review_count=item["reviewCount"],
            review_avg=item["reviewAverage"],
            stars=star_string(item["reviewAverage"]),
            aff_url=item["affiliateUrl"],
            product_url=html.escape(product_url_of(item), quote=True),
            idx=idx,
            room_caption=html.escape(cap.get("roomCaption", "")),
            featured_captions=featured_captions,
        ))

    daily_cards_html = []
    for idx, text in enumerate(daily_posts):
        daily_cards_html.append(DAILY_CARD_TEMPLATE.format(
            num=idx + 1,
            idx=idx,
            text=html.escape(text),
        ))

    page = TEMPLATE.format(
        label=html.escape(args.label),
        count=len(selected),
        cards="\n".join(cards_html),
        daily_cards="\n".join(daily_cards_html) if daily_cards_html else "<p style='color:var(--ink-soft);font-size:0.85rem;'>今回は日常投稿ネタが生成されませんでした。</p>",
        script=SCRIPT,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"ページを生成しました: {out_path}")


if __name__ == "__main__":
    main()
