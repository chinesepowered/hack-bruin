/* @bruin
name: story.stills
type: duckdb.sql
description: The anchor frames to paint, with the writers' room's image prompt for each.
tags: [writers_room]
depends:
  - story.still_specs
  - story.episode
  - story.real_entities
materialization:
  type: table
columns:
  - name: still_id
    type: varchar
    primary_key: true
    checks:
      - name: unique
  - name: prompt
    type: varchar
    checks:
      - name: not_null
custom_checks:
  - name: every still in the bible has a prompt
    query: SELECT count(*) FROM story.stills WHERE prompt IS NULL OR length(prompt) < 40
    value: 0
  - name: no real names leak into image prompts
    query: |
      SELECT count(*) FROM story.stills s JOIN story.real_entities e
        ON contains(' ' || regexp_replace(lower(s.prompt), '[^a-z0-9]+', ' ', 'g') || ' ',
                    ' ' || trim(regexp_replace(e.entity, '[^a-z0-9]+', ' ', 'g')) || ' ')
    value: 0
@bruin */
WITH ep AS (
    SELECT script_json FROM story.episode WHERE episode_id = 'ep01'
),
llm AS (
    SELECT s ->> '$.id' AS still_id, s ->> '$.prompt' AS prompt
    FROM (SELECT unnest(from_json(json_extract(script_json, '$.stills'), '["JSON"]')) AS s FROM ep)
)
SELECT p.still_id, p.chars_json, p.parent_still, p.what, l.prompt
FROM story.still_specs p
LEFT JOIN llm l USING (still_id)
ORDER BY p.still_id
