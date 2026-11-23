"""ffmpeg/ffprobe helpers: frame grabs, durations, audio mixing, encoding."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {p.stderr[-1500:]}")
    return p.stdout


def probe(path: str | Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(out)


def duration(path: str | Path) -> float:
    return float(probe(path)["format"]["duration"])


def video_size(path: str | Path) -> tuple[int, int]:
    for s in probe(path)["streams"]:
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise RuntimeError("no video stream")


def has_audio(path: str | Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path)["streams"])


def frame_at(video: str | Path, t: float, out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1",
         "-q:v", "2", str(out)])
    return out


def last_frame(video: str | Path, out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.05", "-i", str(video), "-update", "1",
         "-frames:v", "1", "-q:v", "2", str(out)])
    return out


def sample_frames(video: str | Path, out_dir: str | Path, n: int = 3) -> list[Path]:
    d = duration(video)
    out_dir = Path(out_dir)
    return [frame_at(video, d * (i + 0.5) / n, out_dir / f"f{i}.jpg") for i in range(n)]


def mix_voice(video: str | Path, voice_tracks: list[tuple[str | Path, float]], out: str | Path,
              bed_gain: float = 0.55, voice_gain: float = 1.0) -> Path:
    """Overlay voice clips (path, start_seconds) on the clip's own audio, ducking the bed slightly."""
    out = Path(out)
    inputs = ["-i", str(video)]
    filters = []
    labels = []
    base = "[0:a]" if has_audio(video) else None
    for i, (vp, start) in enumerate(voice_tracks, start=1):
        inputs += ["-i", str(vp)]
        ms = int(start * 1000)
        filters.append(f"[{i}:a]adelay={ms}|{ms},volume={voice_gain}[v{i}]")
        labels.append(f"[v{i}]")
    if base:
        filters.append(f"{base}volume={bed_gain}[bed]")
        labels = ["[bed]"] + labels
    if not labels:
        raise ValueError("nothing to mix")
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0[aout]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
         "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)])
    return out


def web_encode(src: str | Path, out: str | Path, crf: int = 21, max_w: int = 1920) -> Path:
    """H.264 + AAC, faststart, for the browser player."""
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", f"scale='min({max_w},iw)':-2",
         "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    return Path(out)
