"""Cut the demo video: real film clips + player/pipeline screenshots + a presenter voice-over + the score.

Run after the film and vibes pipelines and scripts/screenshots.cjs. Output: demo/capypunk_demo.mp4
Pass --rebuild to redraw every segment; by default, existing segments are reused and only the sound is remixed.
"""
import sys
from pathlib import Path

import duckdb
from PIL import Image, ImageDraw, ImageFont

import soundtrack  # scripts/soundtrack.py

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from capypunk import clients, config, media  # noqa: E402

REPO = config.REPO
BUILD = REPO / "demo" / "build"
SHOTS = BUILD / "shots"
SEG = BUILD / "segments"
for d in (BUILD, SHOTS, SEG):
    d.mkdir(parents=True, exist_ok=True)
CUTS = config.MEDIA / "film" / "cuts"
STILLS = config.MEDIA / "film" / "stills"
W, H, FPS = 1920, 1080, 30
PRESENTER = "JBFqnCBsd6RMkjVDRZzb"  # ElevenLabs "George": warm, captivating storyteller
FONT_DIR = Path("/usr/share/fonts")


def font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"]
    for n in names:
        hits = list(FONT_DIR.rglob(n))
        if hits:
            return ImageFont.truetype(str(hits[0]), size)
    return ImageFont.load_default()


def mono(size):
    for n in ("DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"):
        hits = list(FONT_DIR.rglob(n))
        if hits:
            return ImageFont.truetype(str(hits[0]), size)
    return ImageFont.load_default()


def facts():
    con = duckdb.connect(str(REPO / "capypunk.duckdb"), read_only=True)
    q = lambda s: con.execute(s).fetchall()
    f = {
        "spend": q("SELECT round(sum(cost_usd), 2) FROM film.spend")[0][0],
        "clip_takes": q("SELECT sum(takes) FROM film.spend WHERE kind = 'clip'")[0][0],
        "still_takes": q("SELECT sum(takes) FROM film.spend WHERE kind = 'still'")[0][0],
        "critic": q("SELECT hook, cliffhanger, overall FROM story.critic")[0],
        "headline": q("SELECT real_title FROM story.headline_digest ORDER BY rank LIMIT 1")[0][0],
        "matches": q("SELECT item, dialogue_match FROM film.spend WHERE kind = 'clip' ORDER BY item"),
        "stills": q("SELECT item, qa_score, takes FROM film.spend WHERE kind = 'still' ORDER BY item"),
        "vibe": q("SELECT alias, archetype, total_usd FROM vibes.cards LIMIT 1") if con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='vibes' AND table_name='cards'").fetchone()[0] else [],
        "quote": q("SELECT l.text FROM story.line_ratings r JOIN story.lines l USING (line_id) ORDER BY r.quotability DESC LIMIT 1")
        if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='story' AND table_name='line_ratings'").fetchone()[0] else [],
    }
    con.close()
    return f


# ---------------------------------------------------------------- cards
def gates_card(f, out):
    img = Image.new("RGB", (W, H), (7, 8, 13))
    d = ImageDraw.Draw(img)
    d.text((110, 90), "bruin run  ·  quality gates", font=mono(34), fill=(141, 143, 163))
    rows = [
        ("PASS", "raw.headlines            at least 5 fresh headlines (Telem)"),
        ("PASS", "story.stills             no real names leak into image prompts"),
        ("PASS", "story.lines              no real names leak into the script"),
        ("PASS", "story.lines              dialogue fits the shot (max 20 words)"),
        ("PASS", "story.paths              exactly four playthroughs, all end at c04"),
        ("PASS", f"story.critic             cliffhanger {f['critic'][1]}/10 >= 8, overall {f['critic'][2]}/10 >= 7"),
        ("PASS", "film.plan                worst case fits the render budget"),
        ("FAIL", "film.still_s07           qa_score below 6: frame missed the brief"),
        ("HOLD", "film.clip_d1, clip_d2    held back: upstream check failed"),
        ("PASS", "film.still_s07           re-shot with a director's note, qa passed"),
        ("PASS", "film.clip_*              actors said their lines (Scribe)"),
    ]
    y = 190
    for tag, text in rows:
        col = {"PASS": (46, 230, 255), "FAIL": (255, 59, 59), "HOLD": (242, 201, 76)}[tag]
        d.rounded_rectangle((110, y, 230, y + 54), 8, fill=col)
        d.text((130, y + 9), tag, font=mono(30), fill=(7, 8, 13))
        d.text((262, y + 9), text, font=mono(30), fill=(232, 230, 239))
        y += 72
    img.save(out)


