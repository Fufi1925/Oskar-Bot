# ╔══════════════════════════════════════════════════════════════════╗
# ║   The status panel's emojis                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The custom emojis uploaded to the Discord application, with fallbacks.

**The constraint that shapes this whole file:** an application-owned
emoji can only be used by the application that owns it. Discord's own
documentation says so plainly -- "an application can own up to 2000
emojis that can only be used by that app". There is no permission that
lifts it, and `USE_EXTERNAL_EMOJIS` does not apply.

That matters here because the status bot is a *second* application. If
these emojis were uploaded to the main bot's application, the status bot
posting ``<:online:1532...>`` produces exactly that literal text in the
message -- not a picture. A status panel reading ``<:online:15321681>``
is worse than one with a plain green circle.

So nothing is assumed. At start-up the bot asks Discord which emojis its
own application owns (``fetch_application_emojis``) and calls
``adopt()`` with the result. Only ids that come back are used; every
other one silently falls back to the unicode character that was there
before. The panel therefore looks right in both cases, and the log says
which happened.
"""

from __future__ import annotations

# ── What was uploaded, by name ────────────────────────────────────────
#
# The ids are from the application's emoji page. The names are theirs,
# typos included ("loding", "offllien") -- renaming them here would only
# make the two lists disagree.
# Each entry is (id, animated).
#
# The animated flag is not cosmetic: an animated emoji has to be written
# `<a:name:id>`. Writing `<:name:id>` for one produces no picture at all
# -- Discord prints the raw text instead. That is exactly what happened
# on the first deploy: uptime, website and zbot showed up (static, so
# `<:` was right) while online, offllien and loding appeared as literal
# ":online:" text, because all three are animated.
#
# Verified against the CDN rather than guessed: fetching
# cdn.discordapp.com/emojis/<id>.webp?animated=true and looking for the
# ANIM chunk in the RIFF container tells you which is which.
CUSTOM: dict[str, tuple[int, bool]] = {
    "loding": (1532168121182453950, True),
    "offllien": (1532168119597142068, True),
    "online": (1532168117319499839, True),
    "uptime": (1532168115339919552, False),
    "website": (1532168114085826863, False),
    "zbot": (1532168112810627222, False),
}

# ── Where each one is used, and what to show instead ──────────────────
#
# Keyed by the role it plays in the panel rather than by its name, so a
# renamed emoji is a one-line change here and nothing else moves.
#
# The fallbacks are the characters the panel used before any of this
# existed, which is why losing the custom set costs nothing.
ROLES: dict[str, tuple[str, str]] = {
    # state of a bot / of everything
    "online": ("online", "🟢"),
    "down": ("offllien", "🔴"),
    "starting": ("loding", "🟡"),
    "unknown": ("", "⚪"),
    # rows and links
    "uptime": ("uptime", "⏱️"),
    "website": ("website", "🖥️"),
    "bot": ("zbot", "🤖"),
    "invite": ("", "➕"),
}

# Filled in by adopt(). Empty until then, which means "use the
# fallbacks" -- the safe direction: a panel drawn before the check has
# finished shows plain circles rather than raw text.
#
# name -> (id, animated). The animated flag here comes from Discord's
# answer, not from the table above, so an emoji that gets re-uploaded as
# a still image starts rendering correctly without a code change.
_usable: dict[str, tuple[int, bool]] = {}


def adopt(owned: dict[str, tuple[int, bool]]) -> list[str]:
    """
    Record which of the emojis this application actually owns.

    `owned` maps name -> (id, animated), as read from Discord. Only
    entries whose id matches the one listed above are taken: a name
    collision with some unrelated emoji uploaded later should not
    silently change what the panel draws.

    Discord's own `animated` flag wins over the table. The table is
    there so the right thing happens before the first check completes;
    once Discord has answered, its answer is the truth -- re-uploading
    an emoji as a still image then needs no code change.

    Returns the names that were accepted, for the log line.
    """
    _usable.clear()
    for name, (emoji_id, animated) in CUSTOM.items():
        found = owned.get(name)
        if not found:
            continue
        found_id, found_animated = found
        if found_id == emoji_id:
            _usable[name] = (found_id, bool(found_animated))
    return sorted(_usable)


def missing() -> list[str]:
    """Which of the uploaded emojis this application cannot use."""
    return sorted(set(CUSTOM) - set(_usable))


def markup(role: str) -> str:
    """
    The emoji for a role, as it goes into message text.

    A custom one becomes ``<a:name:id>`` when it is animated and
    ``<:name:id>`` when it is not. Getting that prefix wrong does not
    degrade gracefully -- Discord renders the raw text, so the panel
    reads ":online:" instead of showing a picture.
    """
    name, fallback = ROLES.get(role, ("", "•"))
    if name and name in _usable:
        emoji_id, animated = _usable[name]
        return f"<{'a' if animated else ''}:{name}:{emoji_id}>"
    return fallback


def button(role: str):
    """
    The emoji for a role, as a button accepts it.

    discord.py takes either a `PartialEmoji` or a plain string here, and
    a custom emoji has to be the former -- passing ``<:name:id>`` as a
    string makes Discord reject the component.
    """
    name, fallback = ROLES.get(role, ("", "•"))
    if name and name in _usable:
        import discord

        emoji_id, animated = _usable[name]
        # `animated` matters here too: a button whose emoji is animated
        # but not flagged as such shows a still frame at best.
        return discord.PartialEmoji(name=name, id=emoji_id, animated=animated)
    return fallback


def state_mark(ok: bool | None) -> str:
    """The checklist mark: measured good, measured bad, or not looked at."""
    return markup({True: "online", False: "down", None: "unknown"}[ok])
