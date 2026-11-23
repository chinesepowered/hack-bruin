/* @bruin
name: story.paths
type: duckdb.sql
description: Every possible playthrough, walked through the story graph with a recursive query.
tags: [writers_room]
depends:
  - story.clips
  - story.choices
materialization:
  type: table
columns:
  - name: path
    type: varchar
    primary_key: true
  - name: ends_at
    type: varchar
    checks:
      - name: accepted_values
        value: [c04]
  - name: runtime_s
    type: integer
    checks:
      - name: min
        value: 30
      - name: max
        value: 90
custom_checks:
  - name: exactly four distinct playthroughs
    query: SELECT count(*) FROM story.paths
    value: 4
@bruin */
WITH RECURSIVE edges AS (
    SELECT clip_id AS src, unnest(from_json(next_json, '["VARCHAR"]')) AS dst, NULL::VARCHAR AS label
    FROM story.clips WHERE choice_id IS NULL
    UNION ALL
    SELECT clip_id AS src, next_clip AS dst, label FROM story.choices
),
walk(path, last, picks, runtime_s, depth) AS (
    SELECT 'c01', 'c01', '', (SELECT duration FROM story.clips WHERE clip_id = 'c01'), 1
    UNION ALL
    SELECT w.path || ' > ' || e.dst, e.dst,
           w.picks || CASE WHEN e.label IS NULL THEN '' ELSE (CASE WHEN w.picks = '' THEN '' ELSE ' / ' END) || e.label END,
           w.runtime_s + c.duration, w.depth + 1
    FROM walk w
    JOIN edges e ON e.src = w.last
    JOIN story.clips c ON c.clip_id = e.dst
    WHERE w.depth < 20
)
SELECT path, last AS ends_at, picks, runtime_s, depth AS n_clips
FROM walk
WHERE last NOT IN (SELECT src FROM edges)
ORDER BY path
