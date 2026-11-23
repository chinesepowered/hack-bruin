"""Compile the episode's story graph (series/bible.json) into the `film` Bruin pipeline.

One asset per cast member, per anchor still and per clip, plus narration, final cuts, a budget
gate, a spend audit, the manifest and the player build. Dependencies follow the story: a still
depends on the cast in it and the still it continues from; a clip depends on the stills it runs
between; a cut depends on its clip and the narration. Re-run it whenever the structure changes.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "pipelines" / "film"
ASSETS = OUT / "assets"
bible = json.loads((REPO / "series" / "bible.json").read_text())
clips = bible["structure"]["clips"]
spec = bible["structure"]["stills_spec"]
CAST = ["yuzu", "vex", "kade", "sable"]

for old in ASSETS.glob("*"):
    if old.is_file():
        old.unlink()
ASSETS.mkdir(parents=True, exist_ok=True)

(OUT / "pipeline.yml").write_text("""name: film
default_connections:
  duckdb: duckdb-default
variables:
  resolution:
    type: string
    default: "1080p"
  budget_usd:
    type: number
    default: 40
default:
  # inject_as spelled out: see patches/ for the upstream fix to pipeline-level default secrets
  secrets:
    - key: RUNWARE_API_KEY
      inject_as: RUNWARE_API_KEY
    - key: ELEVENLABS_API_KEY
      inject_as: ELEVENLABS_API_KEY
    - key: duckdb-default
      inject_as: duckdb-default
""")


def write(name: str, text: str):
    (ASSETS / name).write_text(text.lstrip("\n"))


def deps(items):
    return "\n".join(f"  - {d}" for d in items)


# ---------------------------------------------------------------- budget gate
write("plan.sql", f"""
/* @bruin
name: film.plan
type: duckdb.sql
description: |
  The render plan and its worst-case cost (3 takes per still, 2 per clip). Blocking budget gate:
  if the plan could cost more than the budget, no still or clip renders.
tags: [film, quality_gate]
materialization:
  type: table
columns:
  - name: planned_usd
    type: double
custom_checks:
  - name: worst case fits the render budget
    query: SELECT count(*) FROM film.plan WHERE planned_usd > budget_usd
    value: 0
  - name: the critic signed off on the script
    query: SELECT count(*) FROM story.critic WHERE overall < 7 OR cliffhanger < 8
    value: 0
@bruin */
SELECT
    (SELECT count(*) FROM story.stills)      AS n_stills,
    (SELECT count(*) FROM story.clips)       AS n_clips,
    (SELECT sum(duration) FROM story.clips)  AS footage_s,
    '{{{{ var.resolution }}}}'                AS resolution,
    round((SELECT count(*) FROM story.stills) * 0.0141 * 3
          + (SELECT sum(duration) FROM story.clips)
            * CASE '{{{{ var.resolution }}}}' WHEN '1080p' THEN 0.28 WHEN '720p' THEN 0.14 ELSE 0.068 END * 2, 2)
                                             AS planned_usd,
    CAST({{{{ var.budget_usd }}}} AS DOUBLE)  AS budget_usd
""")

# ---------------------------------------------------------------- cast
for c in CAST:
    name = bible["characters"][c]["name"]
    write(f"cast_{c}.py", f'''
"""@bruin
name: film.cast_{c}
image: python:3.12
connection: duckdb-default
description: {name}'s locked character sheet (series/cast/{c}.jpg), registered with Runware as a reference image.
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
    return pd.DataFrame([film.register_cast("{c}")])
''')

# ---------------------------------------------------------------- stills
for sid, s in spec.items():
    parent = s.get("parent")
    d = [f"film.cast_{c}" for c in s["chars"]] + ([f"film.still_{parent}"] if parent else [])
    write(f"still_{sid}.py", f'''