def stills_grid(f, out):
    img = Image.new("RGB", (W, H), (7, 8, 13))
    d = ImageDraw.Draw(img)
    ids = ["s01", "s02", "s03", "s04a", "s04b", "s05", "s06", "s07", "s08"]
    scores = {sid: (qa, takes) for sid, qa, takes in f["stills"]}
    tw, th, pad = 560, 315, 40
    x0 = (W - (3 * tw + 2 * pad)) // 2
    y0 = 50
    for i, sid in enumerate(ids):
        im = Image.open(STILLS / f"{sid}.png").convert("RGB").resize((tw, th))
        x, y = x0 + (i % 3) * (tw + pad), y0 + (i // 3) * (th + 26 + pad // 2)
        img.paste(im, (x, y))
        qa, takes = scores.get(sid, ("?", "?"))
        label = f"{sid}   QA {qa}/10   {takes} take{'s' if takes != 1 else ''}"
        d.text((x, y + th + 4), label, font=mono(22), fill=(141, 143, 163))
    img.save(out)


def to_frame(src, out):
    """Fit any screenshot onto a 1920x1080 dark frame."""
    im = Image.open(src).convert("RGB")
    k = min((W - 120) / im.width, (H - 120) / im.height)
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    bg = Image.new("RGB", (W, H), (7, 8, 13))
    bg.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    bg.save(out)


# ---------------------------------------------------------------- segments
def enc(args, out):
    media.run(["ffmpeg", "-y", "-v", "error", *args, "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)])
    return out


def film_segment(cid, out):
    """A finished cut with its subtitles burned in."""
    vtt = CUTS / f"{cid}.vtt"
    style = "FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,BorderStyle=3,Outline=1,Shadow=0,MarginV=36"
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,subtitles='{vtt}':force_style='{style}'"
    return enc(["-i", str(CUTS / f"{cid}.mp4"), "-vf", vf, "-af", "aresample=48000"], out)


def still_segment(img, seconds, out, voice=None, zoom=True):
    dur = max(seconds, (media.duration(voice) + 0.8) if voice else 0)
    frames = int(dur * FPS)
    vf = (f"scale={W * 2}:{H * 2},zoompan=z='min(1+0.0006*on,1.06)':d={frames}:s={W}x{H}:fps={FPS}" if zoom
          else f"scale={W}:{H}")
    args = ["-loop", "1", "-t", f"{dur:.2f}", "-i", str(img)]
    if voice:
        args += ["-i", str(voice), "-filter_complex", f"[0:v]{vf}[v];[1:a]adelay=300|300,apad,atrim=0:{dur:.2f}[a]",
                 "-map", "[v]", "-map", "[a]"]
    else:
        args += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf, "-map", "0:v", "-map", "1:a"]
    return enc(args + ["-t", f"{dur:.2f}"], out)


def vo(name, text):
    p = BUILD / "vo" / f"{name}.mp3"
    if not p.exists():
        clients.eleven_tts(text, PRESENTER, p, model_id="eleven_v3")
    return p


def main():
    f = facts()
    gates_card(f, BUILD / "gates.png")
    stills_grid(f, BUILD / "stills_grid.png")
    for n in ("title", "choice1", "choice2", "end", "crew", "lineage_top", "making", "map"):
        if (SHOTS / f"{n}.png").exists():
            to_frame(SHOTS / f"{n}.png", BUILD / f"{n}_frame.png")
    spend = f["spend"]
    vibe = f["vibe"][0] if f["vibe"] else ("Spork", "Gadget Smith", 0.04)
    lines = {
        "v1": "This is CapyPunk: an interactive cyberpunk episode about the one creature a surveillance AI can't see.",
        "v2": "Every scene, every line and every choice was written, filmed and checked by three Bruin pipelines: "
              "fifty-five assets, from today's headlines to the final cut.",
        "v3": "Telem pulls this week's real AI news. Qwen 4 Max on Runwear turns it into Lumina's fiction, writes the "
              "branching script, and critiques its own draft. Bruin checks block rendering if a real name leaks, "
              "a path dead-ends, or the cliffhanger scores below eight.",
        "v4": "Qwen-Image paints every anchor frame from locked cast sheets. When one missed the brief, its check failed "
              "and Bruin held back that branch until it was re-shot. Wan three point oh Prime films each shot between two frames, "
              f"with lip-synced dialogue. The whole episode cost about {round(spend)} dollars to render.",
        "v5": f"Viewers can opt in with their own Instagram. Glass-er fetches it for about a tenth of a cent, and Qwen 4 Max "
              f"casts them as crew. This one is {vibe[0]}, a {vibe[1]}, and the player predicts their choices.",
        "v6": "Episode two is already being written. A Telem monitor is watching tomorrow's headlines.",
    }
    voices = {k: vo(k, t) for k, t in lines.items()}
    film = lambda cid: {"kind": "film", "src": CUTS / f"{cid}.mp4"}  # noqa: E731
    voice = lambda k: {"kind": "voice", "src": voices[k], "delay": 0.3}  # noqa: E731  (still_segment starts lines 0.3 s in)
    quiet = {"kind": "silence", "music_up": True}
    # (segment, how to draw it, what plays under it)
    plan = [
        ("01_c01", lambda o: film_segment("c01", o), film("c01")),
        ("02_c02", lambda o: film_segment("c02", o), film("c02")),
        ("03_choice1", lambda o: still_segment(BUILD / "choice1_frame.png", 3.5, o), quiet),
        ("04_b1", lambda o: film_segment("b1", o), film("b1")),
        ("05_title", lambda o: still_segment(BUILD / "title_frame.png", 6, o, voices["v1"]), voice("v1")),
        ("06_docs", lambda o: still_segment(BUILD / "lineage_top_frame.png", 8, o, voices["v2"]), voice("v2")),
        ("07_gates", lambda o: still_segment(BUILD / "gates.png", 10, o, voices["v3"], zoom=False), voice("v3")),
        ("08_stills", lambda o: still_segment(BUILD / "stills_grid.png", 10, o, voices["v4"], zoom=False), voice("v4")),
        ("09_crew", lambda o: still_segment(BUILD / "crew_frame.png", 8, o, voices["v5"]), voice("v5")),
        ("10_c03", lambda o: film_segment("c03", o), film("c03")),
        ("11_choice2", lambda o: still_segment(BUILD / "choice2_frame.png", 3, o), quiet),
        ("12_d2", lambda o: film_segment("d2", o), film("d2")),
        ("13_c04", lambda o: film_segment("c04", o), film("c04")),
        ("14_end", lambda o: still_segment(BUILD / "end_frame.png", 6, o, voices["v6"]), voice("v6")),
    ]
    rebuild = "--rebuild" in sys.argv  # otherwise reuse segments already drawn, so a sound fix keeps the picture
    segs, sections, windows, t = [], [], [], 0.0
    for name, draw, audio in plan:
        seg = SEG / f"{name}.mp4"
        if rebuild or not seg.exists():
            draw(seg)
        dur = soundtrack.duration(seg)
        if audio.get("music_up"):  # nothing is said here: let the score carry it
            windows.append((t, t + dur))
        segs.append(seg)
        sections.append({"name": name, "dur": dur, **audio})
        t += dur
    # after the last line, the score swells and fades out under the cliffhanger card
    windows.append((t - sections[-1]["dur"] + 0.3 + media.duration(voices["v6"]) + 0.2, t + 1))
    video = soundtrack.join_video(segs, BUILD / "joined.mp4")
    fg = soundtrack.foreground(sections, BUILD / "audio" / "foreground.wav")
    music = soundtrack.score(config.MEDIA / "film" / "music" / "score.mp3", t, windows, BUILD / "audio" / "score.wav")
    out = soundtrack.master(video, fg, music, REPO / "demo" / "capypunk_demo.mp4")
    soundtrack.report(out, sections)
    print(f"demo: {out} ({t:.1f}s, {out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
