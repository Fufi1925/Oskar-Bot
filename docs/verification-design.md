# Verification dashboard and Discord defaults

The verification tab has a single header with setup, member and published-panel
status, five clearly separated sections, a responsive Discord preview and the
existing sticky save bar. Channel selection, three verified roles, unverified
role removal, Premium User Pull, server blacklist, custom messages, security
rules, channel cleanup, logs and per-member history actions remain available.
A failed initial load shows a retry action. User Pull cannot discard pending
configuration changes by being toggled during an unsaved edit.

Discord's standard panel, success messages and rejection notices use English.
Panels and responses are Components V2 with custom emoji markers. The dashboard
can load the English panel template as an unsaved draft, which must be saved and
published explicitly. Existing server-written texts remain editable and intact;
stock fields migrate independently instead of replacing the entire message.
Success messages only claim access to channels permitted by the member's roles.

After startup, the bot refreshes existing enabled, configured panel messages
once. It updates the stored message without posting additional panels. Missing
or inaccessible messages are skipped, and a missing configuration cannot grant
roles. This refresh uses the same renderer as preview, publishing and restore.
