"""@bruin
name: raw.headline_pages
image: python:3.12
connection: duckdb-default
description: Full text of today's top headlines (one per query first), read as clean markdown with Telem fetch.
tags: [telem, writers_room]
depends:
  - raw.headlines
materialization:
  type: table
columns:
  - name: url
    type: varchar
    primary_key: true
    checks:
      - name: unique
  - name: title
    type: varchar
  - name: content
    type: varchar
  - name: content_length
    type: integer
  - name: provider
    type: varchar
  - name: status
    type: varchar
    checks:
      - name: accepted_values
        value: [succeeded, failed]
custom_checks:
  - name: at least 3 readable articles
    query: SELECT CASE WHEN count(*) >= 3 THEN 1 ELSE 0 END FROM raw.headline_pages WHERE status = 'succeeded' AND content_length > 800
    value: 1
@bruin"""
import pandas as pd
from bruin import query

from capypunk import clients


def materialize():
    df = query("SELECT url, title, query, rank FROM raw.headlines WHERE run_date = CURRENT_DATE ORDER BY rank",
               connection="duckdb-default")
    # round-robin across the queries so the room sees a spread of stories
    picks, seen = [], set()
    by_q ={q: g.sort_values("rank")["url"].tolist() for q, g in df.groupby("query")}
    while len(picks) < 5 and any(by_q.values()):
        for q in list(by_q):
            if by_q[q] and len(picks) < 5:
                u = by_q[q].pop(0)
                if u not in seen:
                    seen.add(u)
                    picks.append(u)
    titles = dict(zip(df["url"], df["title"]))
    docs = clients.telem_fetch(picks)
    rows = [{"url": d.get("url"), "title": d.get("title") or titles.get(d.get("url")), "content": (d.get("content") or "")[:12000],
             "content_length": int(d.get("content_length") or len(d.get("content") or "")), "provider": d.get("provider"),
             "status": d.get("status") or "failed"} for d in docs]
    print(f"fetched {sum(r['status'] == 'succeeded' for r in rows)}/{len(rows)} pages")
    return pd.DataFrame(rows)
