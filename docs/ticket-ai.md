# Ticket AI workspace

The guild ticket page now has **Ticket panels** and **Ticket AI** tabs. The latter
is available to every server with Premium access. The old admin rollout list
no longer restricts access. Existing Premium expiry and frozen-settings rules
still apply; the server must enable the assistant and its ticket categories.
A direct link can use `/dashboard/guild/<id>/tickets#ticket-ai`.

- **Chat:** Remember knowledge stores the administrator's exact statement as a
  shared guild fact. Test reply uses the same grounded answer generation as live
  tickets. A question does not become knowledge. Chats belong to the signed-in
  account, retain at most 60 messages and expire after 30 days on access.
  Local topic matching recognizes DE/EN price paraphrases and common typos.
  Related facts trigger a red, localized review dialog before any write. Keeping
  old knowledge leaves facts untouched; replacing it updates the related memory
  entries and matching document lines in one transaction. Content hashes prevent
  an old confirmation from overwriting a concurrent update. No AI call is used
  to detect these conflicts.
- **Saved knowledge:** Review, search, edit or delete individual entries. Up to
  200 facts and 100 KB of fact content are allowed. The separate TXT document is
  limited to 100 KB. Replacing it does not erase facts taught in chat.
- **Read server:** Create a local review draft from server structure, redacted
  configuration and readable owner/administrator messages from the past 30 days.
  Ticket channels, member messages, backups and binary data are excluded. No provider call is made.
  Four concurrent readers check the latest 300 messages per channel within the
  past 30 days and up to 50 archived threads per parent. Message retrieval gets
  10 seconds per channel; the whole collection gets 90 seconds. Configuration
  reads omit BLOB values at SQL level, use at most 30 rows per table and reserve
  separate byte budgets so backups/settings cannot starve channel messages.
  Cached previews from older scans also have binary repr lines removed.
  Archive discovery, configuration export, individual channel history and the
  overall read have time limits. Partial scans report warnings rather than
  claiming full coverage. Explicit acceptance saves a reviewed document.
- **Ticket replies:** Category switches and instructions display their parent
  panel. The assistant uses imported documents and manually taught facts,
  stops when a team member claims/closes a ticket and retains the existing
  answer limits and escalation rules. Up to three recent questions from the same
  creator can be read temporarily for short follow-ups, with a two-second
  timeout; other members' messages are ignored. Ticket conversations are not stored by AI.

Teaching and reading require no provider key. Generating answers uses the existing
server-only `GROQ_TICKET_AI_KEY` / `GROQ_TICKET_AI_MODEL`. Only the current question,
recent personal questions for dashboard/ticket follow-ups, matching approved knowledge
excerpts and category rules are sent. Provider failures are distinguished from
missing knowledge in the coaching chat. Server data is never used as a system
instruction, and the provider must explicitly return `supported: true`.

New tables `ticket_ai_memories` and `ticket_ai_coaching` are migrated automatically
in `db/ticket.db`. Personal chats are excluded from configuration-only exports,
included in account exports and removed by account erasure. Shared server facts
have no account attribution and can be removed from the workspace. Existing TXT
knowledge, settings and per-category enablement are retained.

Tests: from `bot`, run `python tests/test_ticket_ai_workspace.py`,
`python tests/test_ticket_ai_pilot.py` and `python tests/test_ticket_workflow.py`.
From `dashboard`, run the TypeScript check and production build.
