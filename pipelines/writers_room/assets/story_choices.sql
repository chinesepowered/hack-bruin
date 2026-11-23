/* @bruin
name: story.choices
type: duckdb.sql
description: The viewer's decisions, with the writers' room's final button labels.
tags: [writers_room]
depends:
  - story.choice_options
  - story.episode
  - story.clips
materialization:
  type: table
columns:
  - name: option_key
    type: varchar
    primary_key: true
  - name: label
    type: varchar
    checks:
      - name: not_null
  - name: next_clip
    type: varchar
    foreign_key:
      table: story.clips
      column: clip_id
    checks:
      - name: relationships
custom_checks:
  - name: every decision has exactly two options
    query: SELECT count(*) FROM (SELECT choice_id FROM story.choices GROUP BY 1 HAVING count(*) <> 2)
    value: 0
@bruin */
WITH ep AS (
    SELECT script_json FROM story.episode WHERE episode_id = 'ep01'
)
SELECT o.option_key, o.choice_id, o.clip_id, o.option_idx, o.prompt,
       coalesce(nullif(json_extract_string(ep.script_json, '$.choice_labels.' || o.option_key), ''), o.default_label) AS label,
       o.next_clip
FROM story.choice_options o, ep
ORDER BY o.option_key
