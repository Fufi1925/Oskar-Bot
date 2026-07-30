# Security & Architecture Notes

> **Eine Lücke gefunden?** Bitte nicht als öffentliches Issue —
> der Meldeweg steht in [.github/SECURITY.md](.github/SECURITY.md).
>
> Diese Datei hier beschreibt, *wie* die Sicherheitsmechanismen
> funktionieren.

Wie Authentifizierung, Autorisierung und die globalen Feature-Flags in diesem
Projekt funktionieren.

---

## 1. Wer darf was?

| Ebene | Prüfung | Ort |
|---|---|---|
| Eingeloggt? | NextAuth-Session | `dashboard/middleware.ts` |
| Darf Server X verwalten? | Discord-Rechte des Nutzers (`Manage Server` oder Owner) | `dashboard/lib/guild-auth.ts` |
| Globaler Admin? | `ADMIN_IDS` | `dashboard/lib/guild-auth.ts` |
| Darf die Bot-API angesprochen werden? | `Authorization: Bearer <DASHBOARD_API_KEY>` | `bot/api/dependencies.py` |

---

## 2. Der API-Key verlässt nie den Server

**Problem vorher:** `lib/api.ts` las clientseitig `NEXT_PUBLIC_DASHBOARD_API_KEY`.
Next.js ersetzt `NEXT_PUBLIC_*` beim Build durch den Literalwert — der Key stand
also im ausgelieferten JavaScript und war für jeden Besucher lesbar. Damit
konnte jeder die komplette Bot-API ansprechen und **jeden** Server konfigurieren.

**Jetzt:**

```
Browser ──► /api/bot/guilds/<id>/automod ──► FastAPI /api/v1/guilds/<id>/automod
            (nur Session-Cookie)              (Bearer DASHBOARD_API_KEY)
                     │
                     └─ app/api/bot/[...path]/route.ts
                        1. Session prüfen
                        2. Discord fragen: darf dieser Nutzer diesen Server verwalten?
                        3. erst dann weiterleiten, Key serverseitig anhängen
```

* Server Components rufen FastAPI weiterhin direkt auf (der Key ist dort ohnehin verfügbar).
* Client Components gehen über den Proxy.
* `start.sh` löscht `NEXT_PUBLIC_DASHBOARD_API_KEY` aktiv, falls jemand sie doch setzt.
* Der `ARG`/`ENV`-Eintrag im Dockerfile wurde entfernt.

**Nachweis:** Ein Testbuild mit gesetztem Key findet ihn in `.next/static` nicht mehr;
mit dem alten Code tauchte er in mehreren Client-Chunks auf.

---

## 3. Guild-Autorisierung

Vorher prüften **22 von 23** Guild-Seiten gar nichts — wer eingeloggt war,
konnte `/dashboard/guild/<beliebige-id>/automod` öffnen.

Drei Ebenen greifen jetzt:

1. **`middleware.ts`** — alles unter `/dashboard` und `/api/bot` verlangt eine Session.
2. **`layout.tsx` der Guild-Routen** — ruft `verifyGuildAccess(guildId)` auf und zeigt
   sonst „Access Denied". Das gilt automatisch für alle Unterseiten.
3. **BFF-Proxy** — prüft jede einzelne API-Anfrage nochmal, damit auch direkte
   `fetch`-Aufrufe abgesichert sind.

`verifyGuildAccess` fragt `https://discord.com/api/users/@me/guilds` mit dem
OAuth-Token des Nutzers ab und verlangt `ADMINISTRATOR`, `MANAGE_GUILD` oder
Owner-Status. Die Antwort wird 60 Sekunden pro Token gecacht (Discord erlaubt
dort nur ~1 Request/Sekunde).

---

## 4. `verify_api_key()` — kein localhost-Bypass mehr

Vorher galt jede Anfrage von `127.0.0.1` als vertrauenswürdig. Da der Next.js-Proxy
genau von dort kommt, hatte damit **jeder Besucher** vollen API-Zugriff.

Jetzt gilt: Ist `DASHBOARD_API_KEY` gesetzt, wird er immer verlangt — unabhängig
von der Herkunft. Der Vergleich läuft über `hmac.compare_digest` (timing-safe).
Ohne konfigurierten Key läuft nur die lokale Entwicklung; mit
`ALLOW_KEYLESS_API=false` lässt sich auch das abschalten.

