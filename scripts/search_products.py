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
import re
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


def _plain_product_url(item):
    """楽天ROOMへの投稿・共有に使う素の商品ページURL(item.rakuten.co.jp/...)。
    APIのaffiliateUrlはhb.afl.rakuten.co.jpの転送URLで、スマホで開けない/商品URLに
    見えない問題があるため、pc=パラメータから素のURLを取り出す。取れなければ
    itemUrlをそのまま返す。"""
    for key in ("itemUrl", "affiliateUrl"):
        val = item.get(key) or ""
        if val.startswith("https://item.rakuten.co.jp/") or val.startswith("http://item.rakuten.co.jp/"):
            return val
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(val).query)
            pc = qs.get("pc", [""])[0]
            if pc.startswith("http"):
                return pc
        except Exception:
            pass
    return item.get("itemUrl") or ""



# 商品タイプ語(これが2件以上すでに投稿されていたら、そのカテゴリは飽和とみなす)
_TYPE_WORDS = [
    "ロボット掃除機", "ハンディクリーナー", "コードレス掃除機", "スティック掃除機", "電気ケトル",
    "電気圧力鍋", "衣類スチーマー", "スチームアイロン", "食洗機ラック", "サーキュレーター",
    "布団乾燥機", "空気清浄機", "加湿器", "除湿機", "ブレンダー", "ミキサー", "炊飯器",
    "保存容器", "ゴミ箱", "分別", "水切りラック", "米びつ", "弁当箱", "水筒", "マイボトル",
    "収納ボックス", "収納ケース", "収納ワゴン", "ハンガーラック", "チェスト", "カラーボックス",
    "突っ張り棒", "突っ張り棚", "ハンガー", "シューズラック", "絵本ラック", "おもちゃ収納",
    "抱っこ紐", "ヒップシート", "ベビーカー", "鼻吸い器", "鼻水吸引", "離乳食", "ベビー食器",
    "歯固め", "ベビーゲート", "ベビーサークル", "おむつ", "ベビーモニター", "豆いす", "踏み台",
    "保冷シート", "ファンシート", "抱っこ紐 冷", "蚊取り", "虫除け", "室内物干し", "部屋干し",
    "簡易トイレ", "防災", "モバイルバッテリー", "ランタン", "電気毛布", "ルームシューズ",
    "こたつ", "湯たんぽ", "換気扇フィルター", "レンジフード", "電動歯ブラシ", "シェーバー",
    "ドライヤー", "マットレス", "ジョイントマット", "枕", "三輪車", "バランスバイク",
]


def _name_tokens(name):
    """商品名から「ブランドらしい識別トークン」を抽出する。
    カタカナ4文字以上の連続、英数字3文字以上の語(型番・ブランド)を拾う。"""
    toks = set()
    for m in re.findall(r"[ァ-ヴー]{4,}", name):
        toks.add(m)
    for m in re.findall(r"[A-Za-z0-9][A-Za-z0-9+-]{2,}", name):
        toks.add(m.lower())
    # ノイズになりやすい一般カタカナ語を除外
    for junk in ("セット", "シリーズ", "サイズ", "カラー", "レビュー", "クーポン", "ポイント",
                 "プレゼント", "ランキング", "スーパー", "タイプ", "コンパクト", "おしゃれ",
                 "ホワイト", "ブラック", "グレー", "ナチュラル", "ブラウン"):
        toks.discard(junk)
    return toks


def build_name_filters(history):
    """投稿履歴から (ブランドトークン集合, タイプ語→件数) を作る。"""
    brand_tokens = set()
    type_counts = {}
    for p in history.get("posted", []):
        nm = p.get("itemName", "")
        brand_tokens |= _name_tokens(nm)
        for t in _TYPE_WORDS:
            if t in nm:
                type_counts[t] = type_counts.get(t, 0) + 1
    return brand_tokens, type_counts


# すでに何度も投稿していて新規性が薄いタイプ語(1件でも投稿済みなら除外する)
_HARD_BLOCK = [
    "空気清浄機", "ヒップシート", "抱っこ紐", "収納ワゴン", "ゴミ箱", "分別",
    "電気ケトル", "電気圧力鍋", "ロボット掃除機", "ハンディクリーナー",
    "コードレス掃除機", "布団乾燥機", "サーキュレーター", "衣類スチーマー",
    "スチームアイロン", "鼻吸い器", "鼻水吸引", "保存容器", "室内物干し",
    "部屋干し", "マイボトル", "水筒", "ハンガーラック", "カラーボックス",
    "突っ張り棒", "食洗機ラック", "換気扇フィルター", "ジョイントマット",
    "マットレス", "簡易トイレ", "非常用トイレ", "携帯トイレ", "三輪車",
]


def is_name_duplicate(item, brand_tokens, type_counts):
    """itemCodeは新しいが、実質すでに投稿済みの商品/カテゴリなら True。"""
    nm = item.get("itemName", "")
    # 1) 投稿済みブランド/型番トークンと一致 → 同一商品の別ショップ・型違いとみなす
    if _name_tokens(nm) & brand_tokens:
        return True
    # 2) 飽和カテゴリ: 1件でも投稿済みのタイプ語
    for t in _HARD_BLOCK:
        if t in nm and type_counts.get(t, 0) >= 1:
            return True
    # 3) その他のタイプ語も2件以上投稿済みなら除外
    for t, c in type_counts.items():
        if c >= 2 and t in nm:
            return True
    return False


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
    brand_tokens, type_counts = build_name_filters(history)

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
            if is_name_duplicate(item, brand_tokens, type_counts):
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
            "productUrl": _plain_product_url(item),
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
