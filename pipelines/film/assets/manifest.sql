/* @bruin
name: film.manifest
type: duckdb.sql
description: Everything the player needs, one row per clip.
tags: [film]
depends:
  - film.cut_c01
  - film.cut_c02
  - film.cut_a1
  - film.cut_b1
  - film.cut_c03
  - film.cut_d1
  - film.cut_d2
  - film.cut_c04
  - film.still_s01
  - film.still_s02
  - film.still_s03
  - film.still_s04a
  - film.still_s04b
  - film.still_s05
  - film.still_s06
  - film.still_s07
  - film.still_s08
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
    SELECT * FROM film.cut_c01
    UNION ALL BY NAME SELECT * FROM film.cut_c02
    UNION ALL BY NAME SELECT * FROM film.cut_a1
    UNION ALL BY NAME SELECT * FROM film.cut_b1
    UNION ALL BY NAME SELECT * FROM film.cut_c03
    UNION ALL BY NAME SELECT * FROM film.cut_d1
    UNION ALL BY NAME SELECT * FROM film.cut_d2
    UNION ALL BY NAME SELECT * FROM film.cut_c04
)
SELECT c.clip_id, c.ord, c.title, c.duration, c.choice_id, c.next_json, c.start_still, c.end_still,
       cu.path AS video, cu.vtt_path AS vtt, cu.duration_s
FROM story.clips c
JOIN cuts cu USING (clip_id)
ORDER BY c.ord
