"""Cut a straight playthrough of Episode 1, as a viewer sees it in the player, with nothing added.

The title screen, every shot on the path Sporkwhale's vibe predicts (with the player's HUD and subtitles),
both decisions with their countdown and the pick, and the cliffhanger card. The overlays are drawn by the
built player itself (site/, via scripts/playthrough_frames.cjs), so they match it exactly. The sound gets the
same treatment as the demo (scripts/soundtrack.py). Output: demo/capypunk_playthrough.mp4
"""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import soundtrack  # scripts/soundtrack.py

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from capypunk import config  # noqa: E402

REPO = config.REPO
BUILD = REPO / "demo" / "build" / "playthrough"
FRAMES = BUILD / "frames"
SEG = BUILD / "segments"
CUTS = config.MEDIA / "film" / "cuts"
W, H, FPS = 1920, 1080, 30
COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"  # the player's object-fit: cover
VIDEO = ["-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
ff = soundtrack.ff


def draw_overlays():
    """Serve the built site locally and let the player draw its own overlays."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                               "--directory", str(REPO / "site")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        subprocess.run(["node", str(REPO / "scripts" / "playthrough_frames.cjs"), f"http://127.0.0.1:{port}",
                        str(FRAMES), str(FPS)], check=True)
    finally:
        server.terminate()
    return json.loads((FRAMES / "plan.json").read_text())


def title_segment(t, out):
    """The title screen, fading up from black; "Play episode" is pressed at the end."""
    hold = t["seconds"] - t["press_seconds"]
    ff("-loop", 1, "-framerate", FPS, "-t", f"{hold:.3f}", "-i", FRAMES / t["frame"],
       "-loop", 1, "-framerate", FPS, "-t", f"{t['press_seconds']:.3f}", "-i", FRAMES / t["press"],
       "-filter_complex", f"[0:v]{COVER}[a];[1:v]{COVER}[b];[a][b]concat=n=2:v=1:a=0,fade=t=in:d=0.5[v]",
       "-map", "[v]", *VIDEO, out)


def film_segment(cid, plan, out):
    """A shot as the player shows it: cover-fit, with the HUD (REC dot blinking) and the subtitles on top."""
    hud, cues = plan["hud"][cid], plan["cues"][cid]
    inputs = ["-i", CUTS / f"{cid}.mp4"]
    for png in [hud["on"], hud["off"], *[c["frame"] for c in cues]]:
        inputs += ["-loop", 1, "-framerate", FPS, "-i", FRAMES / png]
    shows = ["lt(mod(t,1.4),0.7)", "gte(mod(t,1.4),0.7)"] + [f"between(t,{c['s']:.3f},{c['e']:.3f})" for c in cues]
    chain, last = [f"[0:v]{COVER}[v0]"], "v0"
    for k, show in enumerate(shows, start=1):
        chain.append(f"[{last}][{k}:v]overlay=0:0:shortest=1:enable='{show}'[v{k}]")
        last = f"v{k}"
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", f"[{last}]",
       "-t", f"{soundtrack.duration(CUTS / f'{cid}.mp4'):.4f}", *VIDEO, out)


def choice_segment(cid, choice, out):
    """The shot's last frame, held under the decision: the countdown runs, then the pick."""
    last = BUILD / f"last_{cid}.png"
    ff("-sseof", "-0.5", "-i", CUTS / f"{cid}.mp4", "-vf", COVER, "-update", 1, last)
    ff("-loop", 1, "-framerate", FPS, "-i", last, "-framerate", FPS, "-i", FRAMES / choice["pattern"],
       "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1[v]", "-map", "[v]",
       "-t", f"{choice['frames'] / FPS:.4f}", *VIDEO, out)


def end_segment(end, out):
    """The cliffhanger card typing out, then held, fading to black."""
    ff("-framerate", FPS, "-i", FRAMES / end["pattern"],
       "-vf", f"{COVER},tpad=stop_mode=clone:stop_duration={end['seconds']},fade=t=out:st={end['seconds'] - 1}:d=1",
       "-t", f"{end['seconds']:.4f}", *VIDEO, out)


def main():
    SEG.mkdir(parents=True, exist_ok=True)
    plan = draw_overlays()
    segs, sections, windows = [], [], []

    def add(name, seg, audio, music_up=False):
        t0 = sum(s["dur"] for s in sections)
        dur = soundtrack.duration(seg)
        if music_up:  # nothing is said here: let the score carry it
            windows.append((t0 if t0 else -1.0, t0 + dur))
        segs.append(seg)
        sections.append({"name": name, "dur": dur, **audio})

    seg = SEG / "00_title.mp4"
    title_segment(plan["title"], seg)
    add("title", seg, {"kind": "silence"}, music_up=True)
    for n, cid in enumerate(plan["path"], start=1):
        seg = SEG / f"{n:02d}_{cid}.mp4"
        film_segment(cid, plan, seg)
        add(cid, seg, {"kind": "film", "src": CUTS / f"{cid}.mp4"})
        if cid in plan["choices"]:
            seg = SEG / f"{n:02d}_{cid}_choice.mp4"
            choice_segment(cid, plan["choices"][cid], seg)
            add(f"{cid} decision", seg, {"kind": "silence"}, music_up=True)
    seg = SEG / "99_end.mp4"
    end_segment(plan["end"], seg)
    add("cliffhanger", seg, {"kind": "silence"}, music_up=True)

    total = sum(s["dur"] for s in sections)
    video = soundtrack.join_video(segs, BUILD / "joined.mp4")
    fg = soundtrack.foreground(sections, BUILD / "audio" / "foreground.wav")
    music = soundtrack.score(config.MEDIA / "film" / "music" / "score.mp3", total, windows, BUILD / "audio" / "score.wav")
    out = soundtrack.master(video, fg, music, REPO / "demo" / "capypunk_playthrough.mp4")
    soundtrack.report(out, sections)
    print(f"playthrough: {out} ({total:.1f}s, {out.stat().st_size / 1e6:.1f} MB): {' > '.join(plan['path'])}")


if __name__ == "__main__":
    main()
