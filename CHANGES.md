# Was gemacht wurde

5 Commits, 36 Dateien, +4501 / −328 Zeilen. Alles auf `arena/019f9aa2-oskar-bot`.

---

## 🔴 Sicherheit

### API-Key im Browser-Bundle
`lib/api.ts` las clientseitig `NEXT_PUBLIC_DASHBOARD_API_KEY`. Next.js ersetzt
`NEXT_PUBLIC_*` beim Build durch den Literalwert — der Key stand also im
JavaScript, das jeder Besucher herunterlädt.

**Gelöst mit einem BFF-Proxy:**
```
Browser → /api/bot/guilds/<id>/automod → FastAPI /api/v1/guilds/<id>/automod
          (nur Session-Cookie)            (Bearer-Key, serverseitig gesetzt)
```
`app/api/bot/[...path]/route.ts` prüft Session + Guild-Rechte und hängt den Key
erst danach an. Server Components rufen die API weiterhin direkt auf.

**Verifiziert:** Testbuild mit gesetztem Key → nicht in `.next/static`.
Gegenprobe mit dem alten Code → Key in 3 Client-Chunks gefunden.

### Fehlende Guild-Autorisierung
`guilds.py` prüfte nie, ob der Aufrufer den Server verwalten darf. 22 von 23
Guild-Seiten riefen kein `getServerSession()` auf.

Drei Ebenen greifen jetzt:
1. `middleware.ts` — Session-Pflicht für `/dashboard` und `/api/bot`
2. Guild-Layout — `verifyGuildAccess()`, gilt für alle 23 Unterseiten
3. BFF-Proxy — prüft jede einzelne API-Anfrage

`lib/guild-auth.ts` fragt Discord nach den echten Rechten des Nutzers
(`ADMINISTRATOR` / `MANAGE_GUILD` / Owner), 60 s pro Token gecacht.

### localhost-Bypass
`verify_api_key()` vertraute jeder Anfrage von `127.0.0.1` — und der Proxy kam
genau von dort. Der Key wird jetzt immer verlangt, Vergleich per
`hmac.compare_digest`.

### Kleinkram
- Giphy-Key aus `fun.py` → `GIPHY_API_KEY`
- `eval()` in `calc.py` → AST-Evaluator mit Operator-Whitelist
  (getestet: `__import__(...)`, `open(...)`, `9**9**9` werden blockiert)

---

## 🟠 Deployment-Blocker

| Problem | Lösung |
|---|---|
| `pillow` auskommentiert, 14 Module importieren PIL hart | einkommentiert |
| `pytz` fehlt (alle 17 Antinuke-Cogs) | ergänzt |
| `aiofiles`, `google-generativeai`, `pydantic`, `typing_extensions` fehlen | ergänzt |
| Stdlib als Pakete (`asyncio`, `typing`, `pathlib`, `collection`) | entfernt |
| Dubletten + ungenutzte Pakete (Quart, flask, motor, pymongo, Augmentor …) | entfernt |
| `db/` wird nie angelegt | `utils/bootstrap.py` |
| `instructions/`, `channels.json` fehlen → Crash | Defaults statt Exception |
| `asyncio.run()` beim Import | Fallback auf `sqlite3` |
| Crash bei leerem `CMD_WEBHOOK_URL` | wird übersprungen |
| Node-Version ungepinnt | Node 18 in beiden Stages |

---

## 🟡 Feature-Flags — alle 50 implementiert

Vorher: Werte in einer Tabelle, die niemand las. Jetzt echte Wirkung.

| Modul | Aufgabe |
|---|---|
| `feature_flags.py` | Registry, Persistenz, Cache, Dependencies, Rollouts |
| `feature_gates.py` | Command-Gate: Lockdown, Freeze, Owner-Only, Blacklist, Premium, Beta |
| `feature_services.py` | Health-Monitore, Backups mit Rotation, Cleanup, Announcements, Deadlock-Watchdog |
| `feature_audit.py` | Audit-Log, Notification-History, Approval-Queue, Timeline |
| `feature_reports.py` | Security-Score, Risk-Scans, Invite-Growth, Retention, Voice |
| `feature_enforcement.py` | Guild-Join-Guard, Leave-Audit, Voice-Tracking, Cache-Warmup |

**Getestet:** Toggle, Dependency-Kaskade (`music_node_failover` inaktiv wenn
`lavalink_health_monitor` aus), Rollout (50 % → exakt 100 von 200 Guilds),
Persistenz über Reload, Reauth-Epoch.

**Dashboard:** neue Tabs *Features* (gruppiert, durchsuchbar, Rollout-Slider)
und *Health* (Shards, Lavalink, Discord-Status, Integrität, Backups, Logs).

**13 neue Endpunkte:** `/admin/features/detail`, `/admin/health`, `/admin/logs`,
`/admin/metrics`, `/admin/audit`, `/admin/timeline`, `/admin/approvals`,
`/admin/reports/{name}`, `/admin/announcements`, `/admin/mass-config`,
`/admin/premium/{id}`, `/admin/session-policy`, `/admin/features/{key}/rollout`

`maintenance_mode` setzt jetzt zusätzlich `global_command_freeze` und zeigt ein
Banner.

---

## 🟡 Doppelte Endpunkte & Performance

- `/welcome` und `/autoreact` waren doppelt definiert. Starlette nimmt die
  **erste** Registrierung — die zweite war toter Code. 80 Zeilen entfernt.
- `getConfig()` lief bei jeder Nachricht gegen SQLite → jetzt In-Memory-Cache.
- `get_prefix()` öffnete zusätzlich 2× `db/np.db` → beide Tabellen gecacht,
  60 s Refresh, API invalidiert bei Änderungen.

**Gemessen:** 100 `getConfig()`-Aufrufe → 0 DB-Öffnungen (vorher 100).
Pro Nachricht: 3 → 0.

---

## Übersprungen (auf deinen Wunsch)

Die 70 bare `except:` Blöcke.

---

## Verifikation

| Check | Ergebnis |
|---|---|
| `python -m compileall bot/` | ✅ |
| `npx tsc --noEmit` | ✅ |
| `npm run build` | ✅ 11/11 Seiten, Middleware 50.3 kB |
| Key-Leak-Test | ✅ nicht im Bundle (alter Code: 3 Chunks) |
| Feature-Flag-Tests | ✅ alle 50, Dependencies, Rollout, Persistenz |
| Bootstrap-Test | ✅ legt Ordner/Dateien an |
| Config-Loader ohne Dateien | ✅ kein Crash |
| Prefix-Cache | ✅ 100 Calls → 0 DB-Öffnungen |

---

## ⚠️ Nach dem Deploy zu tun

1. **`DASHBOARD_API_KEY` neu setzen** — der alte wurde ausgeliefert
2. **`ADMIN_IDS`** setzen (serverseitige Prüfung, zusätzlich zu `NEXT_PUBLIC_ADMIN_IDS`)
3. **`NEXTAUTH_SECRET`** separat setzen, falls bisher vom API-Key abgeleitet
4. **Giphy-Key widerrufen** (`y3Kc…` stand im Repo) und neuen als `GIPHY_API_KEY` setzen
5. **`NEXT_PUBLIC_DASHBOARD_API_KEY` in Railway löschen** (start.sh entfernt sie
   zwar zur Laufzeit, aber sauberer ist weg)
