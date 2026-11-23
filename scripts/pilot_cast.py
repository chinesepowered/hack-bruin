"""Pilot step 1: character reference sheets for Yuzu and Vex (2 options each)."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from capypunk import clients, config  # noqa: E402

bible = json.loads((config.SERIES / "bible.json").read_text())
out = config.media_dir("pilot", "cast")


def sheet(cid: str):
    ch = bible["characters"][cid]
    prompt = (f"Character reference portrait of {ch['look']}. Full body, standing, three-quarter view, "
              f"centered, plain dark charcoal studio backdrop with a soft neon rim light, clean silhouette. "
              f"{bible['style']}. {bible['negative_style']}.")
    rows = clients.qwen_image(prompt, width=1024, height=1536, n=2)
    res = []
    for i, r in enumerate(rows):
        p = clients.download(r["imageURL"], out / f"{cid}_{i}.png")
        res.append({"char": cid, "i": i, "url": r["imageURL"], "path": str(p), "cost": r.get("cost"), "seed": r.get("seed")})
    return res


with ThreadPoolExecutor(2) as ex:
    results = [x for batch in ex.map(sheet, ["yuzu", "vex"]) for x in batch]
(out / "cast.json").write_text(json.dumps(results, indent=1))
for r in results:
    print(r["char"], r["i"], r["path"], "cost", r["cost"])
