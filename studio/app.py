"""CapyPunk Studio: type a premise, get a playable choose-your-own-adventure skit.

The browser talks only to this server. This server calls HarnessRouter Cloud with HR_API_KEY from its
own environment, maps the feature to its Harness (never taken from the browser), and keeps each
visitor's tasks with their response id and session id so they can be listed and continued.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import posixpath
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from hr import TERMINAL, HarnessRouter, HRError, answer_text

HERE = Path(__file__).resolve().parent
CONF = json.loads((HERE / "harnessrouter.json").read_text())
FEATURES = {"cyoa_story": CONF["harness_id"]}   # feature -> Harness, set on the server only
FEATURE = "cyoa_story"
OUT = "story/"
PREVIEW_TTL = 15 * 60
PREVIEW_SECRET = (os.environ.get("PREVIEW_SIGNING_SECRET") or "").encode() or secrets.token_bytes(32)
PREVIEW_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8", ".json": "application/json",
                 ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}
PREVIEW_CSP = ("sandbox allow-scripts allow-forms; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; "
               "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; "
               "img-src 'self' data: blob:; connect-src 'none'; form-action 'none'; frame-ancestors 'self'")

app = FastAPI(title="CapyPunk Studio")
_hr: HarnessRouter | None = None
_lock = threading.Lock()


def hr() -> HarnessRouter:
    global _hr
    if _hr is None:
        _hr = HarnessRouter.from_env(HERE)
    return _hr


# ------------------------------------------------------------------ storage
def db() -> sqlite3.Connection:
    path = Path(os.environ.get("STUDIO_DB", HERE / "data" / "studio.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, user TEXT NOT NULL, feature TEXT NOT NULL, harness_id TEXT NOT NULL,
        prompt TEXT NOT NULL, status TEXT NOT NULL, response_id TEXT, session_id TEXT,
        title TEXT, summary TEXT, answer TEXT, error TEXT, turns INTEGER DEFAULT 1,
        created REAL NOT NULL, updated REAL NOT NULL, polled REAL DEFAULT 0)""")
    return con


def owned(con, task_id: str, user: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM tasks WHERE id = ? AND user = ?", (task_id, user)).fetchone()
    if row is None:  # the same answer for "missing" and "someone else's"
        raise HTTPException(404, "No such story.")
    return row


# ------------------------------------------------------------------ identity
def visitor(request: Request) -> str:
    uid = request.cookies.get("cp_uid")
    if not uid or len(uid) != 32 or not all(c in "0123456789abcdef" for c in uid):
        raise HTTPException(401, "Open the studio page first.")
    return uid


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    resp = HTMLResponse((HERE / "static" / "index.html").read_text())
    if not request.cookies.get("cp_uid"):
        resp.set_cookie("cp_uid", secrets.token_hex(16), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365)
    return resp


# ------------------------------------------------------------------ tasks
class NewTask(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


def public(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "prompt": row["prompt"], "status": row["status"], "title": row["title"],
            "summary": row["summary"], "turns": row["turns"], "created": row["created"]}


@app.post("/api/tasks")
def create_task(body: NewTask, request: Request) -> dict:
    user = visitor(request)
    task_id, now = uuid.uuid4().hex, time.time()
    harness_id = FEATURES[FEATURE]
    try:
        r = hr().start_task(text=body.prompt.strip(), user=user, harness_id=harness_id,
                            idempotency_key=f"{task_id}-1")
    except HRError as e:
        raise HTTPException(502, "The story writer is unavailable right now. Try again in a minute.") from e
    with db() as con:
        con.execute("INSERT INTO tasks (id, user, feature, harness_id, prompt, status, response_id, session_id, created, updated)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (task_id, user, FEATURE, harness_id, body.prompt.strip(), r.get("status", "in_progress"),
                     r["id"], (r.get("metadata") or {}).get("session_id"), now, now))
    return {"id": task_id, "status": "in_progress"}


@app.get("/api/tasks")
def list_tasks(request: Request) -> dict:
    user = visitor(request)
    with db() as con:
        rows = con.execute("SELECT * FROM tasks WHERE user = ? ORDER BY created DESC LIMIT 50", (user,)).fetchall()
    return {"tasks": [public(r) for r in rows]}


def _refresh(con, row: sqlite3.Row) -> sqlite3.Row:
    """Poll HarnessRouter for a running task (at most every 3 seconds) and record what finished."""
    if row["status"] in TERMINAL or row["status"] == "role_mismatch" or time.time() - (row["polled"] or 0) < 3:
        return row
    with _lock:
        r = hr().get_response(row["response_id"])
    status = r.get("status", "in_progress")
    fields = {"polled": time.time(), "status": status, "updated": time.time(),
              "session_id": (r.get("metadata") or {}).get("session_id") or row["session_id"]}
    if status in TERMINAL:
        text = answer_text(r)
        fields["answer"] = text[:4000]
        if text.lower().startswith("role_mismatch"):
            fields["status"] = "role_mismatch"
        if status == "completed" and fields["status"] != "role_mismatch":
            manifest = _manifest(fields["session_id"])
            fields["title"] = manifest.get("title")
            fields["summary"] = manifest.get("summary") or text[:300]
        if status in ("failed", "incomplete"):
            fields["error"] = (r.get("incomplete_details") or {}).get("reason") or "failed"
    sets = ", ".join(f"{k} = ?" for k in fields)
    con.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*fields.values(), row["id"]))
    return con.execute("SELECT * FROM tasks WHERE id = ?", (row["id"],)).fetchone()


