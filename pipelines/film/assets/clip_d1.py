"""@bruin
name: film.clip_d1
image: python:3.12
connection: duckdb-default
description: |
  "The Handover": 8s rendered by Wan 3.0 Prime between stills s06 and s07, with native
  lip-synced dialogue. ElevenLabs Scribe transcribes it to verify the lines were spoken; Qwen4-Max checks
  sampled frames. One retake with a new seed if the dialogue check fails.
tags: [film, clip, runware, wan]
depends:
  - film.still_s06
  - film.still_s07
  - film.cast_yuzu
  - film.cast_sable
materialization:
  type: table
columns:
  - name: clip_id
    type: varchar
    primary_key: true
  - name: has_audio
    type: boolean
  - name: dialogue_match
    type: double
custom_checks:
  - name: clip runs the planned length
    query: SELECT count(*) FROM film.clip_d1 WHERE abs(duration_s - planned_s) > 1.0 OR NOT has_audio
    value: 0
  - name: the actors said their lines
    query: SELECT count(*) FROM film.clip_d1 WHERE has_dialogue AND dialogue_match < 0.6
    value: 0
    blocking: false
@bruin"""
import json

import pandas as pd
from bruin import context, query

from capypunk import film

CLIP_ID, START, END, CHARS = "d1", "s06", 's07', ['yuzu', 'sable']


def materialize():
    q = lambda sql: query(sql, connection="duckdb-default")
    c = q(f"SELECT action, sfx, dialogue_json, duration FROM story.clips WHERE clip_id = '{CLIP_ID}'").iloc[0]
    first = q(f"SELECT url FROM film.still_{START}").iloc[0].to_dict()
    last = q(f"SELECT url FROM film.still_{END}").iloc[0].to_dict() if END else None
    cast = {x: q(f"SELECT * FROM film.cast_{x}").iloc[0].to_dict() for x in CHARS}
    resolution = (context.vars or {}).get("resolution", "1080p")
    row = film.shoot_clip(CLIP_ID, c["action"], json.loads(c["dialogue_json"]), c["sfx"], int(c["duration"]),
                          CHARS, first, last, cast, resolution)
    return pd.DataFrame([row])
