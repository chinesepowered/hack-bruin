"""@bruin
name: vibes.cards
image: python:3.12
connection: duckdb-default
description: |
  Each viewer's crew card: their own capybara, dressed in the loadout Qwen4-Max picked from their posts,
  painted by Qwen-Image with Yuzu's sheet as the species and style reference. The player reads this table.
tags: [vibes, runware, qwen]
depends:
  - vibes.personas
  - vibes.ig_profiles
materialization:
  type: table
columns:
  - name: handle
    type: varchar
    primary_key: true
  - name: card_path
    type: varchar
    checks:
      - name: not_null
  - name: total_usd
    type: double
    checks:
      - name: max
        value: 0.10
@bruin"""
import json

import pandas as pd
from bruin import query

from capypunk import clients, config, vibes


def materialize():
    bible = json.loads((config.SERIES / "bible.json").read_text())
    yuzu_ref = clients.runware_upload(config.SERIES / "cast" / "yuzu.jpg")
    ref = yuzu_ref.get("mediaURL") or yuzu_ref.get("mediaUUID")
    out = config.media_dir("vibes")
    rows = []
    sql = ("SELECT p.*, g.glasser_usd FROM vibes.personas p JOIN vibes.ig_profiles g USING (handle)")
    for p in query(sql, connection="duckdb-default").to_dict("records"):
        vibe = {**p, "palette": json.loads(p["palette_json"])}
        img = clients.qwen_image(vibes.crew_card_prompt(bible, vibe), width=1024, height=1536, refs=[ref])[0]
        path = clients.download(img["imageURL"], out / f"card_{p['handle']}.png")
        card_usd = float(img.get("cost") or 0.0141)
        rows.append({**{k: p[k] for k in ("handle", "alias", "archetype", "palette_json", "risk_appetite", "trust_pick",
                                         "trust_reason", "package_pick", "package_reason", "most_like", "tagline",
                                         "predicted_path")},
                     "card_path": str(path.relative_to(config.REPO)), "card_url": img["imageURL"],
                     "total_usd": round(float(p["glasser_usd"]) + float(p["qwen_usd"]) + card_usd, 4)})
    return pd.DataFrame(rows)
