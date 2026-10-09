# Reusable message codes

The **Eigene Nachricht / Custom message** editor saves message designs as eight-digit
codes. Codes have no expiration or usage limit, including previously consumed
legacy codes. Importing loads a snapshot into the editor and does not send a message.

Anyone with a code and the required dashboard access can import it into another
server. Cross-server imports clear the source channel and select the main bot;
choose a destination channel before sending. Same-server imports retain delivery
settings. Importing never changes the saved design.

The server's code library lists designs created by every user on that server,
with copy, preview, and editor actions. It is paginated and supports refresh.
Viewing previews preserves the current draft. Lists, previews and loading designs require access
to that server; creating codes and sending messages retain the
existing write permissions. A server cannot enumerate another server's library.

Designs stay in the existing `bot/db/compose_codes.db`. The legacy usage fields now
record only the latest import; they do not invalidate a code. Preserve the database
volume when deploying. The shared Discord-style renderer displays the editor and
stored-code previews, including static/animated custom emojis and formatting.

Validation: run `python -m pytest -q bot/tests/test_compose_codes_and_guild_emojis.py`
and `python bot/tests/test_compose.py` from the repository root. The announcement and
dashboard emoji scripts also cover the shared renderer. Check TypeScript and run
the dashboard production build from `dashboard/`.
