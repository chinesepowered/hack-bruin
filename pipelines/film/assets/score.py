"""@bruin
name: film.score
image: python:3.12
connection: duckdb-default
description: A 60-second neo-noir synth score composed by ElevenLabs Music; the player loops it quietly under the episode.
tags: [film, elevenlabs]
depends:
  - film.plan
materialization:
  type: table
columns:
  - name: path
    type: varchar
    checks:
      - name: not_null
  - name: duration_s
    type: double
    checks:
      - name: min
        value: 30
@bruin"""
import pandas as pd

from capypunk import film


def materialize():
    return pd.DataFrame([film.compose_score()])
