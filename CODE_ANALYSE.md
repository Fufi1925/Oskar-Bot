# 🔍 Code-Analyse — Oskar-Bot (Branch `arena/019f9aa2-oskar-bot`)

> Stand: 26.07.2026 · Commit `f2b775c` · 893 Dateien · ~61.000 Zeilen Code · 46 MB

---

## 1. Was ist das Projekt?

Ein **Discord-Bot ("University Bot") + Web-Dashboard**, die zusammen in **einem einzigen Docker-Container** laufen und für Railway gebaut sind.

```
Railway Container (1 Port, 8080)
│
├── Python: discord.py Bot  ──► spawnt Thread ──► FastAPI (uvicorn, Port 8080)
│                                                  ├── /api/v1/*  → Bot-REST-API
│                                                  ├── /health    → Healthcheck
│                                                  └── /*         → Proxy zu Next.js
└── Node: Next.js Dashboard (Port 3000, standalone SSR)
```

`start.sh` startet Next.js im Hintergrund, wartet bis es antwortet, startet dann den Bot. Der Bot startet FastAPI in einem Daemon-Thread. FastAPI proxyt alles, was nicht `/api/v1` ist, an Next.js weiter — deshalb funktioniert NextAuth (`/api/auth/*`) über denselben Port.

---

## 2. Verzeichnisstruktur

| Pfad | Dateien | Zeilen | Inhalt |
|---|---|---|---|
| `bot/cogs/` | 151 | 39.882 | Alle Discord-Features (Commands, Events, Antinuke, Automod, Moderation) |
| `bot/games/` | 25 | 4.900 | 12+ Spiele (Chess, Battleship, Wordle, 2048, TicTacToe …) |
| `bot/api/` | 9 | 2.828 | FastAPI Backend (3 Router: bot, guilds, admin) |
| `bot/utils/` | 11 | 1.768 | Tools, Emoji-Registry, Emoji-Sync, Paginator, AI-Utils |
| `bot/core/` | 4 | 324 | Bot-Klasse, Custom Context, Cog-Basis |
| `dashboard/app/` | 38 | 5.076 | Next.js 14 App Router (23 Guild-Config-Seiten) |
| `dashboard/components/` | 30 | 4.469 | UI + Formulare pro Modul |
| `dashboard/lib/` | 6 | 1.121 | API-Client, NextAuth-Config, i18n (DE/EN) |

**Größte Dateien:** `leveling.py` (3.165), `logging.py` (2.999), `verification.py` (1.716), `api/routes/guilds.py` (1.632), `ai.py` (1.630).

---

## 3. Bot-Architektur

### Einstieg: `bot/university_bot.py` (461 Zeilen)
- Erstellt `universitybot()` Client, registriert Events direkt via `@client.event`
- Hardcodierte Channel-IDs für Stats/Logs (Zeile 53–55)
- Ein paar lose Commands direkt hier: `spotify`, `makeinvite`, `create_hook`, `delete_hook`, `list_hooks`, `reaction`
- `apply_nickname_rules()` — Prefix/Suffix-Nicknames nach Rollen (Dashboard-gesteuert)
- Startet FastAPI-Thread, dann `client.start(TOKEN)` mit Retry bei 429

### Bot-Klasse: `bot/core/universitybot.py`
- `commands.AutoShardedBot`, `shard_count=1`, alle Intents an
- **`get_prefix()`** öffnet bei **jeder Nachricht** bis zu 3× SQLite (`db/np.db` + `db/prefix.db`) → Performance-Hotspot
- Status-Rotation alle 30 s (5 Presence-Texte)
- `on_message` prüft Mention-Prefix-Response, `on_message_edit` invoked Commands erneut

### Cogs: `bot/cogs/__init__.py`
Ein einziges `setup()` mit **~140 manuellen `add_cog()`-Aufrufen**. Struktur:

