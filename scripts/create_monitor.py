"""Create (or reuse) the Telem monitor whose findings seed Episode 2. Writes series/monitor.json (no secrets)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from capypunk import clients, config  # noqa: E402

QUERY = "New laws, lawsuits or product launches involving AI emotion recognition or biometric surveillance"
out = config.SERIES / "monitor.json"

existing = clients.telem("GET", "/monitors") or {}
items = existing.get("data") or existing.get("monitors") or existing.get("items") or []
mon = next((m for m in items if m.get("query") == QUERY and m.get("status") not in ("ended", "deleted")), None)
if mon:
    print("reusing monitor", mon["id"])
else:
    mon = clients.telem("POST", "/monitors", {"query": QUERY, "options": {"frequency": "1d"}, "ttl": "7d", "agent": True})
    print("created monitor", mon.get("id"), "| agent note:", mon.get("agent_note"))
out.write_text(json.dumps({"monitor_id": mon["id"], "query": QUERY, "frequency": "1d", "ttl": "7d",
                           "purpose": "Findings seed the next episode's Lumina announcement."}, indent=2) + "\n")
print(json.dumps({k: mon.get(k) for k in ("id", "status", "frequency", "expires_at", "agent_state")}, default=str)[:500])
