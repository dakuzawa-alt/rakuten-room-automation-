#!/usr/bin/env python3
"""投稿履歴との重複チェック。LLMに履歴を丸読みさせずに済むよう、決定的に判定する。

使い方: python scripts/dup_check.py output/selected_2026-09-30_morning.json [--allow itemCode,...]

判定:
  FAIL  itemCodeが履歴にある(rejected_duplicate含む) / 飽和カテゴリ語(config/saturated_terms.json)が
        新商品名と履歴商品名の両方にある → 実質重複の疑い。人が確認し、問題なければ --allow で通す
  WARN  新商品名と履歴商品名が「履歴内でも珍しい語」を共有(ブランド名・商品タイプの可能性)。参考情報
  INFO  同じショップの商品が履歴にある
同じ日付・枠(selected_YYYY-MM-DD_slot.json)の履歴は比較対象から外す(再実行・自動実行分との衝突を避ける)。
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY = BASE_DIR / "data" / "posted_history.json"
SATURATED = BASE_DIR / "config" / "saturated_terms.json"
NAME_RE = re.compile(r"selected_(\d{4}-\d{2}-\d{2})_(morning|night)")
PROMO_RE = re.compile(r"【[^】]*】|\[[^\]]*\]|［[^］]*］|＼[^／]*／|★[^★]*★")
TOKEN_RE = re.compile(r"[ァ-ヴー]{3,}|[一-龥々]{3,}|[a-z0-9][a-z0-9+\-]{2,}")
STOP = {"日本製", "送料無料", "大容量", "公式", "限定", "対応", "商品", "楽天", "収納", "プレゼント", "ギフト",
        "セット", "サイズ", "カラー", "シリーズ", "タイプ", "おしゃれ", "ランキング", "レビュー", "クーポン", "ポイント",
        "子供", "子ども", "家庭", "家族", "便利", "簡単", "自宅", "業務用", "専用", "新生児", "赤ちゃん", "ベビー",
        "キッズ", "メンズ", "レディース", "本体", "付き", "対策", "予防",
        "ライト", "カメラ", "ケース", "スタンド", "ホルダー", "ボックス", "バッグ", "マット", "カバー", "シート", "ラック", "ボトル",
        "ポット", "ブラシ", "ハンガー", "クリーナー", "ドライヤー", "アダプター", "スマホ", "ステンレス", "コンパクト"}


def norm(s):
    return unicodedata.normalize("NFKC", s or "").lower()


def tokens(name):
    s = norm(PROMO_RE.sub(" ", name or ""))[:80]
    return {t for t in TOKEN_RE.findall(s) if t not in STOP}


def load_history():
    return json.loads(HISTORY.read_text(encoding="utf-8"))["posted"]


def load_items(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("items", "selected", "candidates", "products"):
            if isinstance(data.get(key), list):
                return data[key]
        raise SystemExit(f"{path}: 商品リストが見つかりません")
    return data


def slot_of(path):
    m = NAME_RE.search(Path(path).name)
    return (m.group(1), m.group(2)) if m else (None, None)


def check_items(items, date=None, slot=None, allow=()):
    """[(level, itemCode, message)] を返す。"""
    hist = [h for h in load_history() if not (date and h.get("date") == date and h.get("slot") == slot)]
    terms = json.loads(SATURATED.read_text(encoding="utf-8"))["terms"] if SATURATED.exists() else []
    hist_norm = [(h, norm(h.get("itemName", ""))) for h in hist]
    df = Counter()
    hist_tok = []
    for h, _ in hist_norm:
        t = tokens(h.get("itemName", ""))
        hist_tok.append(t)
        df.update(t)
    by_code = {h["itemCode"]: h for h in hist}
    out = []
    for it in items:
        code, name = it["itemCode"], it.get("itemName", "")
        n = norm(name)
        if code in by_code:
            h = by_code[code]
            out.append(("FAIL", code, f"itemCodeが履歴にあります({h.get('date')} {h.get('slot')})"))
            continue
        shop = code.split(":")[0]
        same = [h for h in hist if h["itemCode"].startswith(shop + ":")]
        if same:
            out.append(("INFO", code, f"同じショップ({shop})の履歴: " + " / ".join(h["itemName"][:18] for h in same[:2])))
        for term in terms:
            t = norm(term)
            if t in n:
                hit = [h for h, hn in hist_norm if t in hn]
                if hit:
                    lvl = "ALLOW" if code in allow else "FAIL"
                    h = hit[0]
                    out.append((lvl, code, f"飽和カテゴリ『{term}』が履歴にあります: {h['itemCode']} {h['itemName'][:24]}({h.get('date')} {h.get('slot')})"))
                    break
        mine = tokens(name)
        scored = []
        for (h, _), ht in zip(hist_norm, hist_tok):
            shared = sorted(t for t in mine & ht if df[t] <= 3)
            if shared:
                scored.append((len(shared), h, shared))
        scored.sort(key=lambda x: -x[0])
        for _, h, shared in scored[:2]:
            out.append(("WARN", code, f"類似語 {','.join(shared[:3])} : {h['itemCode']} {h['itemName'][:24]}"))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--allow", default="", help="人が確認済みで通すitemCode(カンマ区切り)")
    a = ap.parse_args()
    date, slot = slot_of(a.path)
    res = check_items(load_items(a.path), date, slot, set(filter(None, a.allow.split(","))))
    for lvl, code, msg in res:
        print(f"[{lvl}] {code} {msg}")
    fails = sum(1 for r in res if r[0] == "FAIL")
    print(f"重複チェック: FAIL {fails}件" if fails else "重複チェック: FAILなし")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
