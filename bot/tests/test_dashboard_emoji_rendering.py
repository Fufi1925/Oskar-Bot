#!/usr/bin/env python3
"""Custom emoji chosen in the dashboard must look like emoji in previews."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard" / "components" / "dashboard"
renderer = (DASH / "discord-emoji.tsx").read_text(encoding="utf-8")
failures = []


def check(name, condition):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(name)


check("renderer uses Discord's emoji CDN", "cdn.discordapp.com/emojis/" in renderer)
check("static custom emoji syntax is recognized", "[A-Za-z0-9_]+" in renderer)
check("animated custom emoji are GIFs", 'animated ? "gif" : "png"' in renderer)
check("legacy <emoji:id> values are supported", "<emoji:" in renderer)
check("text is kept in its original form for the API", "presentation-only" in renderer)

panels = [
    "applications-panel.tsx", "broadcast-panel.tsx", "compose-panel.tsx",
    "giveaway-detail.tsx", "giveaways-panel.tsx", "joindm-panel.tsx",
    "leveling-panel.tsx", "reactionroles-panel.tsx", "speedrun-panel.tsx",
    "teamlist-panel.tsx", "teamupdate-panel.tsx", "ticket-panels.tsx",
    "verify-panel.tsx", "welcome-form.tsx",
]
for filename in panels:
    body = (DASH / filename).read_text(encoding="utf-8")
    check(f"{filename} uses the shared emoji renderer", "DiscordEmoji" in body)

emoji_field = (DASH / "emoji-field.tsx").read_text(encoding="utf-8")
check("single emoji fields show the image after selection", "<DiscordEmoji value={value}" in emoji_field)
check("message fields use a rich editor instead of a plain textarea", "contentEditable={!disabled}" in emoji_field)
check("rich fields preserve the raw value for Discord", "dataset.emojiRaw" in emoji_field)
check("the picker inserts into the rich field", 'new CustomEvent("rich-text-insert"' in emoji_field)

print(f"\n{len(failures)} failures")
raise SystemExit(1 if failures else 0)