| Gruppe | Anzahl | Beispiele |
|---|---|---|
| Commands | 68 | music, leveling, ticket, ai, giveaway, verification, minecraft, youtube |
| Antinuke | 17 | antiban, antikick, antichcr, antiwebhook, antiprune, antiguild … |
| Automod | 6 | antispam, anticaps, antilink, anti_invites, anti_mass_mention, anti_emoji_spam |
| Moderation | 15 | ban, kick, mute, warn, lock, hide, role, snipe, topcheck |
| Events | 12 | Errors, on_guild, greet2, mention, react, ai, stickymessage |
| Help-Cogs | 28 | `cogs/universitybot/*` — nur Hilfetexte pro Kategorie |

**Commands gesamt:** 114 `@commands.command` + 72 `@commands.hybrid_command` + 48 `@commands.group` + 1 `@app_commands.command`.

### Datenhaltung
**35 separate SQLite-Dateien** unter `bot/db/` — keine Migrationen, jede Datei legt ihre Tabellen mit `CREATE TABLE IF NOT EXISTS` selbst an.

Top-Nutzung: `automod.db` (56×), `anti.db` (41×), `leveling.db` (28×), `block.db` (22×), `welcome.db` (19×), `stickymessages.db` (19×).

Dazu ein paar JSON-Dateien (`jsondb/birthdays.json`, `logging_config.json`, `db/counting.json`).

---

## 4. API (FastAPI)

`bot/api/server.py` baut zwei Apps:
- **Haupt-App**: Logging-Middleware, SlowAPI-Ratelimit, CORS, `/health`, Catch-all-Proxy zu Next.js
- **Sub-App** unter `/api/v1` mit `Depends(verify_api_key)`

**Endpunkte:** 2 (bot) + 55 (guilds) + 8 (admin) = **65**

| Router | Zweck |
|---|---|
| `/bot/status`, `/bot/info` | Latenz, Guild-/User-Count, Shards |
| `/guilds/…` | Pro Modul GET+PATCH: automod, tickets, leveling, welcome, antinuke, verification, autorole, logging, j2c, joindm, customroles, reactionroles, vanityroles, invites, noprefix, nickname, extra-settings … |
| `/admin/…` | stats, config (maintenance/notification), features (50 Flags), member-action, quick-action |

Der Proxy in `server.py` behandelt `Set-Cookie` korrekt über `resp.headers.raw` — das war ein bewusster Fix gegen NextAuth-Loginschleifen (steht so im Kommentar).

---

## 5. Dashboard (Next.js 14)

- **App Router**, `output: 'standalone'`, Tailwind, Radix, lucide-react, sonner
- **NextAuth** mit Discord-Provider, Scope `identify guilds`, JWT-Session 30 Tage
- **i18n** Deutsch/Englisch über eigenen `LanguageContext` + `dom-translations.ts` (479 Zeilen DOM-Text-Ersetzung)
- **23 Guild-Seiten** (antinuke, automod, tickets, leveling, welcome, logging, verification, j2c, invites, autorole, reactionroles, vanityroles, customroles, joindm, noprefix, nickname, tracking, autoreact, invcrole, admin-dashboard, settings, leaderboard, overview)
- Admin-Panel (`/dashboard/admin`) mit Tabs: members / channels / server / scans → ruft `/admin/quick-action`

---

## 6. 🔴 Kritische Befunde

### 6.1 API-Key liegt im Browser
`dashboard/lib/api.ts` nutzt clientseitig `NEXT_PUBLIC_DASHBOARD_API_KEY`. `start.sh` kopiert `DASHBOARD_API_KEY` genau dorthin. **27 Client-Komponenten** rufen darüber die API auf → der Key steht im JS-Bundle und ist für jeden Besucher lesbar.

### 6.2 Keine Autorisierung pro Guild
- `bot/api/routes/guilds.py`: **kein einziger** Check, ob der Aufrufer Rechte auf der Guild hat. Wer den Key hat, kann jede Guild konfigurieren.
- `verify_api_key()` lässt **alle** `127.0.0.1`-Requests ohne Key durch — und der Next.js-Proxy kommt genau von dort.
- **22 von 23** Guild-Seiten rufen kein `getServerSession()` auf. Nur `guilds/page.tsx` und `admin/page.tsx` prüfen die Session.
- Keine `middleware.ts` vorhanden.

