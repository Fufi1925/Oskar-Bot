# Security & Architecture Notes

> **Eine Lücke gefunden?** Bitte nicht als öffentliches Issue —
> der Meldeweg steht in [.github/SECURITY.md](.github/SECURITY.md).
>
> Diese Datei hier beschreibt, *wie* die Sicherheitsmechanismen
> funktionieren, und was noch offen ist.

Stand: September 2026. Wie Authentifizierung, Autorisierung, die
globalen Feature-Flags und die Firewall zusammenhängen.

---

## 1. Wer darf was?

| Ebene | Prüfung | Ort |
|---|---|---|
| Eingeloggt? | NextAuth-Sitzung | `dashboard/middleware.ts` |
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
* `start.sh` löscht `NEXT_PUBLIC_DASHBOARD_API_KEY` aktiv, falls jemand sie doch setzt —
  und sagt im Log, dass es passiert ist.
* Der `ARG`/`ENV`-Eintrag im Dockerfile ist entfernt.

**Nachweis:** Ein Testbuild mit gesetztem Key findet ihn in `.next/static` nicht mehr;
mit dem alten Code tauchte er in mehreren Client-Chunks auf.

---

## 3. Guild-Autorisierung

Früher prüften fast alle Guild-Seiten gar nichts — wer eingeloggt war,
konnte `/dashboard/guild/<beliebige-id>/automod` öffnen. Heute sind es
53 Seiten unter `app/dashboard/guild/[guildId]/`, und drei Ebenen greifen:

1. **`middleware.ts`** — alles unter `/dashboard` und `/api/bot` verlangt eine Session.
2. **`layout.tsx` der Guild-Routen** — ruft `verifyGuildAccess(guildId)` auf und zeigt
   sonst „Access Denied". Das gilt automatisch für alle Unterseiten.
3. **BFF-Proxy** — prüft **jede einzelne** API-Anfrage nochmal, damit auch direkte
   `fetch`-Aufrufe abgesichert sind.

`verifyGuildAccess` fragt `https://discord.com/api/users/@me/guilds` mit dem
OAuth-Token des Nutzers ab und verlangt `ADMINISTRATOR`, `MANAGE_GUILD` oder
Owner-Status. Die Antwort wird 60 Sekunden pro Token gecacht (Discord erlaubt
dort nur etwa einen Request pro Sekunde).

Ohne `ADMIN_IDS` oder eine eingetragene Team-Rolle ist der Admin-Bereich
nicht erreichbar; der Proxy antwortet dort mit 404 statt 403, damit sich
nicht abfragen lässt, welche Bereiche es gibt.

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

Alle 50 Flags sind registriert und wirken sich real aus — ein Flag, das nur
in einer Tabelle steht, ist eine Anzeige, keine Steuerung. Registry und
Metadaten: `bot/utils/feature_flags.py`.

| Modul | Aufgabe |
|---|---|
| `feature_flags.py` | Registry, Persistenz, Cache, Dependencies, Rollouts |
| `feature_gates.py` | Command-Gate (Lockdown, Freeze, Owner-Only, Blacklist, Premium, Beta) |
| `feature_services.py` | Hintergrund-Loops (Health, Backups, Cleanup, Announcements, Watchdog) |
| `feature_audit.py` | Audit-Log, Notification-History, Approval-Queue, Timeline |
| `feature_reports.py` | Analytics (Security-Score, Risk-Scans, Invites, Retention …) |
| `cogs/events/feature_enforcement.py` | Event-Handler (Guild-Guard, Voice, Cache-Warmup) |

### Eigenschaften

* **Sofort wirksam** — kein Neustart nötig, jede Loop-Iteration liest das Flag neu.
* **Dependencies** — `music_node_failover` ist inaktiv, solange `lavalink_health_monitor` aus ist.
* **Prozentuale Rollouts** — `is_enabled_for_guild()` verteilt stabil über `guild_id % 100`.
* **Owner-Bypass** — die Safety-Flags sperren nie die Bot-Owner aus.

### Wichtige Endpunkte

