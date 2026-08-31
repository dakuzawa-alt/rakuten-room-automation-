#!/usr/bin/env python3
"""
楽天市場APIで商品を検索し、スコアリング・重複除外を行った上で
上位候補をJSONで出力するスクリプト。

使い方:
    python search_products.py --count 5 --out ../output/candidates_YYYY-MM-DD_morning.json
"""
import argparse
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_api(creds, keyword, hits=30):
    params = {
        "applicationId": creds["applicationId"],
        "accessKey": creds["accessKey"],
        "affiliateId": creds["affiliateId"],
        "keyword": keyword,
        "hits": hits,
        "sort": "-reviewCount",
        "format": "json",
    }
    url = API_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "room-research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        print(f"  [WARN] keyword='{keyword}' の検索に失敗: {e}", file=sys.stderr)
        return None


def score_item(item):
    review_count = item.get("reviewCount", 0)
    review_avg = item.get("reviewAverage", 0)
    # レビュー数は対数的に頭打ちにしつつ、評価の高さを重視するスコア
    import math
    return review_avg * 20 + min(math.log(review_count + 1) * 8, 40)


def is_excluded(item, keywords_cfg):
    name = item.get("itemName", "")
    for word in keywords_cfg.get("excluded_categories", []):
        if word in name:
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--out", type=str, required=True)
    args = parser.parse_args()

    creds = load_json(BASE_DIR / "config" / "credentials.json")
    kw_cfg = load_json(BASE_DIR / "config" / "keywords.json")
    history = load_json(BASE_DIR / "data" / "posted_history.json")
    posted_codes = {p["itemCode"] for p in history.get("posted", [])}

    price_min = kw_cfg["price_range"]["min"]
    price_max = kw_cfg["price_range"]["max"]
    min_avg = kw_cfg["quality_bar"]["min_review_average"]
    min_count = kw_cfg["quality_bar"]["min_review_count"]

    # ジャンルの偏りを防ぐため、グループごとにキーワードを2件までサンプリングして
    # 全グループを横断的に検索する(1グループだけで候補が埋まらないようにする)
    kw_to_group = {}
    sampled_keywords = []
    for group_name, kws in kw_cfg["keyword_groups"].items():
        picked = random.sample(kws, min(2, len(kws)))
        for kw in picked:
            kw_to_group[kw] = group_name
        sampled_keywords.extend(picked)
    random.shuffle(sampled_keywords)

    MAX_PER_KEYWORD = 4  # 1キーワードあたりの採用上限(特定ジャンルへの偏り防止)

    candidates = {}
    for i, kw in enumerate(sampled_keywords):
        if i > 0:
            time.sleep(1.2)  # 申請したQPS(1)を超えないよう間隔を空ける
        result = call_api(creds, kw)
        if not result or "Items" not in result:
            continue
        taken_for_this_kw = 0
        for wrapped in result["Items"]:
            if taken_for_this_kw >= MAX_PER_KEYWORD:
                break
            item = wrapped["Item"]
            code = item.get("itemCode")
            if not code or code in posted_codes or code in candidates:
                continue
            if item.get("reviewAverage", 0) < min_avg:
                continue
            if item.get("reviewCount", 0) < min_count:
                continue
            price = item.get("itemPrice", 0)
            if not (price_min <= price <= price_max):
                continue
            if is_excluded(item, kw_cfg):
                continue
            item["_matchedKeyword"] = kw
            item["_group"] = kw_to_group.get(kw, "その他")
            item["_score"] = score_item(item)
            candidates[code] = item
            taken_for_this_kw += 1

    ranked = sorted(candidates.values(), key=lambda x: x["_score"], reverse=True)

    # ジャンルの多様性を確保しながら上位N件を選ぶ(同じグループは最大2件まで)
    MAX_PER_GROUP = 2
    group_counts = {}
    top = []
    leftovers = []
    for item in ranked:
        if len(top) >= args.count:
            break
        g = item["_group"]
        if group_counts.get(g, 0) < MAX_PER_GROUP:
            top.append(item)
            group_counts[g] = group_counts.get(g, 0) + 1
        else:
            leftovers.append(item)
    # 多様性制約だけでは埋まらなかった場合は、スコア順に残りを補充する
    for item in leftovers:
        if len(top) >= args.count:
            break
        top.append(item)

    output = []
    for item in top:
        output.append({
            "itemCode": item.get("itemCode"),
            "itemName": item.get("itemName"),
            "price": item.get("itemPrice"),
            "reviewCount": item.get("reviewCount"),
            "reviewAverage": item.get("reviewAverage"),
            "itemUrl": item.get("itemUrl"),
            "affiliateUrl": item.get("affiliateUrl"),
            "imageUrl": (item.get("mediumImageUrls") or [{}])[0].get("imageUrl", ""),
            "shopName": item.get("shopName"),
            "matchedKeyword": item.get("_matchedKeyword"),
            "genreGroup": item.get("_group"),
            "itemCaptionExcerpt": (item.get("itemCaption") or "")[:300],
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"候補 {len(output)} 件を {out_path} に出力しました。")
    if len(output) < args.count:
        print(f"[NOTICE] 目標件数 {args.count} 件に対し {len(output)} 件しか集まりませんでした。"
              f"キーワードや条件の見直しが必要かもしれません。")


if __name__ == "__main__":
    main()
