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
    '{{ var.resolution }}'                AS resolution,
    round((SELECT count(*) FROM story.stills) * 0.0141 * 3
          + (SELECT sum(duration) FROM story.clips)
            * CASE '{{ var.resolution }}' WHEN '1080p' THEN 0.28 WHEN '720p' THEN 0.14 ELSE 0.068 END * 2, 2)
                                             AS planned_usd,
    CAST({{ var.budget_usd }} AS DOUBLE)  AS budget_usd
