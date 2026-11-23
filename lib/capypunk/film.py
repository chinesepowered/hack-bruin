"""Production: cast sheets, anchor stills, Wan clips, narration and final cuts.

Every function returns a plain dict that a Bruin Python asset turns into a one-row table, so the
warehouse holds the whole production record: URLs, local files, QA verdicts, retakes and cost.
"""
from __future__ import annotations

import difflib
import json
import re
import time
import uuid
from pathlib import Path

from . import clients, config, media
from .writers import SPEECH

PLAN_RATES = {"480p": 0.068, "720p": 0.14, "1080p": 0.28}  # Wan 3.0 Prime, USD per second
STILL_PRICE = 0.0141


def bible() -> dict:
    return json.loads((config.SERIES / "bible.json").read_text())


def _looks(b: dict, chars: list[str]) -> str:
    return " ".join(f"{b['characters'][c]['name']}: {b['characters'][c]['look']} (reference image {i + 1})."
                    for i, c in enumerate(chars))


# ---------------------------------------------------------------- cast
def register_cast(char_id: str) -> dict:
    """Upload a locked character sheet (series/cast/<id>.jpg) to Runware so stills can reference it."""
    path = config.SERIES / "cast" / f"{char_id}.jpg"
    up = clients.runware_upload(path)
    return {"char_id": char_id, "sheet_path": str(path.relative_to(config.REPO)),
            "ref": up.get("mediaURL") or up.get("mediaUUID"), "media_uuid": up.get("mediaUUID")}


# ---------------------------------------------------------------- stills
STILL_QA_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"on_model": {"type": "boolean"}, "matches_brief": {"type": "boolean"},
                   "artifacts": {"type": "string"}, "score": {"type": "integer"}},
    "required": ["on_model", "matches_brief", "artifacts", "score"],
}


def still_prompt(b: dict, chars: list[str], brief: str, has_parent: bool) -> str:
    parent = (" Match the lighting, colour grade and weather of the final reference image." if has_parent else "")
    return (f"Cinematic 16:9 film still. {brief} {_looks(b, chars)}{parent} {b['style']}. "
            f"{b['negative_style']}, except any billboard or screen text quoted above.")


def qa_still(b: dict, chars: list[str], brief: str, cast_paths: list[str], still_path: str) -> dict:
    content = [{"type": "text", "text": (
        "The first images are character reference sheets (" + ", ".join(b['characters'][c]['name'] for c in chars) +
        "). The last image is a new film still meant to show: " + brief +
        "\nIs every character on-model (same face, hair, outfit, the capybara's yuzu fruit and harness)? Does the "
        "frame match the brief? List artifacts (extra limbs, warped faces or paws, garbled text other than "
        "intended signage). Score 1-10 as a usable film frame.")}]
    content += [clients.image_part(p) for p in cast_paths] + [clients.image_part(still_path)]
    verdict, _ = clients.qwen_chat([{"role": "user", "content": content}], schema=STILL_QA_SCHEMA,
                                   schema_name="still_qa", max_tokens=3000)
    return verdict


def paint_still(still_id: str, brief: str, chars: list[str], cast: dict[str, dict], parent: dict | None,
                max_attempts: int = 3, good_enough: int = 8) -> dict:
    """Qwen-Image with the cast sheets (and parent still) as references, checked by Qwen4-Max; keeps the best take."""
    b = bible()
    refs = [cast[c]["ref"] for c in chars] + ([parent["url"]] if parent else [])
    prompt = still_prompt(b, chars, brief, bool(parent))
    out_dir = config.media_dir("film", "stills")
    best, cost, takes = None, 0.0, []
    for attempt in range(1, max_attempts + 1):
        row = clients.qwen_image(prompt, refs=refs)[0]
        cost += float(row.get("cost") or STILL_PRICE)
        path = clients.download(row["imageURL"], out_dir / f"{still_id}_take{attempt}.png")
        qa = qa_still(b, chars, brief, [str(config.REPO / cast[c]["sheet_path"]) for c in chars], str(path))
        score = int(qa["score"]) - (0 if qa["on_model"] else 3)
        takes.append({"attempt": attempt, "score": score, "qa": qa})
        if best is None or score > best["score"]:
            best = {"url": row["imageURL"], "path": path, "score": score, "qa": qa, "attempt": attempt}
        if score >= good_enough:
            break
    final = out_dir / f"{still_id}.png"
    final.write_bytes(Path(best["path"]).read_bytes())
    return {"still_id": still_id, "url": best["url"], "path": str(final.relative_to(config.REPO)),
            "qa_score": best["score"], "on_model": bool(best["qa"]["on_model"]), "qa_notes": best["qa"]["artifacts"][:500],
            "takes": len(takes), "takes_json": json.dumps(takes), "cost_usd": round(cost, 4)}


