"""@bruin
name: story.structure
image: python:3.12
connection: duckdb-default
description: The episode's fixed branching structure from the series bible (one row per clip).
tags: [bible, writers_room]
materialization:
  type: table
columns:
  - name: clip_id
    type: varchar
    primary_key: true
    checks:
      - name: unique
      - name: not_null
  - name: ord
    type: integer
  - name: title
    type: varchar
  - name: start_still
    type: varchar
    checks:
      - name: not_null
  - name: end_still
    type: varchar
  - name: duration
    type: integer
    checks:
      - name: min
        value: 4
      - name: max
        value: 12
  - name: beat
    type: varchar
  - name: choice_id
    type: varchar
  - name: next_json
    type: varchar
@bruin"""
import json

import pandas as pd

from capypunk import config


def materialize():
    bible = json.loads((config.SERIES / "bible.json").read_text())
    rows = []
    for i, c in enumerate(bible["structure"]["clips"]):
        rows.append({"clip_id": c["id"], "ord": i + 1, "title": c["title"], "start_still": c["start"],
                     "end_still": c.get("end"), "duration": int(c["duration"]), "beat": c.get("beat"),
                     "choice_id": (c.get("choice") or {}).get("id"), "next_json": json.dumps(c.get("next", []))})
    return pd.DataFrame(rows)
