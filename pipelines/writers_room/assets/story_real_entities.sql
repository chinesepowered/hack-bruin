/* @bruin
name: story.real_entities
type: duckdb.sql
description: Every real company, product and person named in today's source articles. The fiction may never mention them.
tags: [writers_room]
depends:
  - story.headline_digest
materialization:
  type: table
columns:
  - name: entity
    type: varchar
    checks:
      - name: not_null
      - name: unique
@bruin */
SELECT DISTINCT entity
FROM (
    SELECT lower(trim(unnest(from_json(entities_json, '["VARCHAR"]')))) AS entity
    FROM story.headline_digest
)
WHERE length(entity) >= 3
