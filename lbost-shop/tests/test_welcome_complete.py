#!/usr/bin/env python3
"""University-parity welcome/leave regression coverage."""
from pathlib import Path

from lbost_shop_bot.client import layout
from lbost_shop_bot import welcome_card

root = Path(__file__).resolve().parents[1]
main = (root / "lbost_shop_app/main.py").read_text(encoding="utf-8")
template = (root / "lbost_shop_app/templates/welcome.html").read_text(encoding="utf-8")
client = (root / "lbost_shop_bot/client.py").read_text(encoding="utf-8")
js = (root / "lbost_shop_app/static/dashboard.js").read_text(encoding="utf-8")
requirements = (root / "requirements.txt").read_text(encoding="utf-8").lower()

fields = {
    "welcome_type", "welcome_message", "welcome_auto_delete_duration",
    "welcome_embed_message", "welcome_embed_title", "welcome_embed_description",
    "welcome_embed_author_name", "welcome_embed_author_icon",
    "welcome_embed_footer_text", "welcome_embed_footer_icon",
    "welcome_embed_thumbnail", "welcome_embed_image", "color",
    "welcome_image_enabled", "welcome_image_url", "leave_enabled",
    "leave_channel_id", "leave_message", "leave_auto_delete_duration",
    "leave_image_enabled", "leave_image_url",
}
assert all(f'("{field}"' in main for field in fields)
assert 'data-page-tab="welcome"' in template and 'data-page-tab="leave"' in template
assert 'data-page-panel="welcome"' in template and 'data-page-panel="leave"' in template
assert "data-picker-open" in template and "<select" not in template
assert "Gegenereerde afbeelding" in template and "Gegenereerd afscheidsbeeld" in template
assert "Live-voorbeeld" in template and "Verzenden naar kanaal" in template
assert all(token in template for token in ("{user}", "{user_name}", "{user_nick}", "{user_avatar}", "{server_name}", "{server_membercount}"))
assert "send_greeting(member, \"welcome\")" in client
assert "send_greeting(member, \"leave\")" in client
assert "welcome_card.render" in client and "attachment://" in client
assert "extra_image_url" in client and "MediaGallery" in client
assert "data-greet-template" in js and "data-greet-preview" in js
assert 'draft, _draft_errors = _werte_aus_formular' in main, "Discord test must use the unsaved dashboard draft"
assert 'background_bytes=background_bytes' in main, "Discord test must render the selected custom background"
assert "pillow" in requirements

# The copied University renderer must produce a real PNG without network data.
image = welcome_card.render(
    name="Neuer", avatar_bytes=None, guild_name="University", member_count=1204,
    accent=0x5865F2,
)
assert image is not None and image.getvalue().startswith(b"\x89PNG\r\n\x1a\n")

# Components V2 supports the configured image and generated card together.
view = layout("Willkommen", "Text", image_url="https://example.org/a.png", extra_image_url="attachment://welcome.png")
container = view.children[0]
assert any(type(item).__name__ == "MediaGallery" for item in container.children)

print("ok   Welcome/Leave: zwei Tabs, alle Felder, Bildgenerator und Components V2")
