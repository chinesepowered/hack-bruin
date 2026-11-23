"""@bruin
name: story.headline_digest
image: python:3.12
connection: duckdb-default
description: |
  Qwen4-Max (via Runware) reads today's articles, picks the three that best fuel the story, lists every
  real entity they mention, and invents Lumina's fictional mirror of each.
tags: [runware, qwen, writers_room]
depends:
  - raw.headline_pages
materialization:
  type: table
columns:
  - name: rank
    type: integer
    primary_key: true
  - name: url
    type: varchar
  - name: real_title
    type: varchar
  - name: gist
    type: varchar
  - name: lumina_twist
    type: varchar
    checks:
      - name: not_null
  - name: billboard
    type: varchar
  - name: dystopia_score
    type: integer
    checks:
      - name: min
        value: 1
      - name: max
        value: 10
  - name: entities_json
    type: varchar
@bruin"""
import json

import pandas as pd
from bruin import query

from capypunk import clients, writers


def materialize():
    pages = query("SELECT url, title, content FROM raw.headline_pages WHERE status = 'succeeded' "
                  "ORDER BY content_length DESC LIMIT 5", connection="duckdb-default").to_dict("records")
    out, usage = clients.qwen_chat(writers.digest_messages(pages), schema=writers.DIGEST_SCHEMA,
                                   schema_name="digest", max_tokens=3000)
    stories = sorted(out["stories"], key=lambda s: -s["dystopia_score"])[:3]
    print("tokens", usage.get("total_tokens"))
    return pd.DataFrame([{"rank": i + 1, "url": s["url"], "real_title": s["real_title"], "gist": s["gist"],
                          "lumina_twist": s["lumina_twist"], "billboard": s["billboard"],
                          "dystopia_score": int(s["dystopia_score"]),
                          "entities_json": json.dumps(s["real_entities"])} for i, s in enumerate(stories)])
