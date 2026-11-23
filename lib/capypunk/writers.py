"""The writers' room: prompts and JSON schemas for Qwen4-Max.

Flow: today's headlines -> a digest of fictionalizable stories -> an episode script that follows the
series bible's fixed branching structure -> an independent critic score that gates rendering.
"""
from __future__ import annotations

import json

from . import clients

SPEECH = {
    "vex": "a low, smoky, confident young woman's voice",
    "kade": "a husky, charming man's voice with a playful drawl",
    "sable": "a velvety, unhurried woman's voice with a cultured British accent",
}

# ---------------------------------------------------------------- headline digest
DIGEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"stories": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "real_title": {"type": "string"},
            "gist": {"type": "string", "description": "one sentence, what actually happened"},
            "real_entities": {"type": "array", "items": {"type": "string"},
                              "description": "every real company, product, person and place name in the story"},
            "lumina_twist": {"type": "string", "description": "how megacorp Lumina's fictional version of this plays in Halcyon City"},
            "billboard": {"type": "string", "description": "an in-world Lumina ad line, max 6 words, no real names"},
            "dystopia_score": {"type": "integer", "description": "1-10, how well it fuels an AI-surveillance noir"},
        },
        "required": ["url", "real_title", "gist", "real_entities", "lumina_twist", "billboard", "dystopia_score"],
    }}},
    "required": ["stories"],
}


def digest_messages(pages: list[dict]) -> list[dict]:
    docs = "\n\n".join(f"### {p['title']}\nURL: {p['url']}\n{(p.get('content') or '')[:5000]}" for p in pages)
    return [
        {"role": "system", "content": (
            "You are the research desk of a writers' room for CapyPunk, a cyberpunk noir about Lumina, a "
            "megacorp whose Serenity Grid AI reads every citizen's fear. Read today's real tech headlines and "
            "pick the three that best fuel the story. For each, list every real entity name it mentions (so we "
            "can make sure none leak into the fiction), and invent Lumina's fictional mirror of it.")},
        {"role": "user", "content": f"Today's articles:\n\n{docs}\n\nReturn the three best stories, best first."},
    ]


# ---------------------------------------------------------------- episode
def episode_schema(still_ids: list[str], clip_ids: list[str]) -> dict:
    line = {"type": "object", "additionalProperties": False,
            "properties": {"speaker": {"type": "string", "enum": ["vex", "kade", "sable"]},
                           "line": {"type": "string"}},
            "required": ["speaker", "line"]}
    narr = {"type": "object", "additionalProperties": False,
            "properties": {"text": {"type": "string"}, "start_s": {"type": "number"}},
            "required": ["text", "start_s"]}
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "episode_title": {"type": "string"},
            "headline_hook": {"type": "string", "description": "which real story inspired the episode and how, in one sentence"},
            "billboard": {"type": "string", "description": "the Lumina billboard slogan seen in the cold open, max 6 words"},
            "stills": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"id": {"type": "string", "enum": still_ids}, "prompt": {"type": "string"}},
                "required": ["id", "prompt"]}},
            "clips": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"id": {"type": "string", "enum": clip_ids},
                               "action": {"type": "string"},
                               "dialogue": {"type": "array", "items": line},
                               "narration": {"type": "array", "items": narr},
                               "sfx": {"type": "string"}},
                "required": ["id", "action", "dialogue", "narration", "sfx"]}},
            "choice_labels": {"type": "object", "additionalProperties": False,
                              "properties": {k: {"type": "string"} for k in ("ch1_a", "ch1_b", "ch2_a", "ch2_b")},
                              "required": ["ch1_a", "ch1_b", "ch2_a", "ch2_b"]},
            "cliffhanger_card": {"type": "string", "description": "one ominous line shown on the final black card"},
        },
        "required": ["episode_title", "headline_hook", "billboard", "stills", "clips", "choice_labels", "cliffhanger_card"],
    }


