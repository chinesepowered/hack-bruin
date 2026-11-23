"""Pilot step 4: Instagram (via Glasser) -> Qwen4-Max typed vibe -> Qwen-Image crew card."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from capypunk import clients, config  # noqa: E402
from capypunk.vibes import VIBE_SCHEMA, vibe_messages, crew_card_prompt  # noqa: E402

d = config.MEDIA / "pilot" / "vibe"
profile = json.loads((d / "ig_profile.json").read_text())["output"]["data"]
posts = json.loads((d / "ig_posts.json").read_text())["output"]["data"]["posts"]

# download up to 6 photo thumbnails so the model sees them (CDN links are signed and short-lived)
imgs = []
for i, p in enumerate(posts):
    m = (p.get("media") or [{}])[0]
    if m.get("url") and len(imgs) < 6:
        try:
            imgs.append(clients.download(m["url"], d / f"post_{i}.jpg"))
        except Exception as e:
            print("skip image", i, str(e)[:120])

bible = json.loads((config.SERIES / "bible.json").read_text())
vibe, usage = clients.qwen_chat(vibe_messages(bible, profile, posts, imgs), schema=VIBE_SCHEMA,
                                schema_name="vibe", max_tokens=1200)
print(json.dumps(vibe, indent=1))
print("tokens", usage)
(d / "vibe.json").write_text(json.dumps(vibe, indent=1))

cast = {f"{r['char']}_{r['i']}": r for r in json.loads((config.MEDIA / "pilot/cast/cast.json").read_text())}
rows = clients.qwen_image(crew_card_prompt(bible, vibe), width=1024, height=1536, refs=[cast["yuzu_q1"]["url"]])
card = clients.download(rows[0]["imageURL"], d / "crew_card.png")
print("card", card, rows[0].get("cost"))
