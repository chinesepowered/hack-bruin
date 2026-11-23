"""Reuse or create the CapyPunk Studio Harness on HarnessRouter Cloud, then write harnessrouter.json.

Reads HR_API_KEY from the environment (or studio/.env.harnessrouter); never prints it.
"""
import json
from pathlib import Path

from hr import HarnessRouter

HERE = Path(__file__).resolve().parent
NAME = "CapyPunk Studio"
BASE = "hermes"          # the base HarnessRouter recommends for most jobs and for file deliverables
MODEL = "qwen4-max"      # Alibaba Qwen only, by the project owner's choice
INSTRUCTIONS = (HERE / "instructions.md").read_text()

hr = HarnessRouter.from_env(HERE)
disc = hr.discovery()
me = hr.get("/v1/me")
bases = hr.get("/v1/bases")["bases"]
base = next(b for b in bases if b["id"] == BASE)
if not any(m["id"] == MODEL and m.get("available") for m in base.get("models", [])):
    raise SystemExit(f"{MODEL} is not available on {BASE} for this workspace")

existing = [h for h in hr.get("/v1/harnesses")["harnesses"] if h["name"] == NAME]
body = {"name": NAME, "base": BASE, "default_model": MODEL, "system_prompt": INSTRUCTIONS,
        "mcp_servers": [], "skills": [], "max_step": 80, "timeout_seconds": 1200, "max_cost_usd": 2.0}
if disc.get("capabilities", {}).get("memories"):
    body["memory"] = "auto"   # returning writers; only sent when the service provisions memory
if existing:
    harness, status = existing[0], "REUSED"
else:
    harness, status = hr.post("/v1/harnesses", body), "CREATED"

record = {"harness_id": harness["id"], "name": harness["name"], "base": harness["base"],
          "model": harness.get("defaultModel"), "workspace": me.get("workspace_name"),
          "memory": harness.get("memory") or "not provisioned (service reports memories: false)",
          "budgets": {"max_step": 80, "timeout_seconds": 1200, "max_cost_usd": 2.0},
          "uhp_version": hr.version, "instructions": harness.get("systemPrompt") or INSTRUCTIONS}
(HERE / "harnessrouter.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({"status": status, "harness_id": record["harness_id"], "base": record["base"],
                  "model": record["model"], "workspace": record["workspace"]}))