"""@bruin
name: film.still_{sid}
image: python:3.12
connection: duckdb-default
description: |
  Anchor frame {sid}: {s["what"]}.
  Painted by Qwen-Image 2.1 Turbo from the writers' room prompt with the cast sheets{" and the previous still" if parent else ""} as references,
  then checked by Qwen4-Max; the best of up to 3 takes is kept.
tags: [film, still, runware, qwen]
depends:
{deps(d)}
materialization:
  type: table
columns:
  - name: still_id
    type: varchar
    primary_key: true
  - name: url
    type: varchar
    checks:
      - name: not_null
  - name: qa_score
    type: integer
    checks:
      - name: min
        value: 6
custom_checks:
  - name: characters are on-model
    query: SELECT count(*) FROM film.still_{sid} WHERE NOT on_model
    value: 0
    blocking: false
@bruin"""
import pandas as pd
from bruin import query

from capypunk import film

STILL_ID, CHARS, PARENT = "{sid}", {s["chars"]!r}, {parent!r}


def materialize():
    brief = query(f"SELECT prompt FROM story.stills WHERE still_id = '{{STILL_ID}}'", connection="duckdb-default").iloc[0]["prompt"]
    note = film.bible()["structure"]["stills_spec"][STILL_ID].get("director_note")
    if note:
        brief = f"{{brief}} Director's note, which overrides the framing above: {{note}}"
    cast = {{c: query(f"SELECT * FROM film.cast_{{c}}", connection="duckdb-default").iloc[0].to_dict() for c in CHARS}}
    parent = query(f"SELECT url FROM film.still_{{PARENT}}", connection="duckdb-default").iloc[0].to_dict() if PARENT else None
    return pd.DataFrame([film.paint_still(STILL_ID, brief, CHARS, cast, parent)])
''')

# ---------------------------------------------------------------- clips
for c in clips:
    cid, start, end = c["id"], c["start"], c.get("end")
    chars = sorted(set(spec[start]["chars"]) | set(spec[end]["chars"] if end else []), key=CAST.index)
    d = [f"film.still_{start}"] + ([f"film.still_{end}"] if end else []) + [f"film.cast_{x}" for x in chars]
    write(f"clip_{cid}.py", f'''
"""@bruin
name: film.clip_{cid}
image: python:3.12
connection: duckdb-default
description: |
  "{c["title"]}": {c["duration"]}s rendered by Wan 3.0 Prime {"between stills " + start + " and " + end if end else "from still " + start}, with native
  lip-synced dialogue. ElevenLabs Scribe transcribes it to verify the lines were spoken; Qwen4-Max checks
  sampled frames. One retake with a new seed if the dialogue check fails.
tags: [film, clip, runware, wan]
depends:
{deps(d)}
materialization:
  type: table
columns:
  - name: clip_id
    type: varchar
    primary_key: true
  - name: has_audio
    type: boolean
  - name: dialogue_match
    type: double
custom_checks:
  - name: clip runs the planned length
    query: SELECT count(*) FROM film.clip_{cid} WHERE abs(duration_s - planned_s) > 1.0 OR NOT has_audio
    value: 0
  - name: the actors said their lines
    query: SELECT count(*) FROM film.clip_{cid} WHERE has_dialogue AND dialogue_match < 0.6
    value: 0
    blocking: false
@bruin"""
import json

import pandas as pd
from bruin import context, query

from capypunk import film

CLIP_ID, START, END, CHARS = "{cid}", "{start}", {end!r}, {chars!r}


def materialize():
    q = lambda sql: query(sql, connection="duckdb-default")
    c = q(f"SELECT action, sfx, dialogue_json, duration FROM story.clips WHERE clip_id = '{{CLIP_ID}}'").iloc[0]
    first = q(f"SELECT url FROM film.still_{{START}}").iloc[0].to_dict()
    last = q(f"SELECT url FROM film.still_{{END}}").iloc[0].to_dict() if END else None
    cast = {{x: q(f"SELECT * FROM film.cast_{{x}}").iloc[0].to_dict() for x in CHARS}}
    resolution = (context.vars or {{}}).get("resolution", "1080p")
    row = film.shoot_clip(CLIP_ID, c["action"], json.loads(c["dialogue_json"]), c["sfx"], int(c["duration"]),
                          CHARS, first, last, cast, resolution)
    return pd.DataFrame([row])
''')

# ---------------------------------------------------------------- narration
narrator = bible["characters"]["narrator"]["voice"]["voice_id"]
write("narration.py", f'''
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
    rows = [{{**film.record_line(r.line_id, r.text, "{narrator}"), "clip_id": r.clip_id, "text": r.text}}
            for r in lines.itertuples()]
    return pd.DataFrame(rows)
