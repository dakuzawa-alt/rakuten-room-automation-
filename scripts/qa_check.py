#!/usr/bin/env python3
"""投稿前QA(機械的な検査を全部これで行う)。LLMは、このスクリプトが出した指摘の判断だけに使う。

使い方:
  python scripts/qa_check.py --selected output/selected_2026-09-30_morning.json \
                             --captions output/captions_2026-09-30_morning.json [--allow code,...] [--append]

- 書式のずれ(別書式のcopy_*.json、affiliateUrl/itemUrlの入れ替わり)は自動で正規形に直して保存する(--no-fix で無効)
- 検査: 文字数(Xは全角2換算で280)・禁止語・URL・PR表記・絵文字・価格/レビュー数の一致・日常投稿・重複(dup_check.py)
- 全部通ると exit 0。--append を付けると投稿履歴に追記する(featuredはroom+threads+x、他はroom)
- 人が読む判断が必要な項目(機能記載が商品データで裏付けられるか、日常投稿が捏造エピソードでないか)は対象外
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dup_check  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
NG_WORDS = ["奇跡", "治る", "効く", "絶対", "100%", "100％"]
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⭐⭕⏩-⏺✅⌚⌛]")
PROMO_RE = re.compile(r"【[^】]*】|\[[^\]]*\]|［[^］]*］|＼[^／]*／|★[^★]*★")
LIMITS = {"room": 400, "threads": 400, "x": 280, "daily": 150}


def xweight(s):
    return sum(1 if ord(c) <= 0x7F else 2 for c in s)


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def plain_url(aff):
    m = re.search(r"[?&]pc=([^&]+)", aff or "")
    return re.sub(r"%([0-9A-Fa-f]{2})", lambda x: chr(int(x.group(1), 16)), m.group(1)) if m else aff


def normalize_selected(items):
    notes = []
    for it in items:
        if "itemPrice" not in it and "price" in it:
            it["itemPrice"] = it["price"]
        aff, plain = it.get("affiliateUrl"), it.get("itemUrl", "")
        if not aff and plain.startswith("https://hb.afl.rakuten.co.jp/"):
            it["affiliateUrl"], it["itemUrl"] = plain, plain_url(plain)
            notes.append(f"{it['itemCode']}: itemUrlにアフィリエイトURLが入っていたので分離")
        elif aff and plain.startswith("https://hb.afl.rakuten.co.jp/"):
            it["itemUrl"] = plain_url(aff)
            notes.append(f"{it['itemCode']}: itemUrlを素URLに修正")
    return notes


def normalize_captions(c):
    """copywriter/自動実行が別書式で出した投稿文を、generate_page.pyの書式に直す。"""
    if "products" in c and "dailyLifePosts" in c:
        return c, []
    f = c.get("featured", {})
    out = {
        "products": [{"itemCode": i["itemCode"], "itemName": i.get("itemName", ""), "price": i.get("itemPrice", i.get("price")),
                      "roomCaption": i.get("roomPost", i.get("roomCaption", ""))} for i in c.get("items", c.get("products", c.get("posts", [])))],
        "featured": {"itemCode": f.get("itemCode"), "itemName": f.get("itemName"),
                     "reason": f.get("featuredReason", f.get("reason", "")),
                     "threadsCaption": f.get("threadsPost", f.get("threadsCaption", "")),
                     "xCaption": f.get("xPost", f.get("xCaption", ""))},
        "dailyLifePosts": c.get("aruaruPosts", c.get("dailyLifePosts", c.get("dailyPosts", []))),
    }
    return out, ["投稿文の書式を正規形(products/featured/dailyLifePosts)に変換"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected", required=True)
    ap.add_argument("--captions", required=True)
    ap.add_argument("--allow", default="")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--no-fix", action="store_true")
    a = ap.parse_args()

    date, slot = dup_check.slot_of(a.selected)
    items = dup_check.load_items(a.selected)
    caps = read_json(a.captions)
    fails, warns, notes = [], [], []

    caps, n2 = normalize_captions(caps)
    n1 = normalize_selected(items)
    if (n1 or n2) and not a.no_fix:
        write_json(a.selected, items)
        write_json(a.captions, caps)
    notes += n1 + n2

    codes = [i["itemCode"] for i in items]
    pcodes = [p["itemCode"] for p in caps["products"]]
    if sorted(codes) != sorted(pcodes):
        fails.append(f"商品データと投稿文のitemCodeが一致しません: 差分 {sorted(set(codes) ^ set(pcodes))}")
    if len(codes) != 5:
        warns.append(f"商品が{len(codes)}件です(通常5件)")
    f = caps["featured"]
    if f.get("itemCode") not in codes:
        fails.append(f"featuredのitemCode {f.get('itemCode')} が商品データにありません")

    by_code = {i["itemCode"]: i for i in items}
    for p in caps["products"]:
        code, room = p["itemCode"], p.get("roomCaption", "")
        it = by_code.get(code)
        n = len(room)
        first = room.split("\n")[0]
        if n > LIMITS["room"]:
            fails.append(f"{code} ROOM文が{n}文字(上限400)")
        if len(EMOJI_RE.findall(room)) < 3 or not EMOJI_RE.search(first):
            fails.append(f"{code} 絵文字不足(3個以上・1行目に1個以上)")
        if re.search(r"https?://", room):
            fails.append(f"{code} ROOM文にURLが入っています")
        if not it:
            continue
        m = re.search(r"レビュー\s*([\d,]+)\s*件", room)
        if m and abs(int(m.group(1).replace(",", "")) - it["reviewCount"]) > max(2, it["reviewCount"] * 0.02):
            fails.append(f"{code} レビュー数 {m.group(1)}件 が商品データ({it['reviewCount']}件)と一致しません")
        m = re.search(r"[★星]\s*([\d.]+)", room)
        if m and abs(float(m.group(1)) - it["reviewAverage"]) > 0.05:
            fails.append(f"{code} 星評価 {m.group(1)} が商品データ({it['reviewAverage']})と一致しません")
        lo, hi = it.get("itemPriceMin", it["itemPrice"]), it.get("itemPriceMax", it["itemPrice"])
        prices = [int((a_ or b_).replace(",", "")) for a_, b_ in re.findall(r"[¥￥]([\d,]+)|([\d,]+)円", room)]
        bad = [x for x in prices if x >= 500 and not (lo <= x <= hi) and x != it["itemPrice"]]
        if bad and not re.search(r"(1本|1枚|1個|あたり|クーポン)", room):
            warns.append(f"{code} ROOM文の金額 {bad} が商品データの価格({it['itemPrice']}円)と違います")
        if lo != hi and f"{it['itemPrice']:,}" in room and "〜" not in room and "から" not in room:
            warns.append(f"{code} 価格に幅({lo}〜{hi}円)がありますが『〜』表記がありません")
    for i in items:
        if not re.match(r"https://item\.rakuten\.co\.jp/[^?]*$", i.get("itemUrl", "")):
            fails.append(f"{i['itemCode']} itemUrlが素の商品URLではありません")
        aff = i.get("affiliateUrl", "")
        if not aff.startswith("https://hb.afl.rakuten.co.jp/") or "placeholder" in aff or "pc=" not in aff:
            fails.append(f"{i['itemCode']} affiliateUrlが不正です(placeholder・組み立てURLはAPI実データではないため不可)")

    th, x = f.get("threadsCaption", ""), f.get("xCaption", "")
    if len(th) > LIMITS["threads"]:
        fails.append(f"Threads文が{len(th)}文字(上限400)")
    if xweight(x) > LIMITS["x"]:
        fails.append(f"X文が重み付け{xweight(x)}(上限280。全角=2、半角=1、改行=1)")
    for label, s in (("Threads", th), ("X", x)):
        if not s:
            fails.append(f"{label}文がありません")
        elif "#PR" not in s and "#楽天アフィリエイト" not in s:
            fails.append(f"{label}文にPR表記がありません")
        if re.search(r"https?://", s):
            fails.append(f"{label}文にURLが入っています")
    daily = caps["dailyLifePosts"]
    if len(daily) != 5:
        warns.append(f"あるある投稿が{len(daily)}個です(通常5個)")
    for k, d in enumerate(daily):
        if len(d) > LIMITS["daily"]:
            fails.append(f"あるある投稿{k + 1}が{len(d)}文字(上限150)")
        if re.search(r"https?://|#PR|楽天", d):
            fails.append(f"あるある投稿{k + 1}にURL・PR表記・『楽天』が入っています")
    blob = json.dumps(caps, ensure_ascii=False)
    for w in NG_WORDS:
        if w in blob:
            fails.append(f"禁止語『{w}』が投稿文に含まれています")

    allow = set(filter(None, a.allow.split(",")))
    for lvl, code, msg in dup_check.check_items(items, date, slot, allow):
        if lvl == "FAIL":
            fails.append(f"{code} {msg}")
        elif lvl in ("WARN", "ALLOW"):
            warns.append(f"{code} {msg}" + (" [--allowで許可済み]" if lvl == "ALLOW" else ""))

    print(f"== QA {date} {slot} : 商品{len(codes)}件 / X重み付け {xweight(x)} / Threads {len(th)}文字 ==")
    for n in notes:
        print(f"[修正] {n}")
    for w in warns:
        print(f"[WARN] {w}")
    for x_ in fails:
        print(f"[FAIL] {x_}")
    if fails:
        print(f"結果: 不合格({len(fails)}件)。履歴には追記していません。")
        sys.exit(1)
    print("結果: 合格(機械チェック)。機能記載の裏付け・日常投稿の内容は別途、人の目で確認してください。")
    if a.append:
        hp = dup_check.HISTORY
        raw = hp.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        h = json.loads(raw)
        have = {(e["itemCode"], e.get("date"), e.get("slot")) for e in h["posted"]}
        added = 0
        for i in items:
            if (i["itemCode"], date, slot) in have:
                continue
            name = PROMO_RE.sub("", i["itemName"]).strip()[:60]
            h["posted"].append({"itemCode": i["itemCode"], "itemName": name, "date": date, "slot": slot,
                                "channels": ["room", "threads", "x"] if i["itemCode"] == f["itemCode"] else ["room"]})
            added += 1
        out = json.dumps(h, ensure_ascii=False, indent=2)
        hp.write_text(out.replace("\n", "\r\n") if crlf else out, encoding="utf-8", newline="")
        print(f"投稿履歴に{added}件追記しました(合計{len(h['posted'])}件)")


if __name__ == "__main__":
    main()
