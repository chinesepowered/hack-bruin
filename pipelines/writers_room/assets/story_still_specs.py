"""@bruin
name: story.still_specs
image: python:3.12
connection: duckdb-default
description: The anchor frames from the series bible, who appears in each, and which earlier still it continues from.
tags: [bible, writers_room]
materialization:
  type: table
columns:
  - name: still_id
    type: varchar
    primary_key: true
    checks:
      - name: unique
  - name: chars_json
    type: varchar
  - name: parent_still
    type: varchar
  - name: what
    type: varchar
@bruin"""
import json

import pandas as pd

from capypunk import config


def materialize():
    bible = json.loads((config.SERIES / "bible.json").read_text())
    spec = bible["structure"]["stills_spec"]
    return pd.DataFrame([{"still_id": sid, "chars_json": json.dumps(s["chars"]), "parent_still": s.get("parent"),
                          "what": s["what"]} for sid, s in spec.items()])