---

## 5. Globale Feature-Flags

Alle 50 Flags sind implementiert und wirken sich real aus. Registry und Metadaten:
`bot/utils/feature_flags.py`.

| Modul | Aufgabe |
|---|---|
| `feature_flags.py` | Registry, Persistenz, Cache, Dependencies, Rollouts |
| `feature_gates.py` | Command-Gate (Lockdown, Freeze, Owner-Only, Blacklist, Premium, Beta) |
| `feature_services.py` | Hintergrund-Loops (Health, Backups, Cleanup, Announcements, Watchdog) |
| `feature_audit.py` | Audit-Log, Notification-History, Approval-Queue, Timeline |
| `feature_reports.py` | Analytics (Security-Score, Risk-Scans, Invites, Retention …) |
| `cogs/events/feature_enforcement.py` | Event-Handler (Guild-Guard, Voice, Cache-Warmup) |

### Eigenschaften

* **Sofort wirksam** — kein Neustart nötig, jede Loop-Iteration liest den Flag neu.
* **Dependencies** — `music_node_failover` ist inaktiv, solange `lavalink_health_monitor` aus ist.
* **Prozentuale Rollouts** — `is_enabled_for_guild()` verteilt stabil per `guild_id % 100`.
* **Owner-Bypass** — die Safety-Flags sperren nie die Bot-Owner aus.

### Wichtige Endpunkte

```
GET   /api/v1/admin/features            flache key -> bool Map
GET   /api/v1/admin/features/detail     inkl. Kategorie, Beschreibung, Effekt, Rollout
PATCH /api/v1/admin/features            Flags umschalten
PATCH /api/v1/admin/features/{key}/rollout
GET   /api/v1/admin/health              Monitoring-Ergebnisse
GET   /api/v1/admin/logs                letzte Warnungen/Fehler
GET   /api/v1/admin/metrics             API-Performance, Command-Fehler
GET   /api/v1/admin/audit               Cross-Guild Audit-Log
GET   /api/v1/admin/timeline            Incident-Timeline
GET   /api/v1/admin/reports/{name}      Analytics-Reports
GET   /api/v1/admin/approvals           offene Freigaben
```

Reports: `security-score`, `automod-recommendations`, `staff-permissions`,
`role-risk`, `channel-risk`, `webhook-risk`, `ticket-load`, `invite-growth`,
`member-retention`, `voice-analytics`.

### `maintenance_mode`

War vorher ein reiner Anzeigewert. Jetzt setzt das Umschalten zusätzlich
`global_command_freeze` — Commands sind für alle außer den Ownern gesperrt, und
das Dashboard zeigt (sofern `maintenance_banner` an ist) ein Banner.

---

## 6. Weitere Härtungen

| Was | Vorher | Jetzt |
|---|---|---|
| `calc.py` | `eval(expression)` | AST-Parser mit Operator-Whitelist, Exponenten-Limit |
| `fun.py` | Giphy-Key im Quelltext | `GIPHY_API_KEY` aus der Umgebung |
| `Tools.py` | `asyncio.run()` beim Import | Fällt auf `sqlite3` zurück, wenn ein Loop läuft |
| `on_command_completion` | Crash ohne `CMD_WEBHOOK_URL` | Wird übersprungen |
| `config_loader` | Crash ohne `instructions/` bzw. `channels.json` | Defaults statt Exception |
| Prefix-Lookup | 3 DB-Öffnungen pro Nachricht | In-Memory-Cache mit Invalidierung |

---

## 7. Wenn der Key schon geleakt ist

Der alte Build hat den Key ausgeliefert. Nach dem Deploy dieser Version:

1. **`DASHBOARD_API_KEY` in Railway neu setzen** (neuer Zufallswert).
2. `NEXTAUTH_SECRET` separat setzen, falls es bisher vom API-Key abgeleitet wurde.
3. Den alten Giphy-Key (`y3Kc…`) im Giphy-Dashboard widerrufen.
4. Optional `force_dashboard_reauth` einschalten, um alte Sessions zu entwerten.
