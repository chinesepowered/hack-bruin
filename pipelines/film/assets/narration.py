"""@bruin
name: film.narration
image: python:3.12
connection: duckdb-default
description: The noir narrator's lines, voiced by ElevenLabs (Eleven v3, voice "Rick").
tags: [film, elevenlabs]
depends:
  - film.plan
materialization:
  type: table
columns:
  - name: line_id
    type: varchar
    primary_key: true
  - name: duration_s
    type: double
    checks:
      - name: max
        value: 7
@bruin"""
import pandas as pd
from bruin import query

from capypunk import film


def materialize():
    lines = query("SELECT line_id, clip_id, text FROM story.lines WHERE kind = 'narration' ORDER BY ord, seq",
                  connection="duckdb-default")
    rows = [{**film.record_line(r.line_id, r.text, "wcATjh8zBDfepqUbl99V"), "clip_id": r.clip_id, "text": r.text}
            for r in lines.itertuples()]
    return pd.DataFrame(rows)