```
GET   /api/v1/admin/features            flache key -> bool Karte
GET   /api/v1/admin/features/detail     inkl. Kategorie, Beschreibung, Effekt, Rollout
PATCH /api/v1/admin/features            Flags umschalten
PATCH /api/v1/admin/features/{key}/rollout
GET   /api/v1/admin/health              Monitoring-Ergebnisse
GET   /api/v1/admin/logs                letzte Warnungen und Fehler
GET   /api/v1/admin/metrics             API-Performance, Command-Fehler
GET   /api/v1/admin/audit               Guild-übergreifendes Audit-Log
GET   /api/v1/admin/timeline            Incident-Timeline
GET   /api/v1/admin/reports/{name}      Analytics-Berichte
GET   /api/v1/admin/approvals           offene Freigaben
```

Berichte: `security-score`, `automod-recommendations`, `staff-permissions`,
`role-risk`, `channel-risk`, `webhook-risk`, `ticket-load`, `invite-growth`,
`member-retention`, `voice-analytics`.

### `maintenance_mode`

War früher ein reiner Anzeigewert. Jetzt setzt das Umschalten zusätzlich
`global_command_freeze` — Befehle sind für alle außer den Ownern gesperrt,
und das Dashboard zeigt (wenn `maintenance_banner` an ist) ein Banner.

---

## 6. Anwendungs-Firewall

`bot/utils/firewall.py` und der Admin-Reiter „Firewall" bilden eine eigene
Schicht vor den Routen. Grundsätze, die im Code nachprüfbar sind:

* **Nur beobachten zuerst.** Neue Regeln greifen nicht sofort; ein
  Ereignis wird erst gezählt, und die Regel muss ausdrücklich scharf
  geschaltet werden.
* **Rückgängig.** Jede Sperrung ist im Audit-Protokoll mit Grund und
  Zeitstempel, und es gibt einen Rücknahme-Weg. Ein falsch gesperrter
  Besucher ist der teure Fehler, nicht ein zu später.
* **Ausnahmen für eigene Wege.** Der Dashboard-Proxy und die
  Status-Endpunkte sind freigegeben — sonst sperrt sich der Bot selbst
  aus, während er auf eine Antwort wartet.
* **Vertrauenswürdige Netze.** `TRUSTED_BOTS` und die Liste vertrauter
  Bots bleiben davon getrennt; die Firewall ersetzt sie nicht.

Der Block-Bildschirm (`/firewall-blocked`) nennt keinen Grund im Detail —
eine Meldung, die erklärt, welche Regel traf, ist eine Einladung zum
Austesten.

---

## 7. Der Admin-Bereich filtert sichtbar *und* prüft

Ein Reiter, der im Frontend angezeigt wird, aber nicht darf, erzeugt
Fehlermeldungen; ein Reiter, der versteckt ist, aber nicht prüft, ist
gefährlich. Deshalb gilt beides:

* **Kein Rechteeintrag = kein Reiter.** `TAB_PERMISSION` in
  `admin-content.tsx` ist absichtlich „fail closed": ein neuer Reiter
  ohne Eintrag ist für Team-Rollen unsichtbar, nicht sichtbar.
* **Der Proxy prüft dieselbe Schwelle.** `app/api/bot/[...path]/route.ts`
  entscheidet pro Bereich (`accounts`, `keys`, `revoke` …) und
  verweigert mit 403, unabhängig davon, was im Browser läuft.

Ein Reiter, der nur dem Bot-Inhaber gehört (Ideen, vertraute Bots), ist das
im Code ausdrücklich festgehalten — nicht ein vergessener Eintrag.

---

## 8. Weitere Härtungen

| Was | Vorher | Jetzt |
|---|---|---|
| `calc.py` | `eval(expression)` | AST-Parser mit Operator-Whitelist, Exponenten-Limit |
| `fun.py` | Giphy-Key im Quelltext | `GIPHY_API_KEY` aus der Umgebung |
| `Tools.py` | `asyncio.run()` beim Import | Fällt auf `sqlite3` zurück, wenn ein Loop läuft |
| `on_command_completion` | Crash ohne `CMD_WEBHOOK_URL` | Wird übersprungen |
| `config_loader` | Crash ohne `instructions/` bzw. `channels.json` | Defaults statt Exception |
| Prefix-Lookup | 3 DB-Öffnungen pro Nachricht | In-Memory-Cache mit Invalidierung |
| Ticket-Rückfragen | IP im Klartext | `homepage_visitors.py` speichert nur ein HMAC-Abbild, 10 Minuten entprellt, Länderzahl einen Tag |
| Sicherungen | — | `bot/utils/guild_backup.py` legt Inhalte komprimiert in einer eigenen DB ab; Kennungen sind zufällig und eindeutig |

