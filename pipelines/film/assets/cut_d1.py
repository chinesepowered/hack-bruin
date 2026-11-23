"""@bruin
name: film.cut_d1
image: python:3.12
connection: duckdb-default
description: |
  Final cut of "The Handover": narration mixed in (slid into gaps in the dialogue), H.264 for the web, subtitles timed from Scribe.
tags: [film, cut]
depends:
  - film.clip_d1
  - film.narration
materialization:
  type: table
columns:
  - name: clip_id
    type: varchar
    primary_key: true
  - name: size_mb
    type: double
    checks:
      - name: max
        value: 15
@bruin"""
import json

import pandas as pd
from bruin import query

from capypunk import config, film

CLIP_ID = "d1"


def materialize():
    q = lambda sql: query(sql, connection="duckdb-default")
    clip = q(f"SELECT path FROM film.clip_{CLIP_ID}").iloc[0]
    c = q(f"SELECT dialogue_json, narration_json FROM story.clips WHERE clip_id = '{CLIP_ID}'").iloc[0]
    voices = {r["line_id"]: r for r in q(f"SELECT * FROM film.narration WHERE clip_id = '{CLIP_ID}'").to_dict("records")}
    words = json.loads((config.MEDIA / "film" / "clips" / f"{CLIP_ID}.words.json").read_text())
    return pd.DataFrame([film.cut_clip(CLIP_ID, clip["path"], words, json.loads(c["dialogue_json"]),
                                       json.loads(c["narration_json"]), voices)])
