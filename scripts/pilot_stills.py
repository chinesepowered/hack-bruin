"""Pilot step 2: anchor stills with both characters, then a Qwen4-Max consistency check."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from capypunk import clients, config  # noqa: E402

bible = json.loads((config.SERIES / "bible.json").read_text())
cast = {f"{r['char']}_{r['i']}": r for r in json.loads((config.MEDIA / "pilot/cast/cast.json").read_text())}
YUZU, VEX = cast["yuzu_q1"], cast["vex_1"]
refs = [YUZU["url"], VEX["url"]]
style = bible["style"]
out = config.media_dir("pilot", "stills")

SCENES = {
    "s02": ("Cinematic 16:9 medium-wide shot at night. In a narrow rain-soaked night-market alley of a neon cyberpunk megacity, "
            "the capybara from reference image 1 sits calmly on the wet pavement with half-lidded unbothered eyes, a yuzu fruit on its head. "
            "The woman from reference image 2, with neon-pink hair and a black leather jacket with pink piping, crouches beside it at eye level "
            "with a sly smirk, clipping the glowing cyan canister onto the capybara's harness. Steam rises from a noodle stall behind them; "
            f"a floating chrome surveillance orb with a glowing blue iris hovers above the crowd. {style}."),
    "s04a": ("Cinematic 16:9 wide action shot at night. On a neon-lit rooftop of a cyberpunk megacity in heavy rain, the capybara from "
             "reference image 1 runs across the wet rooftop beside the woman from reference image 2, who sprints with her pink hair "
             "whipping in the wind and looks back over her shoulder. Giant holographic billboards and a swarm of floating chrome "
             f"surveillance orbs with glowing irises in the background. {style}."),
    "s07": ("Cinematic 16:9 extreme close-up of the capybara from reference image 1: for the first time its calm half-lidded eyes are "
            "opening wide in alarm, a deep red light reflected in its dark eyes, rain droplets on its fur, the yuzu fruit on its head "
            f"slightly askew. Dramatic red and cyan rim light. {style}."),
}


def render(item):
    sid, prompt = item
    rows = clients.qwen_image(f"{prompt} {bible['negative_style']}.", refs=refs, n=1)
    r = rows[0]
    p = clients.download(r["imageURL"], out / f"{sid}.png")
    return {"still": sid, "url": r["imageURL"], "path": str(p), "cost": r.get("cost")}


with ThreadPoolExecutor(3) as ex:
    stills = list(ex.map(render, SCENES.items()))

QA_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "capybara_on_model": {"type": "boolean"},
        "woman_on_model": {"type": "boolean"},
        "woman_present": {"type": "boolean"},
        "style_consistent": {"type": "boolean"},
        "artifacts": {"type": "string"},
        "score": {"type": "integer"},
    },
    "required": ["capybara_on_model", "woman_on_model", "woman_present", "style_consistent", "artifacts", "score"],
}
for s in stills:
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "Image 1 is the capybara character sheet, image 2 is the woman's character sheet, image 3 is a new film still. "
                                 "Check the still for continuity: is the capybara the same character (fur, yuzu on head, harness, cyan canister)? "
                                 "If a pink-haired woman is present, is she the same character? Is the style consistent? List visible artifacts "
                                 "(extra limbs, warped faces, garbled text). Score 1-10 for usability as a film frame."},
        clients.image_part(YUZU["path"]), clients.image_part(VEX["path"]), clients.image_part(s["path"]),
    ]}]
    verdict, usage = clients.qwen_chat(msgs, schema=QA_SCHEMA, schema_name="still_qa", max_tokens=800)
    s["qa"] = verdict
    s["qa_tokens"] = usage
    print(s["still"], s["path"], json.dumps(verdict))
(out / "stills.json").write_text(json.dumps(stills, indent=1))
