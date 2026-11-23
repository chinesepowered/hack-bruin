"""@bruin
name: film.still_s08
image: python:3.12
connection: duckdb-default
description: |
  Anchor frame s08: c04 start: wide shot of Halcyon City at night, orbs with red irises, billboards showing Yuzu's face.
  Painted by Qwen-Image 2.1 Turbo from the writers' room prompt with the cast sheets as references,
  then checked by Qwen4-Max; the best of up to 3 takes is kept.
tags: [film, still, runware, qwen]
depends:
  - film.cast_yuzu
materialization:
  type: table
columns:
  - name: still_id
    type: varchar
    primary_key: true
  - name: url
    type: varchar
    checks:
      - name: not_null
  - name: qa_score
    type: integer
    checks:
      - name: min
        value: 6
custom_checks:
  - name: characters are on-model
    query: SELECT count(*) FROM film.still_s08 WHERE NOT on_model
    value: 0
    blocking: false
@bruin"""
import pandas as pd
from bruin import query

from capypunk import film

STILL_ID, CHARS, PARENT = "s08", ['yuzu'], None


def materialize():
    brief = query(f"SELECT prompt FROM story.stills WHERE still_id = '{STILL_ID}'", connection="duckdb-default").iloc[0]["prompt"]
    note = film.bible()["structure"]["stills_spec"][STILL_ID].get("director_note")
    if note:
        brief = f"{brief} Director's note, which overrides the framing above: {note}"
    cast = {c: query(f"SELECT * FROM film.cast_{c}", connection="duckdb-default").iloc[0].to_dict() for c in CHARS}
    parent = query(f"SELECT url FROM film.still_{PARENT}", connection="duckdb-default").iloc[0].to_dict() if PARENT else None
    return pd.DataFrame([film.paint_still(STILL_ID, brief, CHARS, cast, parent)])
