"""Apply a change to the CapyPunk Studio Harness safely: fetch live, reconcile, full PUT with If-Match, re-read.

Edit harnessrouter.json (name, model, instructions) or instructions.md, then run:
    python3 update_harness.py            # shows what would change
    python3 update_harness.py --apply    # applies it
If the live Harness was edited in the HarnessRouter console since harnessrouter.json was written, the
live record wins: the file is refreshed from it first and nothing else is applied in that run.
"""
import json
import sys
from pathlib import Path

from hr import HarnessRouter

HERE = Path(__file__).resolve().parent
FILE = HERE / "harnessrouter.json"
apply = "--apply" in sys.argv

rec = json.loads(FILE.read_text())
wanted = {"name": rec["name"], "model": rec["model"], "instructions": (HERE / "instructions.md").read_text()}
hr = HarnessRouter.from_env(HERE)
resp = hr._req("GET", f"/v1/harnesses/{rec['harness_id']}", raw=True)
live, etag = resp.json(), resp.headers.get("ETag")
live_view = {"name": live["name"], "model": live.get("defaultModel"), "instructions": live.get("systemPrompt") or ""}
on_file = {"name": rec["name"], "model": rec["model"], "instructions": rec["instructions"]}

if live_view != on_file:
    changed = [k for k in live_view if live_view[k] != on_file[k]]
    rec.update({"name": live_view["name"], "model": live_view["model"], "instructions": live_view["instructions"]})
    FILE.write_text(json.dumps(rec, indent=2) + "\n")
    (HERE / "instructions.md").write_text(live_view["instructions"])
    print(json.dumps({"status": "LIVE_CHANGED", "fields": changed, "next": "harnessrouter.json now matches the live Harness; re-apply your change"}))
    sys.exit(0)

diff = [k for k in wanted if wanted[k] != on_file[k]]
if not diff:
    print(json.dumps({"status": "UNCHANGED"}))
    sys.exit(0)
if not apply:
    print(json.dumps({"status": "PENDING", "fields": diff, "next": "run with --apply"}))
    sys.exit(0)

body = {"name": wanted["name"], "base": live["base"], "default_model": wanted["model"], "system_prompt": wanted["instructions"],
        "mcp_servers": live.get("mcpServers") or [], "skills": live.get("skills") or [], "plugins": live.get("plugins") or [],
        "additional_headers": live.get("additionalHeaders") or [], "env": live.get("env") or {},
        "max_step": live.get("maxStep"), "timeout_seconds": live.get("timeoutSeconds"), "max_cost_usd": live.get("maxCostUsd"),
        "reasoning_effort": live.get("reasoningEffort") or None, "environment": live.get("environment") or "",
        "disabled_tools": live.get("disabledTools") or []}
body = {k: v for k, v in body.items() if v is not None}
hr._req("PUT", f"/v1/harnesses/{rec['harness_id']}", json_body=body, headers={"If-Match": etag})
after = hr.get(f"/v1/harnesses/{rec['harness_id']}")
ok = after["name"] == wanted["name"] and after.get("defaultModel") == wanted["model"] and after.get("systemPrompt") == wanted["instructions"]
rec.update({"name": after["name"], "model": after.get("defaultModel"), "instructions": after.get("systemPrompt")})
FILE.write_text(json.dumps(rec, indent=2) + "\n")
print(json.dumps({"status": "UPDATED" if ok else "READBACK_MISMATCH", "fields": diff}))
