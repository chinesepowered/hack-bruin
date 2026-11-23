"""@bruin
name: story.choice_options
image: python:3.12
connection: duckdb-default
description: The decision points from the series bible and where each option leads.
tags: [bible, writers_room]
materialization:
  type: table
columns:
  - name: option_key
    type: varchar
    primary_key: true
  - name: choice_id
    type: varchar
  - name: clip_id
    type: varchar
  - name: option_idx
    type: integer
  - name: prompt
    type: varchar
  - name: default_label
    type: varchar
  - name: next_clip
    type: varchar
    checks:
      - name: not_null
@bruin"""
import json

import pandas as pd

from capypunk import config


def materialize():
    bible = json.loads((config.SERIES / "bible.json").read_text())
    rows = []
    for c in bible["structure"]["clips"]:
        ch = c.get("choice")
        if not ch:
            continue
        for i, o in enumerate(ch["options"]):
            rows.append({"option_key": f"{ch['id']}_{'ab'[i]}", "choice_id": ch["id"], "clip_id": c["id"],
                         "option_idx": i, "prompt": ch["prompt"], "default_label": o["label"], "next_clip": o["next"]})
    return pd.DataFrame(rows)