# ---------------------------------------------------------------- clips
CLIP_QA_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"on_model": {"type": "boolean"}, "follows_action": {"type": "boolean"},
                   "artifacts": {"type": "string"}, "score": {"type": "integer"}},
    "required": ["on_model", "follows_action", "artifacts", "score"],
}


def clip_prompt(b: dict, action: str, dialogue: list[dict], sfx: str) -> str:
    lines = " ".join(f"{d['speaker'].capitalize()} says in {SPEECH[d['speaker']]}: \"{d['line']}\"" for d in dialogue)
    spoken = f" Spoken on screen with lip sync, clearly audible: {lines}" if dialogue else " Nobody speaks."
    return (f"One continuous cinematic shot, no cuts. {action}{spoken} Sound design: {sfx}. Diegetic sound only, "
            f"no music. Yuzu the capybara never speaks. {b['style']}.")


def _norm_words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower()).split()


def dialogue_match(expected: list[str], transcript: str) -> float:
    exp = _norm_words(" ".join(expected))
    if not exp:
        return 1.0
    got = _norm_words(re.sub(r"\[[^\]]*\]", " ", transcript or ""))
    return round(difflib.SequenceMatcher(None, exp, got).ratio(), 3)


def transcribe(path: str | Path) -> dict:
    """ElevenLabs Scribe speech-to-text with word timings (used to verify lines and time subtitles)."""
    import os
    import requests
    wav = Path(path).with_suffix(".wav")
    media.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    with open(wav, "rb") as f:
        r = requests.post("https://api.elevenlabs.io/v1/speech-to-text", timeout=300,
                          headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "User-Agent": clients.UA},
                          data={"model_id": "scribe_v1", "timestamps_granularity": "word"}, files={"file": f})
    r.raise_for_status()
    return r.json()


def qa_clip(b: dict, chars: list[str], action: str, cast_paths: list[str], frames: list[Path]) -> dict:
    content = [{"type": "text", "text": (
        "The first images are character sheets (" + ", ".join(b['characters'][c]['name'] for c in chars) +
        "). The last three are frames sampled from a generated video clip whose direction was: " + action +
        "\nAre the characters on-model? Does it follow the direction? List visible artifacts. Score 1-10.")}]
    content += [clients.image_part(p) for p in cast_paths] + [clients.image_part(f) for f in frames]
    verdict, _ = clients.qwen_chat([{"role": "user", "content": content}], schema=CLIP_QA_SCHEMA,
                                   schema_name="clip_qa", max_tokens=3000)
    return verdict


def shoot_clip(clip_id: str, action: str, dialogue: list[dict], sfx: str, duration: int, chars: list[str],
               first: dict, last: dict | None, cast: dict[str, dict], resolution: str,
               max_takes: int = 2, min_match: float = 0.6) -> dict:
    """Render with Wan 3.0 Prime between anchor stills, then verify the lines were spoken (Scribe) and the
    frames are on-model (Qwen4-Max). Retakes once with a new seed if the dialogue check fails."""
    b = bible()
    prompt = clip_prompt(b, action, dialogue, sfx)
    out_dir = config.media_dir("film", "clips")
    expected = [d["line"] for d in dialogue]
    takes, cost, best = [], 0.0, None
    for take in range(1, max_takes + 1):
        t0 = time.time()
        tu = clients.wan_submit(prompt, first=first["url"], last=(last or {}).get("url"), duration=duration,
                                resolution=resolution, audio=True, seed=int(uuid.uuid4().int % 2_000_000_000))
        row = clients.runware_wait(tu, timeout=2400, first_delay=60)
        cost += float(row.get("cost") or duration * PLAN_RATES.get(resolution, 0.28))
        path = clients.download(row["videoURL"], out_dir / f"{clip_id}_take{take}.mp4")
        stt = transcribe(path)
        match = dialogue_match(expected, stt.get("text", ""))
        frames = media.sample_frames(path, out_dir / f"{clip_id}_take{take}_frames", n=3)
        qa = qa_clip(b, chars, action, [str(config.REPO / cast[c]["sheet_path"]) for c in chars], frames)
        rec = {"take": take, "url": row["videoURL"], "path": str(path), "render_s": round(time.time() - t0),
               "transcript": stt.get("text", ""), "words": stt.get("words", []), "match": match, "qa": qa}
        takes.append(rec)
        rank = (match >= min_match, qa["on_model"], qa["score"], match)
        if best is None or rank > best[0]:
            best = (rank, rec)
        if match >= min_match and qa["on_model"]:
            break
    rec = best[1]
    final = out_dir / f"{clip_id}.mp4"
    final.write_bytes(Path(rec["path"]).read_bytes())
    (out_dir / f"{clip_id}.words.json").write_text(json.dumps(rec["words"]))
    return {"clip_id": clip_id, "url": rec["url"], "path": str(final.relative_to(config.REPO)),
            "duration_s": round(media.duration(final), 2), "planned_s": duration, "resolution": resolution,
            "has_audio": media.has_audio(final), "transcript": rec["transcript"][:1000],
            "dialogue_match": rec["match"], "has_dialogue": bool(expected),
            "qa_score": int(rec["qa"]["score"]), "on_model": bool(rec["qa"]["on_model"]),
            "qa_notes": rec["qa"]["artifacts"][:500], "takes": len(takes), "render_s": rec["render_s"],
            "cost_usd": round(cost, 4)}