CRAFT = """Craft rules (follow exactly):
- Each clip is ONE continuous shot, no cuts, of the given duration. 'action' is a video-model prompt: the camera move, what happens beat by beat from the clip's start still to its end still, performances, lighting changes. Present tense, concrete, visual. 60-110 words.
- Dialogue is spoken on screen by the humans (Yuzu never speaks). At most 2 lines per clip, at most 16 words per clip in total, so it fits 8 seconds. Every line must be quotable: sharp, sexy, menacing or funny. No exposition dumps.
- Narration is wry noir from an older narrator, short sentences, present tense. Only in c01 (start_s 0, before anyone speaks, max 2 sentences), in c04 (the closing line), and optionally one short line in a1 or b1. Narration never overlaps dialogue.
- Still prompts describe a single cinematic 16:9 frame: composition, who is where (refer to characters by name), expressions, lighting, camera angle and lens. The still for a clip's end must be a natural endpoint of that clip's action. 50-90 words. Billboard text may appear in quotes.
- The cliffhanger must land: every path ends on the same final beat, and the viewer must ache to know what PROJECT HALCYON is and what the Grid will do now that it can see Yuzu.
- Weave today's headline in through the Lumina billboard and one line of Sable's, fictionalized. Never use any real company, product or person name.
- Glamorous, flirty, PG-13. No gore, no explicit content."""


def episode_messages(bible: dict, digest: list[dict], feedback: str | None = None) -> list[dict]:
    chars = {k: {kk: v.get(kk) for kk in ("name", "role", "look")} for k, v in bible["characters"].items()
             if k in ("yuzu", "vex", "kade", "sable")}
    structure = [{k: c.get(k) for k in ("id", "title", "start", "end", "duration", "beat", "choice")}
                 for c in bible["structure"]["clips"]]
    user = {
        "world": bible["world"], "tone": bible["tone"], "characters": chars, "rules": bible["rules"],
        "structure": structure, "stills": bible["structure"]["stills_spec"],
        "todays_headlines": [{k: s[k] for k in ("gist", "lumina_twist", "billboard")} for s in digest],
    }
    msgs = [
        {"role": "system", "content": (
            "You are the head writer of CapyPunk, an interactive cyberpunk noir film. You write tight, "
            "captivating, cinematic scenes for a branching episode with a fixed structure. " + CRAFT)},
        {"role": "user", "content": "Write Episode 1 from this brief. Fill every still and every clip.\n\n"
                                    + json.dumps(user, ensure_ascii=False, indent=1)},
    ]
    if feedback:
        msgs.append({"role": "user", "content": "A script editor reviewed your last draft. Rewrite it to fix "
                                                "every note while keeping what works:\n" + feedback})
    return msgs


# ---------------------------------------------------------------- critic
CRITIC_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        **{k: {"type": "integer", "description": "1-10"} for k in
           ("hook", "stakes", "characters", "dialogue", "cliffhanger", "coherence", "overall")},
        "notes": {"type": "string"},
        "fixes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hook", "stakes", "characters", "dialogue", "cliffhanger", "coherence", "overall", "notes", "fixes"],
}


def critic_messages(bible: dict, script: dict) -> list[dict]:
    return [
        {"role": "system", "content": (
            "You are a tough, specific script editor for short-form interactive films. Score honestly: 7 is "
            "solid, 9 is rare. Judge whether a hackathon audience would be hooked in the first 5 seconds, care "
            "about the choices, and be desperate for episode 2.")},
        {"role": "user", "content": json.dumps({"logline": bible["logline"], "structure": [
            {k: c.get(k) for k in ("id", "title", "choice")} for c in bible["structure"]["clips"]],
            "script": script}, ensure_ascii=False)},
    ]


def write_episode(bible: dict, digest: list[dict], min_overall: int = 8, max_rounds: int = 2):
    """Draft -> critique -> revise. Returns (script, critique, rounds, usage_tokens)."""
    still_ids = bible["structure"]["stills"]
    clip_ids = [c["id"] for c in bible["structure"]["clips"]]
    schema = episode_schema(still_ids, clip_ids)
    feedback, tokens = None, 0
    script = critique = None
    for rnd in range(1, max_rounds + 1):
        script, u1 = clients.qwen_chat(episode_messages(bible, digest, feedback), schema=schema,
                                       schema_name="episode", max_tokens=12000)
        critique, u2 = clients.qwen_chat(critic_messages(bible, script), schema=CRITIC_SCHEMA,
                                         schema_name="critique", max_tokens=6000)
        tokens += (u1.get("total_tokens") or 0) + (u2.get("total_tokens") or 0)
        if critique["overall"] >= min_overall and critique["cliffhanger"] >= min_overall:
            return script, critique, rnd, tokens
        feedback = critique["notes"] + "\nFixes:\n- " + "\n- ".join(critique["fixes"])
    return script, critique, max_rounds, tokens
