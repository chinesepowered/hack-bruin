"""@bruin
name: story.episode
image: python:3.12
connection: duckdb-default
description: |
  The writers' room. Qwen4-Max (via Runware) writes Episode 1 from the series bible's beat sheet and
  today's fictionalized headlines, then critiques and revises its own draft until it clears the bar.
tags: [runware, qwen, writers_room]
depends:
  - story.headline_digest
  - story.structure
  - story.still_specs
  - story.choice_options
materialization:
  type: table
columns:
  - name: episode_id
    type: varchar
    primary_key: true
  - name: episode_title
    type: varchar
    checks:
      - name: not_null
  - name: headline_hook
    type: varchar
  - name: billboard
    type: varchar
  - name: cliffhanger_card
    type: varchar
  - name: script_json
    type: varchar
    checks:
      - name: not_null
  - name: self_critique_json
    type: varchar
  - name: rounds
    type: integer
  - name: tokens
    type: integer
  - name: written_at
    type: timestamp
@bruin"""
import datetime as dt
import json

import pandas as pd
from bruin import query

from capypunk import config, writers


def materialize():
    bible = json.loads((config.SERIES / "bible.json").read_text())
    digest = query("SELECT gist, lumina_twist, billboard FROM story.headline_digest ORDER BY rank",
                   connection="duckdb-default").to_dict("records")
    script, critique, rounds, tokens = writers.write_episode(bible, digest)
    print(f"rounds={rounds} overall={critique['overall']} cliffhanger={critique['cliffhanger']} tokens={tokens}")
    return pd.DataFrame([{
        "episode_id": "ep01", "episode_title": script["episode_title"], "headline_hook": script["headline_hook"],
        "billboard": script["billboard"], "cliffhanger_card": script["cliffhanger_card"],
        "script_json": json.dumps(script, ensure_ascii=False), "self_critique_json": json.dumps(critique),
        "rounds": rounds, "tokens": tokens, "written_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    }])
