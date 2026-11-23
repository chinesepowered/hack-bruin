"""Pilot step 3: two Wan clips branching from the same still + one ElevenLabs lip-sync test."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from capypunk import clients, config, media  # noqa: E402

bible = json.loads((config.SERIES / "bible.json").read_text())
stills = {s["still"]: s for s in json.loads((config.MEDIA / "pilot/stills/stills.json").read_text())}
cast = {f"{r['char']}_{r['i']}": r for r in json.loads((config.MEDIA / "pilot/cast/cast.json").read_text())}
out = config.media_dir("pilot", "clips")

# ElevenLabs: Vex's line, uploaded to Runware for the lip-sync test
line = "[whispers] They say the Grid can't see you, Yuzu. [softly laughs] Let's find out."
vex_voice = bible["characters"]["vex"]["voice"]["voice_id"]
vpath = clients.eleven_tts(line, vex_voice, out / "vex_line.mp3", model_id="eleven_v3")
vdur = media.duration(vpath)
up = clients.runware_upload(vpath)
print("voice", vpath, f"{vdur:.2f}s", "uploaded", bool(up.get("mediaURL") or up.get("mediaUUID")))

s02 = stills["s02"]["url"]
JOBS = {
    "p1_dialogue": dict(prompt=(
        "The pink-haired woman leans in close to the calm capybara and says softly, \"They say the Grid can't see you. Let's find out.\" "
        "She winks, rises and backs away into the steaming night-market crowd. The capybara stays perfectly still and blinks slowly, "
        "unbothered. Rain falls, neon flickers, the chrome surveillance orb drifts overhead. Ambient rain, distant market chatter."),
        first=s02, duration=6),
    "p2_branch": dict(prompt=(
        "The chrome surveillance orb descends and sweeps a blue scanning beam across the alley. When the beam crosses the pink-haired "
        "woman her expression tightens and the orb's iris flashes red, locking onto her. The beam passes right over the capybara without "
        "registering it. The capybara calmly turns and trots off down the wet alley, the cyan canister glowing on its harness. "
        "Tense electronic hum, rain."),
        first=s02, duration=6),
    "p3_lipsync": dict(prompt=(
        "Cinematic close-up of the pink-haired woman from the reference images in a rain-soaked neon alley at night, speaking softly "
        "and slyly to someone just below camera, lips moving in sync with the voice, steam and magenta-cyan neon behind her, "
        "shallow depth of field."),
        refs=[cast["vex_1"]["url"], s02], ref_audios=[up.get("mediaURL") or up.get("mediaUUID")],
        duration=max(3, min(10, round(vdur + 0.5)))),
}


def job(item):
    name, kw = item
    t0 = time.time()
    tu = clients.wan_submit(kw.pop("prompt"), **kw)
    row = clients.runware_wait(tu, timeout=1800, first_delay=40)
    p = clients.download(row["videoURL"], out / f"{name}.mp4")
    return {"clip": name, "path": str(p), "url": row["videoURL"], "cost": row.get("cost"),
            "seconds": round(time.time() - t0), "duration": media.duration(p), "audio": media.has_audio(p),
            "size": media.video_size(p)}


results = []
with ThreadPoolExecutor(3) as ex:
    futs = {ex.submit(job, it): it[0] for it in JOBS.items()}
    for f, name in futs.items():
        try:
            r = f.result()
            results.append(r)
            print("DONE", json.dumps(r))
        except Exception as e:  # keep the others going
            print("FAIL", name, str(e)[:500])
(out / "clips.json").write_text(json.dumps(results, indent=1))