---

## 9. Isolierte Bereiche

`/louckup` und `/lbost-shop` sind eigene FastAPI-Anwendungen mit **eigener
Sitzung, eigenem Login-Pfad und eigener Datenbankdatei**. Sie sitzen zwar im
selben Container unter demselben Hostnamen, teilen aber kein Cookie:
`LOUCKUP_COOKIE_PATH` und `LBOST_SHOP_COOKIE_PATH` sind auf den Pfad
beschränkt, damit eine Sitzung aus einem dieser Bereiche nicht automatisch
im Dashboard gilt — und umgekehrt.

Bot-Token, die in diesen Bereichen hinterlegt werden, liegen verschlüsselt
in der Datenbank (`token_cipher`); der Schlüssel kommt aus der Umgebung und
steht nicht in der Datei. Das ist kein Schutz gegen jemanden, der den
Container *und* die Umgebung hat — es verhindert den häufigeren Fall einer
kopierten Datenbankdatei.

---

## 10. Offene Punkte

Nichts hier ist behauptet; jedes ist im Code nachsehbar.

1. **`eval()` in `bot/cogs/commands/autorole.py`** — vier Stellen
   (`humans`, `bots`, jeweils zwei Wege). Der Weg dorthin führt über die
   Konfigurationsübernahme: Werte werden beim Import nicht geprüft, und
   beim nächsten `>autorole humans add` läuft `eval()` über den
   gespeicherten Text. Das ist Codeausführung mit den Rechten des Bots.
   Der Baustein aus `calc.py` (AST-Whitelist) wäre die Vorlage.
2. **Zugangsdaten-Rotation.** Ein Bot-Token, ein Client-Secret und ein
   API-Key standen in einer Chat-Unterhaltung. Solange sie nicht in
   Railway gedreht sind, sind sie geleakt — die Dateien im Repo sind
   sauber, das Problem ist der Kanal. `NEXT_PUBLIC_DASHBOARD_API_KEY`
   sollte zusätzlich aus der Variablenliste verschwinden.
3. **Abhängigkeiten.** Dependabot meldet offene Punkte (Zahl im Reiter
   „Security" des Repos, nicht hier — die Zahl ändert sich wöchentlich und
   wäre in einer Datei sofort falsch).
4. **Impressum.** `IMPRINT_NAME`, `IMPRINT_ADDRESS` und `IMPRINT_EMAIL`
   sind teils belegt, teils leer; für eine öffentliche Seite in
   Deutschland ist das kein Schönheitsfehler.
5. **Live-Tests gegen Discord.** Die Prüfläufe in `bot/tests/` laufen ohne
   Netzwerk. Was sie nicht zeigen können: ob ein Discord-Endpunkt eine
   Antwort geändert hat.

---

## 11. Wenn der Key schon geleakt ist

Der alte Build hat den Key ausgeliefert. Nach dem Deploy dieser Version:

1. **`DASHBOARD_API_KEY` in Railway neu setzen** (neuer Zufallswert).
2. `NEXTAUTH_SECRET` separat setzen, falls es bisher vom API-Key abgeleitet wurde.
3. `DISCORD_CLIENT_SECRET` im Developer Portal zurücksetzen.
4. `NEXT_PUBLIC_DASHBOARD_API_KEY` in Railway **löschen**, nicht nur leeren.
5. Den alten Giphy-Key im Giphy-Dashboard widerrufen.
6. Optional `force_dashboard_reauth` einschalten, um alte Sitzungen zu entwerten.

**Reihenfolge wichtig:** erst widerrufen, dann im Code ändern. Ein Schlüssel,
der nur aus einer Datei verschwindet, ist weiter gültig.