# ---------------------------------------------------------------- narration
def record_line(line_id: str, text: str, voice_id: str) -> dict:
    out = config.media_dir("film", "voice") / f"{line_id}.mp3"
    clients.eleven_tts(text, voice_id, out, model_id="eleven_v3")
    return {"line_id": line_id, "path": str(out.relative_to(config.REPO)), "duration_s": round(media.duration(out), 2),
            "chars": len(text)}


# ---------------------------------------------------------------- final cut
def _align(line: str, words: list[dict]) -> tuple[float, float] | None:
    """Find where a scripted line was spoken using Scribe word timings."""
    toks = [w for w in words if w.get("type", "word") == "word"]
    target = _norm_words(line)
    if not toks or not target:
        return None
    norm = [(_norm_words(w["text"]) or [""])[0] for w in toks]
    best, best_i, n = 0.0, None, len(target)
    for i in range(len(norm)):
        for span in (n - 1, n, n + 1):
            if span <= 0 or i + span > len(norm):
                continue
            r = difflib.SequenceMatcher(None, target, norm[i:i + span]).ratio()
            if r > best:
                best, best_i, best_span = r, i, span
    if best_i is None or best < 0.5:
        return None
    return float(toks[best_i]["start"]), float(toks[best_i + best_span - 1]["end"])


def _vtt_time(t: float) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def _free_gaps(speech: list[tuple[float, float]], dur: float, pad: float = 0.15) -> list[tuple[float, float]]:
    gaps, t = [], 0.0
    for a, z in sorted(speech):
        if a - pad > t:
            gaps.append((t, a - pad))
        t = max(t, z + pad)
    if dur > t:
        gaps.append((t, dur))
    return gaps


def _hold(src: Path, at: str, seconds: float, out: Path) -> Path:
    """A still hold of the clip's first or last frame with a slow push-in and room tone, same size and fps."""
    w, h = media.video_size(src)
    fps = 30
    frame = out.with_suffix(".png")
    (media.frame_at(src, 0.0, frame) if at == "head" else media.last_frame(src, frame))
    n = int(seconds * fps)
    media.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", f"{seconds:.2f}", "-i", str(frame),
               "-f", "lavfi", "-t", f"{seconds:.2f}", "-i", "anullsrc=r=48000:cl=stereo",
               "-filter_complex", f"[0:v]scale={w * 2}:{h * 2},zoompan=z='min(1+0.0005*on,1.04)':d={n}:s={w}x{h}:fps={fps},format=yuv420p[v]",
               "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(out)])
    return out


def _concat(parts: list[Path], out: Path) -> Path:
    inputs = []
    for p in parts:
        inputs += ["-i", str(p)]
    n = len(parts)
    w, h = media.video_size(parts[0])
    norm = ";".join(f"[{i}:v]scale={w}:{h},fps=30,format=yuv420p,setsar=1[v{i}];[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]"
                    for i in range(n))
    chain = "".join(f"[v{i}][a{i}]" for i in range(n))
    media.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", f"{norm};{chain}concat=n={n}:v=1:a=1[v][a]",
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", str(out)])
    return out


