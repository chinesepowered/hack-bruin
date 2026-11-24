"""Even, loud-enough soundtracks for the demo and playthrough videos.

Every section's foreground (a film cut, a voice-over line, or nothing) is set to the same loudness. The score
loops under everything and comes up wherever nothing is being said. The master is peak-limited and set to
-14 LUFS, the level YouTube plays at. Video streams are never re-encoded here.
"""
import json
import math
import re
import subprocess
from pathlib import Path

SR = 48000
TARGET = -14.0  # LUFS: each section's foreground, and the master
CEILING = 0.79  # limiter ceiling, about -2 dBFS, so the AAC file stays under -1 dBTP
FMT = f"aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo"
VOICE = "acompressor=threshold=0.063:ratio=3:attack=10:release=150"  # evens out the presenter's peaks


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *map(str, args)], check=True)


def loudness(src, chain=""):
    """(integrated LUFS, true peak dBTP) of a file's audio, after an optional filter chain."""
    af = f"{chain},loudnorm=print_format=json" if chain else "loudnorm=print_format=json"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-vn", "-af", af, "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    j = json.loads(re.search(r"\{[^{}]*\}\s*$", r.stderr, re.S).group(0))
    return float(j["input_i"]), float(j["input_tp"])


def duration(video):
    """Exact length of a file's video stream, from its frame count."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_frames,r_frame_rate", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = map(int, s["r_frame_rate"].split("/"))
    return int(s["nb_frames"]) * den / num


def join_video(segments, out):
    """Concatenate the segments' video streams only, without re-encoding."""
    parts = []
    for s in map(Path, segments):
        v = s.with_name(s.stem + ".v.mp4")
        ff("-i", s, "-map", "0:v", "-c", "copy", v)
        parts.append(v)
    lst = Path(out).with_suffix(".txt")
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)
    return out


def foreground(sections, out):
    """One PCM track: each section's audio at TARGET loudness, padded or trimmed to the section's length.

    A section is {"dur": seconds, "kind": "film" | "voice" | "silence", "src": file, "delay": seconds}.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for n, sec in enumerate(sections):
        p = out.with_name(f"{out.stem}_{n:02d}.wav")
        dur = sec["dur"]
        if sec["kind"] == "silence":
            ff("-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-t", f"{dur:.4f}", "-c:a", "pcm_f32le", p)
        else:
            chain = FMT + ("," + VOICE if sec["kind"] == "voice" else "")
            lufs, _ = loudness(sec["src"], chain)
            sec["gain_db"] = round(TARGET - lufs, 1)
            ms = int(round(sec.get("delay", 0) * 1000))
            delay = f",adelay={ms}|{ms}" if ms else ""
            ff("-i", sec["src"], "-vn", "-af", f"{chain},volume={TARGET - lufs:.2f}dB{delay},apad,atrim=end={dur:.4f}",
               "-c:a", "pcm_f32le", p)
        parts.append(p)
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)
    return out


def score(src, total, windows, out, bed=0.2, up=0.85, ramp=0.6, fade=3.0, body=(9.0, 55.0), xfade=2.0):
    """The score for `total` seconds: at `up` inside each (start, end) window, at `bed` under everything else.

    The track fades in and out, so only its full-volume `body` is looped, with crossfaded joins.
    """
    w = "0"
    for a, b in windows:
        term = f"clip(min((t-{a - ramp / 2:.3f})/{ramp},({b + ramp / 2:.3f}-t)/{ramp}),0,1)"
        w = term if w == "0" else f"max({w},{term})"
    vol = f"{bed}+{up - bed:.3f}*{w}"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    start, end = body
    length = end - start
    loop = out.with_name(out.stem + "_body.wav")
    ff("-i", src, "-af", f"{FMT},atrim={start}:{end},asetpts=PTS-STARTPTS", "-c:a", "pcm_f32le", loop)
    # overlapping copies with equal-power fades, summed: a seamless crossfaded loop
    n = max(1, math.ceil((total - xfade) / (length - xfade)))
    inputs, chain = [], []
    for i in range(n):
        inputs += ["-i", loop]
        steps = ([f"afade=t=in:d={xfade}:curve=qsin"] if i else []) + \
                ([f"afade=t=out:st={length - xfade}:d={xfade}:curve=qsin"] if i < n - 1 else [])
        ms = int(round(i * (length - xfade) * 1000))
        steps += [f"adelay={ms}|{ms}"] if ms else []
        chain.append(f"[{i}:a]{','.join(steps) or 'anull'}[c{i}]")
    chain.append("".join(f"[c{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest,"
                 f"atrim=end={total:.4f},volume='{vol}':eval=frame,"
                 f"afade=t=in:d=0.4,afade=t=out:st={total - fade:.3f}:d={fade}[m]")
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", "[m]", "-c:a", "pcm_f32le", out)
    return out


def master(video, fg, music, out):
    """Mix the foreground and the score, set the level to TARGET, limit the peaks, and mux with the untouched video."""
    out = Path(out)
    mix = out.parent / "build" / f"{out.stem}_mix.wav"
    mix.parent.mkdir(parents=True, exist_ok=True)
    ff("-i", fg, "-i", music, "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0", "-c:a", "pcm_f32le", mix)
    lufs, _ = loudness(mix)
    ff("-i", video, "-i", mix, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
       "-af", f"volume={TARGET - lufs:.2f}dB,alimiter=limit={CEILING}:attack=5:release=60:level=false:latency=true",
       "-c:a", "aac", "-b:a", "192k", "-ar", SR, "-movflags", "+faststart", out)
    return out


def report(out, sections):
    """Print the loudness of each section of the finished file, and of the whole."""
    t = 0.0
    for sec in sections:
        lufs, _ = loudness(out, f"atrim={t:.3f}:{t + sec['dur']:.3f}")
        print(f"  {sec['name']:<14} {t:6.1f}-{t + sec['dur']:6.1f}s  {lufs:6.1f} LUFS")
        t += sec["dur"]
    lufs, tp = loudness(out)
    print(f"  {'whole video':<14} {0:6.1f}-{t:6.1f}s  {lufs:6.1f} LUFS, true peak {tp:.1f} dBTP")
