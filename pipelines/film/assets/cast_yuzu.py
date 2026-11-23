"""@bruin
name: film.cast_yuzu
image: python:3.12
connection: duckdb-default
description: Yuzu's locked character sheet (series/cast/yuzu.jpg), registered with Runware as a reference image.
tags: [film, cast, runware]
depends:
  - film.plan
materialization:
  type: table
columns:
  - name: char_id
    type: varchar
    primary_key: true
  - name: ref
    type: varchar
    checks:
      - name: not_null
@bruin"""
import pandas as pd

from capypunk import film


def materialize():
    return pd.DataFrame([film.register_cast("yuzu")])
