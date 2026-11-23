"""The vibe check: a viewer's own public Instagram -> an in-world persona + predicted choices.

Privacy by construction: the schema only has fun in-world fields, so the model has nowhere to put
guesses about age, ethnicity, religion, health, politics or sexuality, and the card shows an
original character inspired by the vibe, never the viewer's face.
"""
from __future__ import annotations

import json

from . import clients

ARCHETYPES = ["Netrunner", "Street Racer", "Night-Market Chef", "Rooftop Romantic",
              "Corporate Defector", "Hot-Spring Monk", "Gadget Smith", "Wandering Ronin"]

VIBE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "alias": {"type": "string", "description": "in-world street name, 1-2 words"},
        "archetype": {"type": "string", "enum": ARCHETYPES},
        "palette": {"type": "array", "items": {"type": "string", "description": "hex color like #FF3EA5"}},
        "risk_appetite": {"type": "integer", "description": "1 (cautious) to 5 (reckless)"},
        "trust_pick": {"type": "string", "enum": ["vex", "kade"]},
        "trust_reason": {"type": "string", "description": "one playful line citing their posts"},
        "package_pick": {"type": "string", "enum": ["hand_over", "open"]},
        "package_reason": {"type": "string", "description": "one playful line citing their posts"},
        "most_like": {"type": "string", "enum": ["vex", "kade", "sable", "yuzu"]},
        "tagline": {"type": "string", "description": "one-line in-world bio, under 90 characters"},
        "loadout": {"type": "string", "description": "outfit and props for their crew card, drawn from their interests"},
    },
    "required": ["alias", "archetype", "palette", "risk_appetite", "trust_pick", "trust_reason",
                 "package_pick", "package_reason", "most_like", "tagline", "loadout"],
}

SYSTEM = (
    "You are the casting director for CapyPunk, an interactive cyberpunk film. A viewer opted in and "
    "shared their own public Instagram. Read their vibe from captions and photos and cast them as a "
    "character in Halcyon City. Be playful and flattering, cite specific things they post about, and "
    "predict how they will choose. Use only the fields provided. Never guess or mention age, ethnicity, "
    "nationality, religion, health, politics, sexuality, income or relationships, and never use their real name."
)


def vibe_messages(bible: dict, profile: dict, posts: list[dict], images: list) -> list[dict]:
    caps = [{"type": p.get("productType"), "likes": p.get("likes"), "caption": (p.get("caption") or "")[:280],
             "hashtags": p.get("hashtags")} for p in posts]
    story = {
        "choice_1": "Who do you trust? Vex (pink-haired netrunner who hired Yuzu, take the rooftops) or Kade "
                    "(charming street racer who says Vex sold you out, ride the undercity).",
        "choice_2": "Sable, Lumina's fixer, wants the package: hand it over, or open it yourself?",
        "cast": {k: v.get("role") for k, v in bible["characters"].items() if k in ("vex", "kade", "sable", "yuzu")},
    }
    text = (f"Story: {json.dumps(story)}\n\nProfile bio: {profile.get('bio')!r}; posts: {profile.get('posts')}; "
            f"bio link title: {[b.get('title') for b in profile.get('bioLinks') or []]}\n\n"
            f"Recent posts: {json.dumps(caps, ensure_ascii=False)}\n\n"
            "Their photos follow. Palette: exactly 3 neon hex colors. risk_appetite: 1-5.")
    content = [{"type": "text", "text": text}] + [clients.image_part(p) for p in images]
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


def crew_card_prompt(bible: dict, vibe: dict) -> str:
    """Every viewer's crew card is their own capybara: fun, on-brand, and never a likeness of their face."""
    return (
        f"Vertical character-card portrait for a cyberpunk film. A capybara crew member of Halcyon City "
        f"codenamed {vibe['alias']}, a {vibe['archetype']}: same species and art style as the capybara in the "
        f"reference image but its own character, wearing {vibe['loadout']}. Color palette "
        f"{', '.join(vibe['palette'])}. It stands proudly on a rain-soaked neon street, three-quarter view, "
        f"calm half-lidded eyes. {bible['style']}. No text, no letters, no logos, no watermark."
    )


def qwen_cost(usage: dict) -> float:
    """Qwen4-Max on Runware: $1.50 per 1M input tokens, $4.50 per 1M output tokens."""
    return round((usage.get("prompt_tokens") or 0) * 1.5e-6 + (usage.get("completion_tokens") or 0) * 4.5e-6, 5)


def predicted_path(vibe: dict) -> str:
    return ("c01 > c02 > " + ("a1" if vibe["trust_pick"] == "vex" else "b1") + " > c03 > "
            + ("d1" if vibe["package_pick"] == "hand_over" else "d2") + " > c04")
