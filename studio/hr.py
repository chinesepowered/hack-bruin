"""A small server-side HarnessRouter Cloud client (UHP 2026-09-28).

The key comes only from HR_API_KEY in the environment or the gitignored studio/.env.harnessrouter;
it is sent only to https://api.harnessrouter.ai and never logged, returned or sent to a browser.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

API = "https://api.harnessrouter.ai"
VERSION = "2026-09-28"
TERMINAL = {"completed", "incomplete", "failed", "cancelled"}


class HRError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code = status, code


def _load_key(project: Path) -> str:
    key = os.environ.get("HR_API_KEY")
    if key:
        return key
    f = project / ".env.harnessrouter"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith("HR_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("HR_API_KEY is not configured on the server")


class HarnessRouter:
    def __init__(self, key: str, version: str = VERSION):
        self.version = version
        self._s = requests.Session()
        self._s.headers.update({"Authorization": f"Bearer {key}", "UHP-Version": version,
                                "User-Agent": "capypunk-studio/0.1"})

    @classmethod
    def from_env(cls, project: Path) -> "HarnessRouter":
        return cls(_load_key(project))

    def _req(self, method: str, path: str, *, json_body=None, headers=None, retry: bool = False, raw: bool = False):
        delay = 1.5
        for attempt in range(4 if retry else 1):
            try:
                r = self._s.request(method, API + path, json=json_body, headers=headers or {}, timeout=60)
            except requests.RequestException:
                if retry and attempt < 3:
                    time.sleep(delay); delay *= 2
                    continue
                raise
            if r.status_code in (429, 502, 503, 504) and retry and attempt < 3:
                time.sleep(float(r.headers.get("Retry-After") or delay)); delay *= 2
                continue
            if r.status_code >= 400:
                try:
                    err = r.json().get("error") or {}
                except ValueError:
                    err = {}
                raise HRError(r.status_code, err.get("code") or "http_error", err.get("message") or r.reason)
            return r if raw else r.json()
        raise HRError(503, "unavailable", "HarnessRouter did not answer")

    # ------------------------------------------------------------- catalog and harnesses
    def discovery(self) -> dict:
        return requests.get(API + "/v1/uhp", timeout=30, headers={"User-Agent": "capypunk-studio/0.1"}).json()

    def get(self, path: str) -> dict:
        return self._req("GET", path, retry=True)

    def post(self, path: str, body: dict) -> dict:
        return self._req("POST", path, json_body=body)

    # ------------------------------------------------------------- tasks
    def start_task(self, *, text: str, user: str, harness_id: str, idempotency_key: str | None = None,
                   previous_response_id: str | None = None, session_id: str | None = None) -> dict:
        """Start (or continue) one task in background mode; returns the in-progress response object."""
        body: dict = {"input": text, "user": user, "metadata": {"harness_id": harness_id}, "background": True}
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
            if session_id:
                body["metadata"]["session_id"] = session_id
        return self._req("POST", "/v1/responses", json_body=body, retry=True,
                         headers={"Idempotency-Key": idempotency_key or str(uuid.uuid4())})

    def get_response(self, response_id: str) -> dict:
        return self._req("GET", f"/v1/responses/{response_id}", retry=True)

    def session_files(self, session_id: str) -> list[dict]:
        return self._req("GET", f"/v1/sessions/{session_id}/files", retry=True).get("files", [])

    def file_bytes(self, session_id: str, file_id: str) -> tuple[bytes, str]:
        url = f"{API}/v1/containers/{session_id}/files/{file_id}/content"
        assert urlparse(url).netloc == "api.harnessrouter.ai"
        r = self._req("GET", f"/v1/containers/{session_id}/files/{file_id}/content", retry=True, raw=True)
        return r.content, r.headers.get("Content-Type", "application/octet-stream")


def answer_text(response: dict) -> str:
    """The answer is the output_text of the LAST message item."""
    msgs = [o for o in response.get("output") or [] if o.get("type") == "message"]
    if not msgs:
        return ""
    return "".join(c.get("text", "") for c in msgs[-1].get("content") or [] if c.get("type") == "output_text").strip()
