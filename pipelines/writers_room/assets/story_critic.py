"""@bruin
name: story.critic
image: python:3.12
connection: duckdb-default
description: |
  An independent Qwen4-Max script editor scores the final episode. Its checks gate the film pipeline:
  if the hook or the cliffhanger isn't strong enough, nothing gets rendered.
tags: [runware, qwen, writers_room, quality_gate]
depends:
  - story.episode
  - story.paths
materialization:
  type: table
columns:
  - name: episode_id
    type: varchar
    primary_key: true
  - name: hook
    type: integer
    checks:
      - name: min
        value: 7
  - name: cliffhanger
    type: integer
    checks:
      - name: min
        value: 8
  - name: overall
    type: integer
    checks:
      - name: min
        value: 7
  - name: stakes
    type: integer
  - name: characters
    type: integer
  - name: dialogue
    type: integer
  - name: coherence
    type: integer
  - name: notes
    type: varchar
@bruin"""
import json

import pandas as pd
from bruin import query

from capypunk import clients, config, writers


def materialize():
    bible = json.loads((config.SERIES / "bible.json").read_text())
    ep = query("SELECT episode_id, script_json FROM story.episode", connection="duckdb-default").iloc[0]
    verdict, usage = clients.qwen_chat(writers.critic_messages(bible, json.loads(ep["script_json"])),
                                       schema=writers.CRITIC_SCHEMA, schema_name="critique", max_tokens=6000)
    print(json.dumps({k: verdict[k] for k in ("hook", "cliffhanger", "overall")}), "|", verdict["notes"][:300])
    return pd.DataFrame([{"episode_id": ep["episode_id"], **{k: int(verdict[k]) for k in
                          ("hook", "stakes", "characters", "dialogue", "cliffhanger", "coherence", "overall")},
                          "notes": verdict["notes"] + " | fixes: " + "; ".join(verdict["fixes"])}])
