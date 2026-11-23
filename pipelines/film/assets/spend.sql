/* @bruin
name: film.spend
type: duckdb.sql
description: What the episode actually cost to render, per item, audited against the budget.
tags: [film, quality_gate]
depends:
  - film.clip_c01
  - film.clip_c02
  - film.clip_a1
  - film.clip_b1
  - film.clip_c03
  - film.clip_d1
  - film.clip_d2
  - film.clip_c04
  - film.still_s01
  - film.still_s02
  - film.still_s03
  - film.still_s04a
  - film.still_s04b
  - film.still_s05
  - film.still_s06
  - film.still_s07
  - film.still_s08
  - film.plan
materialization:
  type: table
custom_checks:
  - name: actual spend within budget
    query: SELECT count(*) FROM (SELECT sum(cost_usd) AS s FROM film.spend) WHERE s > (SELECT budget_usd FROM film.plan)
    value: 0
@bruin */
SELECT 'clip' AS kind, clip_id AS item, cost_usd, takes, render_s, dialogue_match, qa_score FROM (
    SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_c01
    UNION ALL BY NAME SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_c02
    UNION ALL BY NAME SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_a1
    UNION ALL BY NAME SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_b1
    UNION ALL BY NAME SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_c03
    UNION ALL BY NAME SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_d1
    UNION ALL BY NAME SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_d2
    UNION ALL BY NAME SELECT clip_id, cost_usd, takes, render_s, dialogue_match, qa_score FROM film.clip_c04
)
UNION ALL BY NAME
SELECT 'still' AS kind, still_id AS item, cost_usd, takes, NULL AS render_s, NULL AS dialogue_match, qa_score FROM (
    SELECT still_id, cost_usd, takes, qa_score FROM film.still_s01
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s02
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s03
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s04a
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s04b
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s05
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s06
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s07
    UNION ALL BY NAME SELECT still_id, cost_usd, takes, qa_score FROM film.still_s08
)
