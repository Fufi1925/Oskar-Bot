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
CUSTOM = {
    "loding": 1532168121182453950,
    "offllien": 1532168119597142068,
    "online": 1532168117319499839,
    "uptime": 1532168115339919552,
    "website": 1532168114085826863,
    "zbot": 1532168112810627222,
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
_usable: dict[str, int] = {}


def adopt(owned: dict[str, int]) -> list[str]:
    """
    Record which of the emojis this application actually owns.

    `owned` maps name -> id, as read from Discord. Only entries whose id
    matches the one listed above are taken: a name collision with some
    unrelated emoji uploaded later should not silently change what the
    panel draws.

    Returns the names that were accepted, for the log line.
    """
    _usable.clear()
    for name, emoji_id in CUSTOM.items():
        if owned.get(name) == emoji_id:
            _usable[name] = emoji_id
    return sorted(_usable)


def missing() -> list[str]:
    """Which of the uploaded emojis this application cannot use."""
    return sorted(set(CUSTOM) - set(_usable))


def markup(role: str) -> str:
    """
    The emoji for a role, as it goes into message text.

    A custom one becomes ``<:name:id>``; otherwise the plain character.
    """
    name, fallback = ROLES.get(role, ("", "•"))
    if name and name in _usable:
        return f"<:{name}:{_usable[name]}>"
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

        return discord.PartialEmoji(name=name, id=_usable[name])
    return fallback


def state_mark(ok: bool | None) -> str:
    """The checklist mark: measured good, measured bad, or not looked at."""
    return markup({True: "online", False: "down", None: "unknown"}[ok])
