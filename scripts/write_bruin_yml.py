"""Write the gitignored .bruin.yml from environment variables (keys never enter git)."""
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ["RUNWARE_API_KEY", "TELEM_API_KEY", "GLASSER_API_KEY", "ELEVENLABS_API_KEY"]

missing = [k for k in KEYS if not os.environ.get(k)]
if missing:
    raise SystemExit(f"set these env vars first: {', '.join(missing)}")

lines = [
    "default_environment: default",
    "environments:",
    "  default:",
    "    connections:",
    "      duckdb:",
    "        - name: duckdb-default",
    "          path: capypunk.duckdb",
    "      runware:",
    "        - name: runware-default",
    f"          api_key: {json.dumps(os.environ['RUNWARE_API_KEY'])}",
    "      generic:",
]
for k in KEYS:
    lines += [f"        - name: {k}", f"          value: {json.dumps(os.environ[k])}"]
p = REPO / ".bruin.yml"
p.write_text("\n".join(lines) + "\n")
p.chmod(0o600)
print(f"wrote {p} with {len(KEYS)} generic connections")
