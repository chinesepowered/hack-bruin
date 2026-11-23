/* @bruin
name: story.clips
type: duckdb.sql
description: One row per clip, joining the bible's fixed structure with the writers' room's scene direction.
tags: [writers_room]
depends:
  - story.structure
  - story.episode
  - story.stills
materialization:
  type: table
columns:
  - name: clip_id
    type: varchar
    primary_key: true
    checks:
      - name: unique
  - name: start_still
    type: varchar
    foreign_key:
      table: story.stills
      column: still_id
    checks:
      - name: relationships
  - name: end_still
    type: varchar
    foreign_key:
      table: story.stills
      column: still_id
    checks:
      - name: relationships
  - name: duration
    type: integer
  - name: action
    type: varchar
    description: the video-model prompt for this shot
    checks:
      - name: not_null
@bruin */
WITH ep AS (
    SELECT script_json FROM story.episode WHERE episode_id = 'ep01'
),
llm AS (
    SELECT c ->> '$.id'                     AS clip_id,
           c ->> '$.action'                 AS action,
           c ->> '$.sfx'                    AS sfx,
           CAST(c -> '$.dialogue' AS VARCHAR)  AS dialogue_json,
           CAST(c -> '$.narration' AS VARCHAR) AS narration_json
    FROM (SELECT unnest(from_json(json_extract(script_json, '$.clips'), '["JSON"]')) AS c FROM ep)
)
SELECT s.clip_id, s.ord, s.title, s.start_still, s.end_still, s.duration, s.beat, s.choice_id, s.next_json,
       l.action, l.sfx, coalesce(l.dialogue_json, '[]') AS dialogue_json, coalesce(l.narration_json, '[]') AS narration_json
FROM story.structure s
LEFT JOIN llm l USING (clip_id)
ORDER BY s.ord