**Konsequenz:** `/dashboard/guild/<beliebige-ID>/automod` ist ohne Prüfung erreichbar, sobald man eingeloggt ist (Layout lädt nur die Guild-Details, prüft aber keine Berechtigung).

### 6.3 `eval()` auf User-Input
`cogs/commands/calc.py:92` → `eval(expression)` aus einem Discord-Button. Die Eingabe kommt zwar nur aus festen Buttons (0-9, +-*/), aber `eval` bleibt unnötig riskant. Zusätzlich `eval()` in `autorole.py` (4×) auf DB-Werte.

### 6.4 Hardcodierter API-Key
`cogs/commands/fun.py:27` → Giphy-Key `y3KcqQTdiS0RYcpNJrWn8hFGglKqX4is` im Klartext im Repo.

### 6.5 `asyncio.run()` beim Import
`utils/Tools.py:34` ruft `asyncio.run(setup_db())` auf Modulebene. Wird das Modul jemals aus einem laufenden Event-Loop importiert, gibt es `RuntimeError: asyncio.run() cannot be called from a running event loop`.

---

## 7. 🟠 Deployment-Blocker

### 7.1 Pillow fehlt in `requirements.txt`
Zeile 34: `# pillow==11.0.0` — **auskommentiert**. Aber **14 Dateien** importieren PIL **hart ohne try/except**:
`ai.py`, `blackjack.py`, `minecraft.py`, `music.py`, `owner.py`, `slots.py`, `status.py`, `verification.py`, `games/battleship.py`, `country_guess.py`, `twenty_48.py`, `typeracer.py`, `wordle.py`.

→ Läuft aktuell nur, weil `Augmentor` Pillow transitiv nachzieht. Sehr fragil.

### 7.2 Weitere fehlende Pakete
| Import | Paket | Wo |
|---|---|---|
| `pytz` | `pytz` | 19 Dateien (alle Antinuke-Cogs!) |
| `aiofiles` | `aiofiles` | mehrere Cogs |
| `google.generativeai` | `google-generativeai` | `ai.py` (immerhin mit try/except) |
| `prodia` | `prodia` | `imagine.py` |
| `deep_translator` | ist drin ✅ | |

### 7.3 Fehlende Dateien/Ordner
| Erwartet | Status | Folge |
|---|---|---|
| `bot/db/` (Ordner für 35 DBs) | existiert, aber leer | Wird nirgends per `os.makedirs` angelegt → erster Start kann scheitern |
| `bot/instructions/` | **fehlt** | `config_loader.load_instructions()` crasht |
| `bot/channels.json` | **fehlt** | `load_active_channels()` gibt `UnboundLocalError` |
| `bot/ignore.json` | fehlt | wird zur Laufzeit erzeugt (ok) |
| `bot/jsondb/joindm_messages.json` | fehlt | ggf. Laufzeitfehler |
| `bot/db/ticket.db-journal` | eingecheckt ⚠️ | verwaistes SQLite-Journal, sollte weg |

### 7.4 requirements.txt ist unsauber
Enthält **Stdlib-Module als Pakete**: `asyncio`, `typing`, `datetime`, `pathlib`, `collection` (Tippfehler für `collections`). Dazu doppelt: `discord` + `discord.py` + `discord.ui`, `flask` + `Quart` (beide ungenutzt), `requests` + `Requests`.

### 7.5 Dockerfile
`apt-get install nodejs` in Stage 2 zieht Debian-Bookworm-Node **18.19** — passt zufällig zu Next 14, ist aber nicht gepinnt. Der Build läuft in Stage 1 mit `node:18-alpine`, die Runtime mit einer anderen Node-Version.

---

## 8. 🟡 Code-Qualität

