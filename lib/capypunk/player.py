"""Build the interactive player: player/template.html + episode.json + web media -> player/dist."""
from __future__ import annotations

import datetime as dt
import json
import shutil

import duckdb

from . import config


def _cues(vtt_path) -> list[dict]:
    """WebVTT -> [{s, e, t}] with only <b>/<i> kept, so the page can draw its own subtitles."""
    import html
    import re
    def secs(ts):
        h, m, rest = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)
    out, blocks = [], open(vtt_path, encoding="utf-8").read().split("\n\n")
    for b in blocks:
        lines = [ln for ln in b.strip().splitlines() if ln.strip()]
        if not lines or "-->" not in lines[0]:
            continue
        a, z = [x.strip() for x in lines[0].split("-->")]
        text = html.escape(" ".join(lines[1:]))
        text = re.sub(r"&lt;(/?[bi])&gt;", r"<\1>", text)
        out.append({"s": round(secs(a), 3), "e": round(secs(z), 3), "t": text})
    return out


def _rows(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _table_exists(con, schema, table):
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
                            [schema, table]).fetchone()[0])


def episode_data(db_path=None) -> dict:
    con = duckdb.connect(str(db_path or config.REPO / "capypunk.duckdb"), read_only=True)
    try:
        ep = _rows(con, "SELECT episode_id, episode_title, headline_hook, billboard, cliffhanger_card FROM story.episode")[0]
        clips = _rows(con, "SELECT * FROM film.manifest ORDER BY ord")
        choices = _rows(con, "SELECT option_key, choice_id, clip_id, option_idx, prompt, label, next_clip FROM story.choices ORDER BY option_key")
        lines = _rows(con, "SELECT clip_id, kind, speaker, text FROM story.lines ORDER BY ord, kind, seq")
        paths = _rows(con, "SELECT path, picks, runtime_s FROM story.paths ORDER BY path")
        spend = _rows(con, "SELECT kind, count(*) AS items, round(sum(cost_usd), 2) AS usd, sum(takes) AS takes FROM film.spend GROUP BY 1")
        critic = _rows(con, "SELECT hook, stakes, characters, dialogue, cliffhanger, coherence, overall FROM story.critic")
        headlines = _rows(con, "SELECT rank, real_title, url, billboard FROM story.headline_digest ORDER BY rank")
        vibes = _rows(con, "SELECT * FROM vibes.cards") if _table_exists(con, "vibes", "cards") else []
    finally:
        con.close()
    for c in clips:
        c["next"] = json.loads(c.pop("next_json") or "[]")
        c["video"] = "media/" + c["video"].split("/")[-1]
        c["cues"] = _cues(config.REPO / c.pop("vtt"))
        c["poster"] = f"media/{c['start_still']}.jpg"
        c["choice"] = [o for o in choices if o["clip_id"] == c["clip_id"]]
        c["lines"] = [ln for ln in lines if ln["clip_id"] == c["clip_id"]]
    for v in vibes:
        v["card"] = "media/" + str(v.get("card_path", "")).split("/")[-1]
    bible = json.loads((config.SERIES / "bible.json").read_text())
    series = {"title": bible.get("title"), "tagline": bible.get("tagline"), "logline": bible.get("logline")}
    return {"series": series, "episode": ep, "clips": clips, "paths": paths, "spend": spend, "critic": critic[0] if critic else None,
            "headlines": headlines, "vibes": vibes, "built_at": dt.datetime.now(dt.timezone.utc).isoformat()}


FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' rx='14' fill='%2307080d'/%3E%3Ccircle cx='32' cy='36' r='17' fill='%23f2c94c'/%3E"
           "%3Cpath d='M32 19c2-6 7-8 11-7-2 5-6 8-11 7z' fill='%232ee6ff'/%3E%3C/svg%3E")


def standalone(page: str, data: dict) -> str:
    """Wrap the player in a full HTML document for static hosting (head metadata, favicon, link previews)."""
    head_end = page.index('<div class="wrap">')
    head, body = page[:head_end], page[head_end:]
    series = data.get("series") or {}
    desc = (series.get("logline") or "").replace('"', "&quot;")
    meta = ('<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f'<meta name="description" content="{desc}">\n'
            '<meta property="og:title" content="CapyPunk: Episode 1, Signature Zero">\n'
            f'<meta property="og:description" content="{desc}">\n'
            '<meta property="og:type" content="video.episode">\n<meta property="og:image" content="media/s03.jpg">\n'
            '<meta name="twitter:card" content="summary_large_image">\n<meta name="theme-color" content="#07080d">\n'
            f'<link rel="icon" href="{FAVICON}">\n')
    return f'<!doctype html>\n<html lang="en">\n<head>\n{meta}{head}</head>\n<body>\n{body}</body>\n</html>\n'


def build(out_dir=None) -> dict:
    out = config.REPO / "site" if out_dir is None else out_dir
    media_out = out / "media"
    media_out.mkdir(parents=True, exist_ok=True)
    data = episode_data()
    film = config.MEDIA / "film"
    for c in data["clips"]:
        shutil.copy2(film / "cuts" / f"{c['clip_id']}.mp4", media_out / f"{c['clip_id']}.mp4")
    import subprocess
    for s in sorted((film / "stills").glob("s*.png")):
        if "_take" in s.name:
            continue
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(s), "-vf", "scale=1280:-2", "-q:v", "3",
                        str(media_out / (s.stem + ".jpg"))], check=True)
    for v in data["vibes"]:
        src = config.REPO / str(v.get("card_path", ""))
        if src.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "scale=720:-2", "-q:v", "3",
                            str(media_out / (src.stem + ".jpg"))], check=True)
            v["card"] = "media/" + src.stem + ".jpg"
    score = film / "music" / "score.mp3"
    if score.exists():
        shutil.copy2(score, media_out / "score.mp3")
        data["score"] = "media/score.mp3"
    template = (config.PLAYER / "template.html").read_text()
    html = template.replace("/*__EPISODE_JSON__*/null", json.dumps(data, default=str, ensure_ascii=True).replace("</", "<\\/"))
    (out / "index.html").write_text(standalone(html, data))
    return {"built_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), "path": str(out),
            "clips": len(data["clips"]), "vibes": len(data["vibes"])}
