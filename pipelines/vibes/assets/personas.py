"""@bruin
name: vibes.personas
image: python:3.12
connection: duckdb-default
description: |
  Qwen4-Max reads each viewer's captions and photos and casts them as a character in Halcyon City, with a
  predicted pick at both decisions. The schema only has in-world fields, so there is nowhere to record guesses
  about age, ethnicity, religion, health, politics or sexuality.
tags: [vibes, runware, qwen]
depends:
  - vibes.ig_profiles
materialization:
  type: table
columns:
  - name: handle
    type: varchar
    primary_key: true
  - name: risk_appetite
    type: integer
    checks:
      - name: min
        value: 1
      - name: max
        value: 5
custom_checks:
  # explicit SQL rather than accepted_values: see the README note on accepted_values for Python assets on DuckDB
  - name: picks and archetypes come from the story's own options
    query: |
      SELECT count(*) FROM vibes.personas
      WHERE trust_pick NOT IN ('vex', 'kade')
         OR package_pick NOT IN ('hand_over', 'open')
         OR most_like NOT IN ('vex', 'kade', 'sable', 'yuzu')
         OR archetype NOT IN ('Netrunner', 'Street Racer', 'Night-Market Chef', 'Rooftop Romantic',
                              'Corporate Defector', 'Hot-Spring Monk', 'Gadget Smith', 'Wandering Ronin')
    value: 0
  - name: every predicted path exists in the story graph
    query: SELECT count(*) FROM vibes.personas p LEFT JOIN story.paths s ON s.path = p.predicted_path WHERE s.path IS NULL
    value: 0
@bruin"""
import json

import pandas as pd
from bruin import query

from capypunk import clients, config, vibes


def materialize():
    bible = json.loads((config.SERIES / "bible.json").read_text())
    rows = []
    for p in query("SELECT * FROM vibes.ig_profiles WHERE found AND NOT private", connection="duckdb-default").to_dict("records"):
        posts = json.loads(p["posts_json"])
        img_dir = config.media_dir("vibes", p["handle"])
        imgs = []
        for i, post in enumerate(posts):
            if post.get("image") and len(imgs) < 6:
                try:
                    imgs.append(clients.download(post["image"], img_dir / f"post_{i}.jpg"))
                except Exception as e:  # CDN links are short-lived; captions still carry the vibe
                    print("skip image", i, str(e)[:100])
        profile = {"bio": p["bio"], "posts": p["posts_count"],
                   "bioLinks": [{"title": t} for t in json.loads(p["link_titles"] or "[]")]}
        vibe, usage = clients.qwen_chat(vibes.vibe_messages(bible, profile, posts, imgs), schema=vibes.VIBE_SCHEMA,
                                        schema_name="vibe", max_tokens=3000)
        rows.append({"handle": p["handle"], "alias": vibe["alias"], "archetype": vibe["archetype"],
                     "palette_json": json.dumps(vibe["palette"][:3]), "risk_appetite": int(vibe["risk_appetite"]),
                     "trust_pick": vibe["trust_pick"], "trust_reason": vibe["trust_reason"],
                     "package_pick": vibe["package_pick"], "package_reason": vibe["package_reason"],
                     "most_like": vibe["most_like"], "tagline": vibe["tagline"], "loadout": vibe["loadout"],
                     "predicted_path": vibes.predicted_path(vibe), "images_seen": len(imgs),
                     "qwen_usd": vibes.qwen_cost(usage)})
        print(p["handle"], "->", vibe["alias"], vibe["archetype"], vibes.predicted_path(vibe))
    return pd.DataFrame(rows)
