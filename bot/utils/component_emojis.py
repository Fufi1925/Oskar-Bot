"""Custom emojis belong in the emoji field of Discord controls, not labels."""
import re

_CUSTOM = re.compile(r"<(a?):([A-Za-z0-9_]{1,32}):(\d{5,22})>|<emoji:(\d{5,22})>")


def label_emoji(label, emoji=None, *, limit=100):
    text = str(label or "")
    matches = list(_CUSTOM.finditer(text))
    if not emoji and matches:
        match = matches[0]
        emoji = (f"<{'a' if match[1] else ''}:{match[2]}:{match[3]}>"
                 if match[3] else f"<:emoji:{match[4]}>")
    if isinstance(emoji, str):
        emoji = emoji.strip() or None
        legacy = re.fullmatch(r"<emoji:(\d{5,22})>", emoji or "")
        if legacy:
            emoji = f"<:emoji:{legacy[1]}>"
    text = _CUSTOM.sub("", text).strip()
    return text[:limit] or ("\u200b" if emoji else "Option"), emoji


def normalize_controls(item):
    """Keep callbacks, values, IDs and layout intact while fixing labels."""
    if hasattr(item, 'label') and hasattr(item, 'emoji') and _CUSTOM.search(str(item.label or '')):
        item.label, item.emoji = label_emoji(item.label, item.emoji, limit=80)
    for option in getattr(item, 'options', ()):
        if _CUSTOM.search(option.label):
            option.label, option.emoji = label_emoji(option.label, option.emoji)
    for child in getattr(item, 'children', ()):
        normalize_controls(child)
    return item


def category_text(name, emoji=None):
    """Custom emoji markup is supported in V2 text, outside bold labels."""
    label, icon = label_emoji(name, emoji)
    return f"{icon} **{label}**" if icon else f"**{label}**"
