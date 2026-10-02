"""Regression checks for the private 90-day ticket transcript flow."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COG = (ROOT / "bot/cogs/commands/ticket.py").read_text()
PANELS = (ROOT / "bot/api/ticket_panels.py").read_text()
ROUTES = (ROOT / "bot/api/routes/tickets.py").read_text()
SCHEMA = (ROOT / "bot/api/schema_guard.py").read_text()
DASHBOARD = (ROOT / "dashboard/components/dashboard/ticket-panels.tsx").read_text()
PAGE = (ROOT / "dashboard/app/Tickets/Transkript/[ticketId]/page.tsx").read_text()
CSS = (ROOT / "dashboard/app/Tickets/Transkript/[ticketId]/transcript.css").read_text()


def test_dashboard_setting_is_additive_and_defaults_off():
    assert "always_transcript INTEGER NOT NULL DEFAULT 0" in PANELS
    assert "always_transcript INTEGER NOT NULL DEFAULT 0" in COG
    assert '"always_transcript": bool(row[3])' in ROUTES
    assert 'patchServer({ always_transcript: !server.always_transcript })' in DASHBOARD
    assert 'role="switch"' in DASHBOARD
    assert "Transcript immer ins Ticket-Log" in DASHBOARD
    assert '("db/ticket.db", "guild_configs", "always_transcript"' in SCHEMA


def test_delete_uses_english_components_v2_yes_no_prompt():
    assert "class DeleteTicketTranscriptChoice(LayoutView)" in COG
    assert 'label="Yes", emoji=TICK' in COG
    assert 'label="No", emoji=CROSS' in COG
    assert "Would you like to send the private transcript" in COG
    assert "ActionRow(yes, no)" in COG
    assert 'custom_id="c_transcript"' not in COG
    assert '@ticket.command(name="transcript"' not in COG


def test_snapshot_covers_complete_discord_message_shape_and_order():
    for field in (
        '"raw_content"', '"attachments"', '"embeds"', '"components"',
        '"stickers"', '"reactions"', '"reply"', '"edited_at"', '"pinned"',
    ):
        assert field in COG
    assert "history(limit=None, oldest_first=True)" in COG
    assert "ON CONFLICT(ticket_id) DO UPDATE" in COG
    assert "timedelta(days=90)" in COG
    assert "purge_expired_transcripts" in COG


def test_delivery_is_optional_for_dms_but_dashboard_log_can_force_snapshot():
    assert "if send_dms or always_log:" in COG
    assert "if always_log and link:" in COG
    assert "if send_dms and link:" in COG
    assert "recipients = [i.user]" in COG
    assert 'creator = i.guild.get_member(ticket["creator_id"])' in COG
    assert "transcript_dm_view" in COG
    assert "Open Transcript" in COG
    assert "/Tickets/Transkript/{ticket_id}" in COG


def test_transcript_requires_login_and_server_side_authorization():
    assert "getServerSession(authOptions)" in PAGE
    assert "redirect(`/api/auth/signin?callbackUrl=" in PAGE
    assert 'Authorization: `Bearer ${process.env.DASHBOARD_API_KEY || ""}`' in PAGE
    assert '"X-API-Key"' not in PAGE
    assert '@router.get("/transcript/{ticket_id}"' in ROUTES
    assert "actor_id in {int(row[\"creator_id\"]), int(row[\"closed_by_id\"])}" in ROUTES
    assert "member.guild_permissions.administrator" in ROUTES
    assert "member.guild_permissions.manage_channels" in ROUTES
    assert "This transcript has expired." in ROUTES


def test_page_recreates_discord_chat_and_message_features():
    for marker in (
        "discord-shell", "channel-rail", "discord-message", "discord-embed",
        "components-v2", "reactions", "attachment-image", "reply-line",
    ):
        assert marker in PAGE or marker in CSS
    assert "DiscordEmojiText" in PAGE
    assert "Read-only ticket transcript" in PAGE
    assert "--bg:#313338" in CSS
    assert "grid-template-columns:72px 240px" in CSS
