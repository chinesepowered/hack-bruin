"""@bruin
name: raw.episode2_signals
image: python:3.12
connection: duckdb-default
description: |
  What the Telem monitor's agent found since the last run: new items, changed values, verdicts and alerts about
  real emotion-recognition and biometric-surveillance news. Read incrementally from the last `seq` stored in this
  table (Telem's own cursor pattern). These seed the next episode's Lumina announcement. Row seq=0 records the
  monitor's status at each poll.
tags: [telem, monitor, writers_room]
materialization:
  type: table
  strategy: merge
columns:
  - name: seq
    type: integer
    primary_key: true
    checks:
      - name: not_null
  - name: kind
    type: varchar
  - name: subject
    type: varchar
  - name: detail_json
    type: varchar
  - name: polled_at
    type: timestamp
@bruin"""
import datetime as dt
import json

import pandas as pd
from bruin import query

from capypunk import clients, config


def materialize():
    monitor_id = json.loads((config.SERIES / "monitor.json").read_text())["monitor_id"]
    try:
        cursor = int(query("SELECT coalesce(max(seq), 0) AS s FROM raw.episode2_signals",
                           connection="duckdb-default")["s"].iloc[0])
    except Exception:  # first run: the table does not exist yet
        cursor = 0
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    rows, page_guard = [], 0
    while page_guard < 20:
        page_guard += 1
        page = clients.telem("GET", f"/monitors/{monitor_id}/agent/changes", params={"cursor": cursor}) or {}
        for ch in page.get("changes") or []:
            subj = ch.get("subject") or {}
            rows.append({"seq": int(ch["seq"]), "kind": ch.get("kind"), "subject": subj.get("name"),
                         "detail_json": json.dumps({k: ch.get(k) for k in ("type", "before", "after", "subject")}, default=str),
                         "polled_at": now})
        nxt = page.get("next_cursor")
        if not page.get("changes") or nxt is None or nxt == cursor or nxt == page.get("watermark"):
            break
        cursor = nxt
    mon = clients.telem("GET", f"/monitors/{monitor_id}") or {}
    state = mon.get("agent_state") or {}
    rows.append({"seq": 0, "kind": "status", "subject": mon.get("query"),
                 "detail_json": json.dumps({"status": mon.get("status"), "agent": state.get("status"),
                                            "watermark": state.get("watermark"), "expires_at": mon.get("expires_at"),
                                            "new_changes": len(rows)}, default=str),
                 "polled_at": now})
    print(f"monitor {monitor_id}: {len(rows) - 1} new changes, agent {state.get('status')}")
    return pd.DataFrame(rows)
