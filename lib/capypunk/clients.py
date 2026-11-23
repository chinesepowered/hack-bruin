"""Thin HTTP clients for the services CapyPunk uses.

Keys come only from the environment:
  RUNWARE_API_KEY, TELEM_API_KEY, GLASSER_API_KEY, ELEVENLABS_API_KEY
Nothing here prints or logs a key.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from . import config

UA = "capypunk/0.1 (hackathon project; python-requests)"
_session = requests.Session()
_session.headers.update({"User-Agent": UA})


class ApiError(RuntimeError):
    pass


def _key(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise ApiError(f"{name} is not set")
    return v


def _request(method: str, url: str, *, headers: dict | None = None, json_body: Any = None,
             params: dict | None = None, timeout: float = 180, retries: int = 4,
             raw: bool = False):
    delay = 2.0
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.request(method, url, headers=headers, json=json_body, params=params, timeout=timeout)
        except requests.RequestException as e:  # network hiccup
            last = e
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            wait = float(r.headers.get("Retry-After") or delay)
            time.sleep(min(wait, 60))
            delay *= 2
            last = ApiError(f"{r.status_code} {r.text[:300]}")
            continue
        if r.status_code >= 400:
            raise ApiError(f"{method} {url} -> {r.status_code}: {r.text[:600]}")
        return r if raw else (r.json() if r.content else None)
    raise ApiError(f"{method} {url} failed after retries: {last}")


# ---------------------------------------------------------------- Runware
RUNWARE_URL = "https://api.runware.ai/v1"


def runware(tasks: list[dict], timeout: float = 180) -> list[dict]:
    """Send native Runware tasks; return the `data` list (raises on `errors`)."""
    out = _request("POST", RUNWARE_URL, headers={"Authorization": f"Bearer {_key('RUNWARE_API_KEY')}"},
                   json_body=tasks, timeout=timeout)
    if not isinstance(out, dict):
        raise ApiError(f"unexpected Runware response: {str(out)[:300]}")
    if out.get("errors"):
        raise ApiError(f"Runware errors: {json.dumps(out['errors'])[:800]}")
    return out.get("data", [])


def data_uri(path: str | Path) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def runware_upload(path: str | Path) -> dict:
    """Upload a local file to Runware media storage -> {mediaUUID, mediaURL}."""
    data = runware([{"taskType": "mediaStorage", "taskUUID": str(uuid.uuid4()),
                     "operation": "upload", "media": data_uri(path)}], timeout=300)
    return data[0]


def runware_balance() -> float:
    d = runware([{"taskType": "accountManagement", "taskUUID": str(uuid.uuid4()), "operation": "getDetails"}])
    return float(d[0].get("balance", 0))


def qwen_image(prompt: str, *, width: int = config.STILL_W, height: int = config.STILL_H,
               refs: list[str] | None = None, n: int = 1, seed: int | None = None,
               fmt: str = "PNG") -> list[dict]:
    """Text- or reference-to-image with Qwen-Image 2.1 Turbo. Returns result rows (imageURL, cost, seed)."""
    task: dict[str, Any] = {
        "taskType": "imageInference", "taskUUID": str(uuid.uuid4()), "model": config.IMAGE_MODEL,
        "positivePrompt": prompt, "width": width, "height": height, "numberResults": n,
        "outputFormat": fmt, "includeCost": True,
    }
    if refs:
        task["inputs"] = {"referenceImages": refs}
    if seed is not None:
        task["seed"] = seed
    return runware([task], timeout=300)


def wan_submit(prompt: str, *, first: str | None = None, last: str | None = None,
               refs: list[str] | None = None, ref_audios: list[str] | None = None,
               duration: int | str = 8, resolution: str = config.VIDEO_RESOLUTION,
               audio: bool = True, seed: int | None = None, prompt_extend: bool = False,
               task_uuid: str | None = None) -> str:
    """Queue a Wan 3.0 Prime video. Returns the taskUUID to poll."""
    tu = task_uuid or str(uuid.uuid4())
    inputs: dict[str, Any] = {}
    frames = []
    if first:
        frames.append({"image": first, "frame": "first"})
    if last:
        frames.append({"image": last, "frame": "last"})
    if frames:
        inputs["frameImages"] = frames
    if refs:
        inputs["referenceImages"] = refs
    if ref_audios:
        inputs["referenceAudios"] = ref_audios
    task: dict[str, Any] = {
        "taskType": "videoInference", "taskUUID": tu, "model": config.VIDEO_MODEL,
        "positivePrompt": prompt, "duration": duration, "resolution": resolution,
        "deliveryMethod": "async", "includeCost": True,
        "settings": {"audio": audio, "promptExtend": prompt_extend},
    }
    if inputs:
        task["inputs"] = inputs
    if seed is not None:
        task["seed"] = seed
    runware([task], timeout=120)
    return tu


def runware_poll(task_uuid: str) -> dict | None:
    """Return the finished result row, None while processing; raise on error."""
    data = runware([{"taskType": "getResponse", "taskUUID": task_uuid}], timeout=60)
    for row in data:
        st = row.get("status")
        if st == "error":
            raise ApiError(f"task {task_uuid} failed: {json.dumps(row)[:600]}")
        if row.get("videoURL") or row.get("imageURL") or st == "success":
            return row
    return None


def runware_wait(task_uuid: str, timeout: float = 1800, first_delay: float = 30) -> dict:
    time.sleep(first_delay)
    t0, delay = time.time(), 5.0
    while time.time() - t0 < timeout:
        row = runware_poll(task_uuid)
        if row:
            return row
        time.sleep(delay)
        delay = min(delay * 1.4, 30)
    raise ApiError(f"task {task_uuid} timed out after {timeout}s")


# ---------------------------------------------------------------- Qwen4-Max (OpenAI-compatible)
def _parse_json(text: str) -> Any:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    return json.loads(t)


def qwen_chat(messages: list[dict], *, schema: dict | None = None, schema_name: str = "result",
              max_tokens: int = 4096, temperature: float | None = None, attempts: int = 3) -> Any:
    """Chat with Qwen4-Max. Reasoning tokens count against max_tokens, so an empty or truncated
    answer is retried with a bigger budget."""
    usage: dict = {}
    last_err = None
    for attempt in range(attempts):
        body: dict[str, Any] = {"model": config.LLM_MODEL, "messages": messages,
                                "max_tokens": max_tokens * (2 ** attempt)}
        if temperature is not None:
            body["temperature"] = temperature
        if schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
        out = _request("POST", f"{RUNWARE_URL}/chat/completions",
                       headers={"Authorization": f"Bearer {_key('RUNWARE_API_KEY')}"},
                       json_body=body, timeout=900)
        choice = out["choices"][0]
        text = (choice.get("message") or {}).get("content") or ""
        u = out.get("usage") or {}
        usage = {k: usage.get(k, 0) + (u.get(k) or 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        if schema is None:
            if text.strip():
                return text, usage
            last_err = f"empty answer (finish_reason={choice.get('finish_reason')})"
            continue
        try:
            return _parse_json(text), usage
        except (ValueError, json.JSONDecodeError) as e:
            last_err = f"{e} (finish_reason={choice.get('finish_reason')}, chars={len(text)})"
    raise ApiError(f"Qwen4-Max gave no usable answer after {attempts} attempts: {last_err}")


def image_part(src: str | Path) -> dict:
    """OpenAI-style image content part from a URL or a local file."""
    s = str(src)
    url = s if s.startswith(("http://", "https://", "data:")) else data_uri(s)
    return {"type": "image_url", "image_url": {"url": url}}


# ---------------------------------------------------------------- Telem
TELEM_URL = "https://router.telem.ai/v1"


def telem_search(query: str, *, providers: list[str] | None = None, num_results: int = 5,
                 tier: str = "default", published_after: str | None = None,
                 auto_routing: bool = False) -> list[dict]:
    search: dict[str, Any] = {"tier": tier, "num_results": num_results}
    if providers:
        search["providers"] = {"include": providers}
    if auto_routing:
        search["auto_routing"] = "accuracy"
    if published_after:
        search["published_after"] = published_after
    out = _request("POST", f"{TELEM_URL}/search", headers={"Authorization": f"Bearer {_key('TELEM_API_KEY')}"},
                   json_body={"user_input": {"query": query}, "search": search}, timeout=120)
    rows = []
    for run in out.get("preprocessor_runs") or []:
        payload = run.get("output_payload") or {}
        for r in payload.get("results") or []:
            rows.append({"provider": run.get("preprocessor_name"), **r})
    return rows


def telem_fetch(urls: list[str], tier: str = "default") -> list[dict]:
    out = _request("POST", f"{TELEM_URL}/fetch", headers={"Authorization": f"Bearer {_key('TELEM_API_KEY')}"},
                   json_body={"urls": urls[:5], "options": {"tier": tier}}, timeout=180)
    docs = []
    for run in out.get("preprocessor_runs") or []:
        docs.extend((run.get("output_payload") or {}).get("fetched_results") or [])
    return docs


def telem(method: str, path: str, body: Any = None, params: dict | None = None) -> Any:
    return _request(method, f"{TELEM_URL}{path}", headers={"Authorization": f"Bearer {_key('TELEM_API_KEY')}"},
                    json_body=body, params=params, timeout=120)


# ---------------------------------------------------------------- Glasser
GLASSER_URL = "https://api.glasser.ai"


def glasser(method: str, path: str, body: Any = None, *, idempotency_key: str | None = None,
            params: dict | None = None) -> Any:
    h = {"Authorization": f"Bearer {_key('GLASSER_API_KEY')}"}
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
    return _request(method, f"{GLASSER_URL}{path}", headers=h, json_body=body, params=params,
                    timeout=180, retries=1 if method == "POST" else 3)


def glasser_run(provider: str, endpoint: str, inp: dict, *, task_id: str | None = None,
                idempotency_key: str | None = None, metadata: dict | None = None) -> dict:
    body: dict[str, Any] = {"provider": provider, "endpoint": endpoint, "input": inp}
    if task_id:
        body["task_id"] = task_id
    if metadata:
        body["metadata"] = {k: str(v) for k, v in metadata.items()}
    run = glasser("POST", "/v1/runs", body, idempotency_key=idempotency_key or str(uuid.uuid4()))
    # async runs come back 202 / RUNNING: poll until terminal
    t0 = time.time()
    while run.get("status") in ("QUEUED", "RUNNING") and time.time() - t0 < 300:
        time.sleep(3)
        run = glasser("GET", f"/v1/runs/{run['id']}")
    return run


# ---------------------------------------------------------------- ElevenLabs
ELEVEN_URL = "https://api.elevenlabs.io/v1"


def eleven_tts(text: str, voice_id: str, out_path: str | Path, *, model_id: str = "eleven_v3",
               stability: float | None = None, style: float | None = None) -> Path:
    body: dict[str, Any] = {"text": text, "model_id": model_id}
    vs = {}
    if stability is not None:
        vs["stability"] = stability
    if style is not None:
        vs["style"] = style
    if vs:
        body["voice_settings"] = vs
    r = _request("POST", f"{ELEVEN_URL}/text-to-speech/{voice_id}",
                 headers={"xi-api-key": _key("ELEVENLABS_API_KEY"), "Accept": "audio/mpeg"},
                 params={"output_format": "mp3_44100_128"}, json_body=body, timeout=180, raw=True)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(r.content)
    return p


def download(url: str, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    r = _request("GET", url, timeout=300, raw=True)
    p.write_bytes(r.content)
    return p