def cut_clip(clip_id: str, clip_path: str, words: list[dict], dialogue: list[dict],
             narration: list[dict], voice_rows: dict[str, dict]) -> dict:
    """Mix narration over the clip without ever talking over the actors, encode for the web, and write
    subtitles timed from Scribe. Narration goes in the free gap nearest its scripted time; if no gap is long
    enough, the shot holds on its first (opening line) or last (closing line) frame while the narrator speaks."""
    b = bible()
    src = config.REPO / clip_path
    out_dir = config.media_dir("film", "cuts")
    dur = media.duration(src)
    speech = [(float(w["start"]), float(w["end"])) for w in words if w.get("type", "word") == "word"]
    head = tail = 0.0
    placed = []  # (voice_path, start_in_clip_or_None, vdur, text, where)
    for i, n in enumerate(narration, start=1):
        v = voice_rows[f"{clip_id}-narration-{i}"]
        want, vdur = float(n.get("start_s") or 0), float(v["duration_s"])
        fits = [(a, z) for a, z in _free_gaps(speech, dur) if z - a >= vdur + 0.2]
        if fits:
            a, z = min(fits, key=lambda g: abs(min(max(want, g[0] + 0.1), g[1] - vdur - 0.1) - want))
            start = min(max(want, a + 0.1), z - vdur - 0.1)
            placed.append((v["path"], start, vdur, n["text"], "clip"))
        elif want < dur / 2:
            head = max(head, vdur + 0.6)
            placed.append((v["path"], 0.3, vdur, n["text"], "head"))
        else:
            placed.append((v["path"], None, vdur, n["text"], "tail"))
            tail = max(tail, vdur + 0.6)
    parts = []
    if head:
        parts.append(_hold(src, "head", head, out_dir / f"{clip_id}_head.mp4"))
    parts.append(src)
    if tail:
        parts.append(_hold(src, "tail", tail, out_dir / f"{clip_id}_tail.mp4"))
    base = _concat(parts, out_dir / f"{clip_id}_held.mp4") if len(parts) > 1 else src
    tracks, cues = [], []
    for path, start, vdur, text, where in placed:
        t = {"clip": head + (start or 0), "head": start, "tail": head + dur + 0.3}[where]
        tracks.append((config.REPO / path, t))
        cues.append((t, t + vdur, f"<i>{text}</i>"))
    t_prev = 0.3
    for d in dialogue:
        span = _align(d["line"], words)
        if span is None:
            span = (t_prev, min(dur, t_prev + max(1.5, len(d["line"].split()) * 0.38)))
        t_prev = span[1] + 0.2
        cues.append((head + span[0], head + span[1] + 0.35,
                     f"<b>{b['characters'][d['speaker']]['name'].upper()}</b> {d['line']}"))
    mixed = out_dir / f"{clip_id}_mix.mp4"
    if tracks:
        media.mix_voice(base, tracks, mixed, bed_gain=0.6, voice_gain=1.6)
    else:
        mixed.write_bytes(Path(base).read_bytes())
    final = out_dir / f"{clip_id}.mp4"
    media.web_encode(mixed, final, crf=21)
    vtt = out_dir / f"{clip_id}.vtt"
    vtt.write_text("WEBVTT\n\n" + "\n".join(f"{_vtt_time(a)} --> {_vtt_time(z)}\n{t}\n" for a, z, t in sorted(cues)))
    return {"clip_id": clip_id, "path": str(final.relative_to(config.REPO)), "vtt_path": str(vtt.relative_to(config.REPO)),
            "duration_s": round(media.duration(final), 2), "size_mb": round(final.stat().st_size / 1e6, 2),
            "narration_lines": len(tracks), "subtitle_cues": len(cues)}


# ---------------------------------------------------------------- score
SCORE_PROMPT = ("Instrumental neo-noir cyberpunk film score. Slow 80 BPM, deep analog synth bass pulse, rain-soaked "
                "reverb pads, a lonely detuned synth lead, ticking hi-hats like a surveillance clock, rising tension in "
                "the last 15 seconds that ends on an unresolved hit. No vocals. Moody, sleek, a little playful.")


def compose_score(seconds: int = 60) -> dict:
    """ElevenLabs Music: one continuous cue so cuts between independently rendered shots feel like one film."""
    import os
    import requests
    out = config.media_dir("film", "music") / "score.mp3"
    if not out.exists():
        r = requests.post("https://api.elevenlabs.io/v1/music", params={"output_format": "mp3_44100_128"}, timeout=600,
                          headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "User-Agent": clients.UA},
                          json={"prompt": SCORE_PROMPT, "music_length_ms": seconds * 1000})
        r.raise_for_status()
        out.write_bytes(r.content)
    return {"path": str(out.relative_to(config.REPO)), "duration_s": round(media.duration(out), 2), "prompt": SCORE_PROMPT}
