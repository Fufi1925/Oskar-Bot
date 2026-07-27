# ╔══════════════════════════════════════════════════════════════════╗
# ║   Leveling: ready-made role ladders and a starter setup          ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Building a level-role ladder by hand means creating a dozen roles in
Discord, colouring them, dragging them into order and then typing a
reward command for each one. This does the whole thing in one call.

The colour ramp is computed in HSL rather than by listing hex codes, so
a five-step and a fifteen-step ladder both come out evenly spaced.
"""

from __future__ import annotations

import colorsys

# Named ramps. Hues are degrees on the colour wheel, and `sweep` says how
# far to travel from `start` — signed, because which way round matters and
# cannot be guessed. Going from blue (220°) to gold (45°) the short way
# passes through green; the long way passes through violet and red, which
# is the one that actually looks like a sunrise.
RAMPS: dict[str, dict] = {
    "sunrise": {
        "label": "Sonnenaufgang",
        "description": "Blau über Violett und Rot zu Gold",
        "start": 220, "sweep": 185, "saturation": 0.72, "lightness": 0.58,
    },
    "ocean": {
        "label": "Ozean",
        "description": "Türkis zu tiefem Blau",
        "start": 175, "sweep": 70, "saturation": 0.68, "lightness": 0.52,
    },
    "forest": {
        "label": "Wald",
        "description": "Hellgrün zu dunklem Tannengrün",
        "start": 95, "sweep": 60, "saturation": 0.55, "lightness": 0.45,
    },
    "fire": {
        "label": "Feuer",
        "description": "Gelb über Orange zu Rot",
        "start": 50, "sweep": -50, "saturation": 0.85, "lightness": 0.55,
    },
    "candy": {
        "label": "Bonbon",
        "description": "Pink über Violett zu Blau",
        "start": 330, "sweep": -80, "saturation": 0.70, "lightness": 0.65,
    },
    "grey": {
        "label": "Dezent",
        "description": "Helles zu dunklem Grau, fällt kaum auf",
        "start": 210, "sweep": 0, "saturation": 0.10, "lightness": 0.62,
        # No hue change, so the ramp darkens instead.
        "lightness_end": 0.30,
    },
}

# Name templates. {level} is the level, {n} the position in the ladder.
NAME_STYLES: dict[str, dict] = {
    "level": {"label": "Level 5", "template": "Level {level}"},
    "lvl": {"label": "Lvl 5", "template": "Lvl {level}"},
    "arrow": {"label": "▸ Level 5", "template": "▸ Level {level}"},
    "star": {"label": "★ Level 5", "template": "★ Level {level}"},
    "metal": {
        "label": "Bronze, Silber, Gold …",
        "names": [
            "Bronze", "Silber", "Gold", "Platin", "Diamant",
            "Meister", "Großmeister", "Champion", "Legende", "Unsterblich",
        ],
    },
    "rank": {
        "label": "Neuling, Stammgast …",
        "names": [
            "Neuling", "Bekannt", "Stammgast", "Veteran", "Erfahren",
            "Experte", "Elite", "Vorbild", "Ikone", "Legende",
        ],
    },
}

# How the levels themselves are spaced.
SPACINGS: dict[str, dict] = {
    "linear": {
        "label": "Gleichmäßig",
        "description": "5, 10, 15, 20 … gleicher Abstand",
    },
    "growing": {
        "label": "Wachsend",
        "description": "5, 12, 21, 32 … die Abstände werden größer",
    },
    "milestones": {
        "label": "Runde Zahlen",
        "description": "5, 10, 25, 50, 75, 100 …",
    },
}

MILESTONES = [5, 10, 25, 50, 75, 100, 150, 200, 300, 400, 500]


def ramp_colours(ramp: str, count: int) -> list[int]:
    """`count` colours evenly spaced along a ramp, as 0xRRGGBB ints."""
    config = RAMPS.get(ramp, RAMPS["sunrise"])
    start = config["start"]
    sweep = config["sweep"]
    saturation = config["saturation"]
    lightness = config["lightness"]
    lightness_end = config.get("lightness_end", lightness)

    colours = []
    for index in range(count):
        position = index / (count - 1) if count > 1 else 0
        hue = ((start + sweep * position) % 360) / 360
        level_lightness = lightness + (lightness_end - lightness) * position
        red, green, blue = colorsys.hls_to_rgb(hue, level_lightness, saturation)
        colours.append(
            (int(red * 255) << 16) | (int(green * 255) << 8) | int(blue * 255)
        )
    return colours


def ladder_levels(spacing: str, count: int, step: int = 5) -> list[int]:
    """Which levels get a role."""
    count = max(1, min(count, 25))
    step = max(1, min(step, 100))

    if spacing == "milestones":
        levels = MILESTONES[:count]
        # Carry on past the built-in list rather than returning fewer.
        while len(levels) < count:
            levels.append(levels[-1] + 100)
        return levels

    if spacing == "growing":
        levels, current, gap = [], step, step
        for _ in range(count):
            levels.append(current)
            gap += max(1, step // 2)
            current += gap
        return levels

    return [step * (index + 1) for index in range(count)]


def ladder_names(style: str, levels: list[int]) -> list[str]:
    """A name per level."""
    config = NAME_STYLES.get(style, NAME_STYLES["level"])

    if "names" in config:
        names = config["names"]
        out = []
        for index, level in enumerate(levels):
            if index < len(names):
                out.append(names[index])
            else:
                # Past the list, fall back to something that stays unique.
                out.append(f"{names[-1]} {index - len(names) + 2}")
        return out

    template = config["template"]
    return [
        template.format(level=level, n=index + 1)
        for index, level in enumerate(levels)
    ]


def build_ladder(
    *, ramp: str = "sunrise", style: str = "level", spacing: str = "linear",
    count: int = 5, step: int = 5,
) -> list[dict]:
    """
    The full plan: level, name and colour for each rung.

    Returned without touching Discord so the dashboard can show a preview
    and let people change their mind before anything is created.
    """
    levels = ladder_levels(spacing, count, step)
    names = ladder_names(style, levels)
    colours = ramp_colours(ramp, len(levels))

    return [
        {
            "level": level,
            "name": name,
            "colour": colour,
            "colour_hex": f"#{colour:06x}",
        }
        for level, name, colour in zip(levels, names, colours)
    ]


# Sensible defaults for a server switching leveling on for the first time.
STARTER_SETTINGS = {
    "enabled": 1,
    "min_xp": 15,
    "max_xp": 25,
    "cooldown_seconds": 60,
    "announce_mode": "channel",
    "level_message": "🎉 {user} ist jetzt **Level {level}**!",
    # Level-ups clean up after themselves; a rank card sticks around a
    # little longer because people screenshot it.
    "delete_after": 60,
    "command_delete_after": 0,
    "stack_roles": 0,
    "card_style": "image",
}