| Befund | Details |
|---|---|
| **Obfuskierter Code** | 4 Dateien im „space-before-paren"-Stil (`func (arg ,arg )`): `leveling.py` (1.175 Stellen), `verification.py` (580), `ai.py` (446), `booster.py` (264). Sieht nach durchgelaufenem Obfuscator/Deobfuscator aus — sehr schlecht wartbar. |
| **796 except-Blöcke** | davon **70 bare `except:`** und 326 `except Exception` — Fehler werden großflächig verschluckt |
| **366× `aiosqlite.connect()`** | Kein Connection-Pooling im Bot (nur die API hat `db_manager`). Jeder Aufruf öffnet die Datei neu. |
| **26 `on_message`-Listener** | Jede Nachricht durchläuft 26 Cogs + `get_prefix` mit 3 DB-Öffnungen |
| **Keine Tests, keine CI** | Kein `tests/`, kein `.github/workflows/` |
| **Tote Dateien** | `help_backup.txt`, `mentionold.txt`, `leveling_original.py`, `map.py` (auskommentiert), `imagine.py`, `msgpack.py`, `cogs/antinuke/extra events (unused)/` (5 Dateien) |
| **Branding inkonsistent** | „University Bot", „universitybot X", „Oskar-Bot", „CODEX"-ASCII-Art, „ZYROX"-ASCII-Art in `bot/README.md` — teils mit kaputten Ersetzungen wie `https://youtube.com/@University BotDevs` (Leerzeichen in URL) |
| **50 Admin-Feature-Flags** | `ADMIN_FEATURE_DEFAULTS` in `admin.py` — **keiner** davon wird irgendwo ausgewertet. Reine Attrappe (jeweils genau 1 Treffer im gesamten Code = die Definition selbst). |
| **`maintenance_mode`** | wird gespeichert und angezeigt, aber **nirgends durchgesetzt** |
| **Doppelte Endpunkte** | `/guilds/{id}/welcome` (Zeile 393 + 694) und `/guilds/{id}/autoreact` (1159 + 1241) je zweimal definiert — die zweite Definition gewinnt, die erste ist toter Code |
| **`on_command_completion`** | Baut `discord.Webhook.from_url(CMD_WEBHOOK_URL)` ohne Null-Check. Ist die Env-Var leer → Exception bei **jedem** Command |
| **SQL via f-String** | 15 Stellen. Meist unkritisch (interne Werte), aber `invites_{guild_id}` als Tabellenname ist ein Anti-Pattern |
| **Hardcodierte IDs** | 41× `1279464563150032991`, 21× `1396114795102470196`, Stats-Channels, Log-Channel, Bot-Invite mit `client_id=1530349205372145715` |
| **Lavalink-Defaults** | `music.py:419` hat als Default-Passwort `https://dsc.gg/ajidevserver` — Reste vom Original-Repo |
| **`ai_utils.py:36`** | `api_key="nah-ha"` — Platzhalter, der Groq-Endpoint würde 401 liefern |

---

## 9. Git-Historie

19 Commits. Basis (`main`) enthält nur eine `README.md` — der komplette Code kam in `c53e7fa "Restore bot codebase and fix build errors"` als Import rein.

```
e3d2964 Initial commit                          ← main (nur README)
c53e7fa Restore bot codebase and fix build errors  ← 893 Dateien auf einmal
549eae9 Fix API rate limiter dependency
518f06f Stabilize Discord dashboard sessions
aba47f1 Preserve NextAuth cookies through proxy
7d81893 Fix bot command loading and music playback
27f148a Apply language switcher across dashboard
25eae10 Switch dashboard accent colors to dark blue
cdccad3 Add no-prefix and nickname dashboard tabs
61bfb03 Show no-prefix and nickname in dashboard sidebar
103ca96 Add premium community server template command
0430513 Replace start template with dashboard admin features
b71bc4d Update founder information and invite link
bf5dfbb Expand admin dashboard to twenty features
4d81f96 Add fifty global admin panel functions
9c8c353 Simplify admin panel with moderation action tabs
5455422 Add tabbed admin action tools
02147c8 Fix admin actions and simplify target selection
f2b775c Fix moderation actions and remove role nickname admin tools  ← HEAD
```

