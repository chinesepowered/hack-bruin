"""@bruin
name: vibes.ig_profiles
image: python:3.12
connection: duckdb-default
description: |
  Each opted-in viewer's public Instagram profile and 12 most recent posts, bought per call through Glasser
  (AnyAPI's Instagram endpoints, about a tenth of a cent each). Every charge and Run URL is kept for audit.
tags: [vibes, glasser]
depends:
  - vibes.viewers
materialization:
  type: table
columns:
  - name: handle
    type: varchar
    primary_key: true
  - name: found
    type: boolean
  - name: private
    type: boolean
  - name: posts_json
    type: varchar
  - name: glasser_usd
    type: double
    checks:
      - name: max
        value: 0.01
  - name: profile_run_url
    type: varchar
  - name: posts_run_url
    type: varchar
custom_checks:
  - name: every opted-in viewer was looked up
    query: SELECT count(*) FROM vibes.viewers v LEFT JOIN vibes.ig_profiles p USING (handle) WHERE p.handle IS NULL
    value: 0
@bruin"""
import json
from decimal import Decimal

import pandas as pd
from bruin import query

from capypunk import clients


def _data(run: dict) -> dict:
    status = (run.get("provider_response") or {}).get("http_status")
    print(f"  {run.get('endpoint')}: {run.get('status')} provider={status} charge=${run.get('charge_usd')} {run.get('run_url')}")
    return ((run.get("output") or {}).get("output") or run.get("output") or {}).get("data") or {}


def materialize():
    rows = []
    for handle in query("SELECT handle FROM vibes.viewers", connection="duckdb-default")["handle"]:
        meta = {"pipeline": "vibes", "handle": handle}
        prof_run = clients.glasser_run("anyapi", "/instagram.profile", {"handle": handle}, metadata=meta)
        posts_run = clients.glasser_run("anyapi", "/instagram.user_posts", {"handle": handle}, metadata=meta)
        prof, posts = _data(prof_run), _data(posts_run).get("posts") or []
        slim = [{"caption": (p.get("caption") or "")[:400], "likes": p.get("likes"), "type": p.get("productType"),
                 "hashtags": p.get("hashtags"), "image": ((p.get("media") or [{}])[0]).get("url")} for p in posts]
        charge = sum(Decimal(str(r.get("charge_usd") or "0")) for r in (prof_run, posts_run))
        rows.append({"handle": handle, "found": bool(prof), "private": bool(prof.get("private")),
                     "bio": prof.get("bio"), "posts_count": prof.get("posts"),
                     "link_titles": json.dumps([b.get("title") for b in prof.get("bioLinks") or []]),
                     "posts_json": json.dumps(slim, ensure_ascii=False), "glasser_usd": float(charge),
                     "profile_run_url": prof_run.get("run_url"), "posts_run_url": posts_run.get("run_url")})
    return pd.DataFrame(rows)
