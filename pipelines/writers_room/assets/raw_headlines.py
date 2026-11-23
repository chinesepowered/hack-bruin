"""@bruin
name: raw.headlines
image: python:3.12
connection: duckdb-default
description: |
  Today's real AI and tech headlines, searched across several providers in one call each with
  Telem (auto-routing picks the best providers per query). Raw material for the writers' room.
tags: [telem, writers_room]
materialization:
  type: table
  strategy: merge
columns:
  - name: url
    type: varchar
    primary_key: true
    checks:
      - name: not_null
  - name: title
    type: varchar
    checks:
      - name: not_null
  - name: summary
    type: varchar
  - name: provider
    type: varchar
  - name: query
    type: varchar
  - name: rank
    type: integer
  - name: publish_date
    type: varchar
  - name: run_date
    type: date
custom_checks:
  - name: at least 5 fresh headlines
    query: SELECT CASE WHEN count(*) >= 5 THEN 1 ELSE 0 END FROM raw.headlines WHERE run_date = CURRENT_DATE
    value: 1
@bruin"""
import datetime as dt

import pandas as pd

from capypunk import clients

QUERIES = [
    "AI company unveils new AI model or AI agent",
    "emotion recognition surveillance AI news",
    "humanoid robot or robotics company announcement",
]


def materialize():
    today = dt.date.today()
    since = (today - dt.timedelta(days=4)).isoformat()
    rows = []
    for q in QUERIES:
        for r in clients.telem_search(q, num_results=6, auto_routing=True, published_after=since):
            if r.get("url") and r.get("title"):
                rows.append({"url": r["url"], "title": r["title"], "summary": (r.get("summary") or "")[:1000],
                             "provider": r.get("provider"), "query": q, "rank": int(r.get("rank") or 99),
                             "publish_date": str(r.get("publish_date") or ""), "run_date": today})
    df = pd.DataFrame(rows).sort_values("rank").drop_duplicates("url")
    print(f"{len(df)} headlines from {df['provider'].nunique()} providers")
    return df
