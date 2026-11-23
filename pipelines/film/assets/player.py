"""@bruin
name: film.player
image: python:3.12
connection: duckdb-default
description: Builds the interactive player (player/dist) from the manifest, the story graph and any vibe checks.
tags: [film, player]
depends:
  - film.manifest
  - film.spend
  - film.score
materialization:
  type: table
columns:
  - name: built_at
    type: timestamp
@bruin"""
import pandas as pd

from capypunk import player


def materialize():
    return pd.DataFrame([player.build()])
