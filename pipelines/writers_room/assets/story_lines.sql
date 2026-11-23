/* @bruin
name: story.lines
type: duckdb.sql
description: Every spoken line (on-screen dialogue) and narration line, in order, per clip.
tags: [writers_room]
depends:
  - story.clips
  - story.real_entities
materialization:
  type: table
columns:
  - name: line_id
    type: varchar
    primary_key: true
    checks:
      - name: unique
  - name: clip_id
    type: varchar
    foreign_key:
      table: story.clips
      column: clip_id
    checks:
      - name: relationships
  - name: kind
    type: varchar
    checks:
      - name: accepted_values
        value: [dialogue, narration]
  - name: speaker
    type: varchar
    checks:
      - name: accepted_values
        value: [vex, kade, sable, narrator]
  - name: text
    type: varchar
    checks:
      - name: not_null
custom_checks:
  - name: dialogue fits the shot (max 20 words per clip)
    query: SELECT count(*) FROM (SELECT clip_id, sum(words) AS w FROM story.lines WHERE kind = 'dialogue' GROUP BY 1 HAVING w > 20)
    value: 0
  - name: no real names leak into the script
    query: |
      SELECT count(*) FROM story.lines l JOIN story.real_entities e
        ON contains(' ' || regexp_replace(lower(l.text), '[^a-z0-9]+', ' ', 'g') || ' ',
                    ' ' || trim(regexp_replace(e.entity, '[^a-z0-9]+', ' ', 'g')) || ' ')
    value: 0
  - name: the episode opens and closes on narration
    query: SELECT count(DISTINCT clip_id) FROM story.lines WHERE kind = 'narration' AND clip_id IN ('c01', 'c04')
    value: 2
@bruin */
WITH lists AS (
    SELECT clip_id, ord,
           from_json(dialogue_json, '["JSON"]')  AS dlg,
           from_json(narration_json, '["JSON"]') AS nar
    FROM story.clips
),
dialogue AS (
    SELECT clip_id, ord, 'dialogue' AS kind, i AS seq,
           dlg[i] ->> '$.speaker' AS speaker, dlg[i] ->> '$.line' AS text, NULL::DOUBLE AS start_s
    FROM (SELECT *, unnest(generate_series(1, len(dlg))) AS i FROM lists WHERE len(dlg) > 0)
),
narration AS (
    SELECT clip_id, ord, 'narration' AS kind, i AS seq,
           'narrator' AS speaker, nar[i] ->> '$.text' AS text, CAST(nar[i] ->> '$.start_s' AS DOUBLE) AS start_s
    FROM (SELECT *, unnest(generate_series(1, len(nar))) AS i FROM lists WHERE len(nar) > 0)
)
SELECT clip_id || '-' || kind || '-' || seq AS line_id, clip_id, ord, kind, seq, speaker, text, start_s,
       len(string_split(trim(text), ' ')) AS words
FROM (SELECT * FROM dialogue UNION ALL SELECT * FROM narration)
ORDER BY ord, kind, seq
