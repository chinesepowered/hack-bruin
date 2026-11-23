"""Write player/dist/pipeline.html: the three Bruin pipelines, their lineage and every quality check.

Built from `bruin internal parse-pipeline`, so it always matches the code. Usage:
    python3 scripts/lineage_page.py <path-to-bruin-binary>
"""
import html
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRUIN = sys.argv[1] if len(sys.argv) > 1 else "bruin"
PIPES = [("writers_room", "Writers' room", "Today's headlines (Telem) become a checked, branching script (Qwen4-Max)."),
         ("film", "Film", "The story graph compiled into a render pipeline: stills, Wan clips, voices, cuts, player."),
         ("vibes", "Vibe check", "An opted-in viewer's Instagram (Glasser) becomes a crew card and predicted choices.")]
# reads across pipelines are SQL lookups rather than declared dependencies; draw them dashed
CROSS = [("story.stills", "film.plan"), ("story.clips", "film.plan"), ("story.critic", "film.plan"),
         ("story.paths", "vibes.personas")]


def parse(name):
    out = subprocess.run([BRUIN, "internal", "parse-pipeline", str(REPO / "pipelines" / name)], capture_output=True, text=True)
    return json.loads(out.stdout)


def checks(a):
    n = sum(len(c.get("checks") or []) for c in a.get("columns") or [])
    return n + len(a.get("custom_checks") or [])


def node_id(name):
    return name.replace(".", "_")


sections, total_assets, total_checks = [], 0, 0
for key, title, blurb in PIPES:
    p = parse(key)
    assets = sorted(p["assets"], key=lambda a: a["name"])
    total_assets += len(assets)
    n_checks = sum(checks(a) for a in assets)
    total_checks += n_checks
    lines = ["graph LR"]
    for a in assets:
        label = a["name"].split(".", 1)[1]
        lines.append(f'  {node_id(a["name"])}["{label}"]')
        for u in a.get("upstreams") or []:
            if u.get("type") == "asset":
                lines.append(f"  {node_id(u['value'])} --> {node_id(a['name'])}")
    names = {a["name"] for a in assets}
    for src, dst in CROSS:
        if dst in names:
            lines.append(f'  {node_id(src)}(["{src}"]) -.-> {node_id(dst)}')
    rows = "".join(
        f"<tr><td><code>{html.escape(a['name'])}</code></td><td>{html.escape(str(a.get('type')))}</td>"
        f"<td>{checks(a)}</td><td>{html.escape((a.get('description') or '').strip().splitlines()[0] if a.get('description') else '')}</td></tr>"
        for a in assets)
    sections.append(f"""
<section>
  <h2>{html.escape(title)} <small>pipelines/{key} &middot; {len(assets)} assets &middot; {n_checks} checks</small></h2>
  <p>{html.escape(blurb)}</p>
  <div class="graph"><pre class="mermaid">{html.escape(chr(10).join(lines))}</pre></div>
  <div class="tbl"><table><thead><tr><th>Asset</th><th>Type</th><th>Checks</th><th>What it does</th></tr></thead><tbody>{rows}</tbody></table></div>
</section>""")

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>CapyPunk Pipelines</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@800&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>
:root {{ color-scheme: dark; --ink: #07080d; --panel: #10121b; --line: #262a3a; --fg: #e8e6ef; --dim: #8d8fa3; --cyan: #2ee6ff; --yuzu: #f2c94c; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--ink); color: var(--fg); font: 15px/1.55 "IBM Plex Sans", Arial, sans-serif; }}
main {{ max-width: 1180px; margin: 0 auto; padding-block: 28px 60px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); display: grid; gap: 22px; }}
h1 {{ margin: 0; font: 800 44px/1 "Big Shoulders Display", "Arial Narrow", sans-serif; text-transform: uppercase; letter-spacing: .03em; }}
h1 span {{ color: var(--yuzu); }}
h2 {{ margin: 0 0 6px; font: 800 26px/1.1 "Big Shoulders Display", "Arial Narrow", sans-serif; text-transform: uppercase; }}
h2 small {{ font: 500 12px "IBM Plex Mono", monospace; color: var(--dim); letter-spacing: .06em; margin-left: 8px; }}
p {{ margin: 0 0 12px; color: #cfcde0; max-width: 75ch; }}
.lead {{ font: 500 13px "IBM Plex Mono", monospace; color: var(--dim); letter-spacing: .04em; }}
.lead b {{ color: var(--cyan); }}
section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; min-width: 0; }}
.graph {{ overflow-x: auto; background: #0b0d14; border: 1px solid var(--line); border-radius: 6px; padding: 10px; margin-bottom: 12px; }}
.tbl {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ font: 600 11px "IBM Plex Mono", monospace; color: var(--dim); letter-spacing: .08em; text-transform: uppercase; }}
td:nth-child(3) {{ font-variant-numeric: tabular-nums; text-align: right; }}
code {{ font: 500 12.5px "IBM Plex Mono", monospace; color: var(--cyan); }}
</style>
</head>
<body>
<main>
  <h1>Capy<span>Punk</span> pipelines</h1>
  <div class="lead">{len(PIPES)} Bruin pipelines &middot; <b>{total_assets}</b> assets &middot; <b>{total_checks}</b> quality checks &middot; DuckDB warehouse &middot; dashed lines are cross-pipeline reads</div>
  {"".join(sections)}
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js"></script>
<script>
mermaid.initialize({{ startOnLoad: true, theme: "dark", flowchart: {{ useMaxWidth: false, htmlLabels: true }},
  themeVariables: {{ primaryColor: "#10121b", primaryBorderColor: "#2ee6ff", primaryTextColor: "#e8e6ef", lineColor: "#8d8fa3", fontFamily: "IBM Plex Mono, monospace" }} }});
</script>
</body>
</html>
"""
out = REPO / "player" / "dist" / "pipeline.html"
out.write_text(page)
print(f"wrote {out} ({out.stat().st_size // 1024} KB): {total_assets} assets, {total_checks} checks")
