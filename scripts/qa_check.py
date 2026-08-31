import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
data = json.load(open(BASE_DIR / "output" / "captions_2026-08-31_morning.json", encoding="utf-8"))
ng_words = ["治る", "効く", "絶対", "100%", "奇跡"]

out = sys.stdout
for item in data:
    room = item["roomCaption"]
    threads = item["threadsCaption"]
    out.write(f"--- {item['itemName'][:20]} ---\n")
    out.write(f"ROOM文字数: {len(room)}  Threads文字数: {len(threads)}\n")
    for label, text in [("ROOM", room), ("Threads", threads)]:
        for ng in ng_words:
            if ng in text:
                out.write(f"  [NG] {label}に禁止語『{ng}』\n")
    if "#PR" not in threads and "#楽天アフィリエイト" not in threads:
        out.write("  [NG] ThreadsにPR表記なし\n")
    price_str1 = str(item["price"])
    price_str2 = f"{item['price']:,}"
    if price_str1 not in room and price_str2 not in room:
        out.write(f"  [WARN] ROOM文に価格{item['price']}円の記載が見当たりません\n")
out.write("チェック完了\n")