''')

# ---------------------------------------------------------------- score
write("score.py", '''
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
''')

# ---------------------------------------------------------------- cuts
for c in clips:
    cid = c["id"]
    write(f"cut_{cid}.py", f'''
"""@bruin
name: film.cut_{cid}
image: python:3.12
connection: duckdb-default
description: |
  Final cut of "{c["title"]}": narration mixed in (slid into gaps in the dialogue), H.264 for the web, subtitles timed from Scribe.
tags: [film, cut]
depends:
  - film.clip_{cid}
  - film.narration
materialization:
  type: table
columns:
  - name: clip_id
    type: varchar
    primary_key: true
  - name: size_mb
    type: double
    checks:
      - name: max
        value: 15
@bruin"""
import json

import pandas as pd
from bruin import query

from capypunk import config, film

CLIP_ID = "{cid}"


def materialize():
    q = lambda sql: query(sql, connection="duckdb-default")
    clip = q(f"SELECT path FROM film.clip_{{CLIP_ID}}").iloc[0]
    c = q(f"SELECT dialogue_json, narration_json FROM story.clips WHERE clip_id = '{{CLIP_ID}}'").iloc[0]
    voices = {{r["line_id"]: r for r in q(f"SELECT * FROM film.narration WHERE clip_id = '{{CLIP_ID}}'").to_dict("records")}}
    words = json.loads((config.MEDIA / "film" / "clips" / f"{{CLIP_ID}}.words.json").read_text())
    return pd.DataFrame([film.cut_clip(CLIP_ID, clip["path"], words, json.loads(c["dialogue_json"]),
                                       json.loads(c["narration_json"]), voices)])
''')

# ---------------------------------------------------------------- manifest + spend + player
cut_union = "\n    UNION ALL BY NAME ".join(f"SELECT * FROM film.cut_{c['id']}" for c in clips)
clip_union = "\n    UNION ALL BY NAME ".join(f"SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_{c['id']}" for c in clips)
still_union = "\n    UNION ALL BY NAME ".join(f"SELECT still_id, cost_usd, takes, qa_score FROM film.still_{s}" for s in spec)
write("manifest.sql", f"""
/* @bruin
name: film.manifest
type: duckdb.sql
description: Everything the player needs, one row per clip.
tags: [film]
depends:
{deps([f"film.cut_{c['id']}" for c in clips] + [f"film.still_{s}" for s in spec])}
materialization:
  type: table
columns:
  - name: clip_id
    type: varchar
    primary_key: true
  - name: video
    type: varchar
    checks:
      - name: not_null
@bruin */
WITH cuts AS (
    {cut_union}
)
SELECT c.clip_id, c.ord, c.title, c.duration, c.choice_id, c.next_json, c.start_still, c.end_still,
       cu.path AS video, cu.vtt_path AS vtt, cu.duration_s
FROM story.clips c
JOIN cuts cu USING (clip_id)
ORDER BY c.ord
""")

write("spend.sql", f"""
/* @bruin
name: film.spend
type: duckdb.sql
description: What the episode actually cost to render, per item, audited against the budget.
tags: [film, quality_gate]
depends:
{deps([f"film.clip_{c['id']}" for c in clips] + [f"film.still_{s}" for s in spec] + ["film.plan"])}
materialization:
  type: table
custom_checks:
  - name: actual spend within budget
    query: SELECT count(*) FROM (SELECT sum(cost_usd) AS s FROM film.spend) WHERE s > (SELECT budget_usd FROM film.plan)
    value: 0
@bruin */
SELECT 'clip' AS kind, clip_id AS item, cost_usd, takes, render_s, dialogue_match, qa_score FROM (
    {clip_union}
)
UNION ALL BY NAME
SELECT 'still' AS kind, still_id AS item, cost_usd, takes, NULL AS render_s, NULL AS dialogue_match, qa_score FROM (
    {still_union}
)
""")

write("player.py", '''
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
''')

print(f"compiled {len(list(ASSETS.glob('*')))} assets into {OUT.relative_to(REPO)}")