def _outputs(session_id: str) -> dict[str, dict]:
    """The task's deliverables, keyed by their path inside the output folder."""
    return {f["path"][len(OUT):]: f for f in hr().session_files(session_id) if f.get("path", "").startswith(OUT)}


def _manifest(session_id: str) -> dict:
    f = _outputs(session_id).get("manifest.json")
    if not f:
        return {}
    try:
        data, _ = hr().file_bytes(session_id, f["id"])
        return json.loads(data)
    except (HRError, ValueError):
        return {}


def sign_preview(task_id: str, ttl: int = PREVIEW_TTL) -> str:
    exp = int(time.time()) + ttl
    sig = hmac.new(PREVIEW_SECRET, f"{task_id}.{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{task_id}.{exp}.{sig}"


def verify_preview(token: str) -> str | None:
    try:
        task_id, exp, sig = token.split(".")
        want = hmac.new(PREVIEW_SECRET, f"{task_id}.{exp}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, want) and int(exp) >= time.time():
            return task_id
    except ValueError:
        pass
    return None


def safe_path(path: str) -> str | None:
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        return None
    norm = posixpath.normpath(path)
    if norm.startswith("..") or "/../" in f"/{norm}/":
        return None
    return norm


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: str, request: Request) -> dict:
    user = visitor(request)
    with db() as con:
        row = _refresh(con, owned(con, task_id, user))
    out = public(row)
    out["answer"] = row["answer"]
    if row["status"] == "completed" and row["session_id"]:
        files = _outputs(row["session_id"])
        out["files"] = [{"path": p, "bytes": f.get("bytes")} for p, f in sorted(files.items())]
        if "index.html" in files:
            out["preview"] = f"/preview/{sign_preview(task_id)}/index.html"
    if row["status"] in ("failed", "incomplete", "cancelled"):
        out["error"] = "The writer stopped before finishing. Try again, or simplify the premise."
    return out


class FollowUp(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


@app.post("/api/tasks/{task_id}/followup")
def follow_up(task_id: str, body: FollowUp, request: Request) -> dict:
    user = visitor(request)
    with db() as con:
        row = _refresh(con, owned(con, task_id, user))
        if row["status"] not in ("completed", "incomplete"):
            raise HTTPException(409, "Wait for the current version to finish.")
        try:
            r = hr().start_task(text=body.prompt.strip(), user=user, harness_id=row["harness_id"],
                                previous_response_id=row["response_id"], session_id=row["session_id"],
                                idempotency_key=f"{task_id}-{row['turns'] + 1}")
        except HRError as e:
            raise HTTPException(502, "The story writer is unavailable right now. Try again in a minute.") from e
        con.execute("UPDATE tasks SET status = 'in_progress', response_id = ?, turns = turns + 1, polled = 0, "
                    "updated = ? WHERE id = ?", (r["id"], time.time(), task_id))
    return {"id": task_id, "status": "in_progress"}


@app.get("/api/tasks/{task_id}/files/{path:path}")
def download(task_id: str, path: str, request: Request) -> Response:
    user = visitor(request)
    rel = safe_path(path)
    if rel is None:
        raise HTTPException(400, "Bad file path.")
    with db() as con:
        row = owned(con, task_id, user)
    f = _outputs(row["session_id"]).get(rel) if row["session_id"] else None
    if not f:
        raise HTTPException(404, "No such file.")
    data, _ = hr().file_bytes(row["session_id"], f["id"])
    name = posixpath.basename(rel)
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff"})


@app.get("/preview/{token}/{path:path}")
def preview(token: str, path: str) -> Response:
    task_id = verify_preview(token)
    rel = safe_path(path)
    ext = posixpath.splitext(rel or "")[1].lower()
    if task_id is None or rel is None or ext not in PREVIEW_TYPES:
        raise HTTPException(404, "Not found.")
    with db() as con:
        row = con.execute("SELECT session_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    f = _outputs(row["session_id"]).get(rel) if row and row["session_id"] else None
    if not f:
        raise HTTPException(404, "Not found.")
    data, _ = hr().file_bytes(row["session_id"], f["id"])
    return Response(data, media_type=PREVIEW_TYPES[ext], headers={
        "Content-Security-Policy": PREVIEW_CSP, "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer", "Cache-Control": "private, max-age=300"})


@app.on_event("startup")
def recover() -> None:
    """Tasks left in progress by a restart resume through the normal poll on their next detail read."""
    with db() as con:
        con.execute("UPDATE tasks SET polled = 0 WHERE status = 'in_progress'")