Klares Muster: erst Infrastruktur-Fixes (Sessions, Proxy, Cookies), dann Feature-Ausbau am Admin-Panel.

---

## 10. Priorisierte Aufgabenliste

### 🔴 Sicherheit (sofort)
1. `NEXT_PUBLIC_DASHBOARD_API_KEY` entfernen → alle Client-Calls über Next.js **Route Handler** proxien, Key bleibt serverseitig
2. Guild-Autorisierung einbauen: `middleware.ts` + serverseitiger Check „hat User MANAGE_GUILD auf dieser Guild?" vor jedem Guild-Endpoint
3. `verify_api_key()` härten — localhost-Bypass entfernen oder auf einen internen Shared-Secret-Header umstellen
4. Giphy-Key aus `fun.py` in `.env` verschieben (und den alten Key rotieren!)
5. `eval()` in `calc.py` durch `ast.literal_eval` oder einen sicheren Expression-Parser ersetzen

### 🟠 Deployment stabilisieren
6. `requirements.txt` aufräumen: `pillow`, `pytz`, `aiofiles`, `google-generativeai`, `pydantic` ergänzen; Stdlib-Einträge und Dubletten raus; Versionen pinnen
7. `os.makedirs("db", exist_ok=True)` beim Start; `instructions/` + `channels.json` anlegen oder die Loader defensiv machen
8. `CMD_WEBHOOK_URL`-Null-Check in `on_command_completion`
9. `bot/db/ticket.db-journal` löschen und `*.db-journal` in `.gitignore`
10. Node-Version im Dockerfile pinnen (Stage 1 und 2 angleichen)

### 🟡 Aufräumen
11. Tote Dateien löschen (`*_backup.txt`, `*old.txt`, `leveling_original.py`, `extra events (unused)/`)
12. Doppelte Endpunkte in `guilds.py` zusammenführen (welcome, autoreact)
13. Die 50 Fake-Feature-Flags entweder implementieren oder entfernen
14. Branding vereinheitlichen (ein Name, keine kaputten URLs mit Leerzeichen)
15. Obfuskierte Dateien reformatieren (`black`/`ruff format` auf leveling/verification/ai/booster)
16. Connection-Pooling im Bot (den vorhandenen `db_manager` auch dort nutzen) — spart bei 366 Öffnungen viel I/O
17. `get_prefix()` cachen (In-Memory-Dict pro Guild statt 3 DB-Öffnungen pro Nachricht)

### 🟢 Optional
18. Tests + GitHub-Actions-Workflow (mindestens `python -m compileall` + `next build`)
19. Migration von 35 SQLite-Dateien auf eine DB mit Schema-Versionierung
20. `maintenance_mode` tatsächlich durchsetzen (Bot-Commands blocken + Dashboard-Banner)

---

## 11. Positives

- Der **Proxy-Ansatz** (ein Port für Bot-API + Dashboard) ist elegant gelöst, inkl. korrektem `Set-Cookie`-Handling
- `start.sh` ist defensiv: wartet auf Dashboard-Readiness, zeigt Logs bei Fehlschlag, hat Cleanup-Trap und Auto-Restart
- FastAPI mit **Pydantic-Schemas** (50 Modelle) und OpenAPI-Docs
- Das Admin-`quick-action`-Endpoint hat **saubere Permission-Checks** gegen Discord (Rollenhierarchie, Owner-Schutz, Bot-Selbstschutz) — deutlich besser als der Rest der API
- Zweisprachiges Dashboard (DE/EN) mit ordentlichem Context
- Konsequente Modularisierung in Cogs
- `.env.example` ist ausführlich dokumentiert, `RAILWAY_DEPLOYMENT.md` ist eine brauchbare Schritt-für-Schritt-Anleitung
