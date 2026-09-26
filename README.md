<div align="center">

# University Bot

**Discord-Bot und Web-Dashboard in einem Railway-Deployment.**

</div>

---

**Rechte.** Alle Rechte vorbehalten, siehe [LICENSE](LICENSE). Der Hinweis
**steht hier im Fließtext und nicht in einem Zitatblock** — ein Test liest
diese Datei und überspringt Zeilen, die mit `>` beginnen. Stand er im Zitat,
meldete der Test die Korrektur einer früheren falschen Lizenzangabe als
neuen Fehler.

**Keine Pull-Requests.** An diesem Projekt arbeitet ein kleines Team. Auch bei
kleinen Korrekturen nehmen wir keine an; der Weg ist der Support-Server. Für
Sicherheitsmeldungen gilt [.github/SECURITY.md](.github/SECURITY.md).

---

## Was hier läuft

Ein Container, vier Teile. FastAPI lauscht auf `$PORT` (Standard 8080) und
ist der öffentliche Eingang; jede Anfrage, die dort nicht bekannt ist, geht
an das Dashboard weiter.

```
Railway-Container  ·  ein Port
├─ university_bot.py      Discord-Bot + FastAPI auf $PORT  (155 Cogs)
│   ├─ /api/v1/*          Bot-Schnittstelle, die das Dashboard anspricht
│   ├─ /louckup           eigener, abgetrennter Bereich (pausiert)
│   ├─ /lbost-shop        Shop-Bereich mit eigener Discord-App
│   └─ /…                 Rest  →  Proxy auf das Dashboard
├─ node server.js         Next.js-Dashboard, 127.0.0.1:3000 (intern)
├─ phantom/run_bot.py     Ticket-Bot, nur mit PHANTOM_BOT_TOKEN
└─ lbost-shop/run_bot.py  Shop-Bot, nur mit LBOST_SHOP_BOT_TOKEN
```

Der Status-Bot unter `statusbot/` läuft als **eigener Railway-Service** — nur
so kann er den Hauptbot überwachen, wenn der nicht mehr antwortet.

## Der Name

Das Produkt heißt **University Bot**. Der Ordner im Host heißt `Oskar-Bot`,
und das ist auch so gemeint: Repo-Name und Produktname sind zwei
verschiedene Dinge.

Der Name wird nicht übersetzt. „Universitätsbot" ist eine Übersetzung des
Namens und damit ein zweiter Name für dasselbe — die Suche findet dann nur
einen von beiden. `bot/utils/config.py` und `dashboard/lib/brand.ts` halten
deshalb dieselbe Regel: Schreibweisen wie „Universitätsbot",
„UniversityBot" oder „universitybot X" werden auf den einen Namen
zurückgeführt. Ein Test sichert das (`bot/tests/test_marke.py`).

## Der Kern in einem Absatz

Der Bot verwaltet Server: Moderation, Automod, Anti-Nuke, Tickets,
Bewerbungen, Begrüßung und Abschied, Level, Musik, Gewinnspiele, Zählen,
Verifizierung, Sprachkanäle und eigene Befehle. Das Dashboard ist die
einzige Stelle, an der das eingestellt wird — für Einstellungen gibt es
keine Chat-Befehle. Jede Änderung läuft über den Proxy des Dashboards, und
**der prüft die Rechte, nicht der Browser**: eine Sperre, die nur als
Blendung im Frontend sitzt, ist keine Sperre.

**Premium** hängt am Discord-Konto und gibt **drei feste Serverplätze**
(`bot/utils/premium_membership.py`). Laufzeiten sind 30, 90 oder 365 Tage.
Bezahlt wird noch nicht: Jede Anfrage bestätigt das Team von Hand.
Einzelheiten in [docs/PREMIUM.md](docs/PREMIUM.md).

## Verzeichnis

| Ordner | Inhalt |
|---|---|
| `bot/` | Discord-Bot, FastAPI-Schnittstelle, SQLite-Speicher, 137 eigenständige Testskripte |
| `dashboard/` | Next.js 14 (App Router): öffentliche Seiten, Server-Dashboard, Admin-Bereich |
| `phantom/` | isolierter Ticket-Bot mit eigenem Login |
| `statusbot/` | Status-Dienst, eigener Railway-Service |
| `lavalink/` | Konfiguration für einen eigenen Musik-Server |
| `louckup/` | abgetrennter Nachschlage-Bereich — **pausiert, nicht anfassen** |
| `lbost-shop/` | Shop-Bereich mit eigenem Bot |
| `tools/` | Helfer für Übersetzungen, Deploy-Verlauf und Prüfläufe |

## Lokal starten

```bash
cd bot
pip install -r requirements.txt
python university_bot.py                     # Bot und API auf 8080

cd ../dashboard
npm install
NEXTAUTH_SECRET=dev npm run dev              # Dashboard auf 3000
```

Nötig sind `TOKEN` und `OWNER_IDS` für den Bot, `NEXTAUTH_SECRET` und
`NEXTAUTH_URL` für das Dashboard. Ohne echten Discord-Bot geht das nicht;
die Prüfung unten schon.

## Prüfen

```bash
cd bot
python3 tests/run_all.py                   # alle Testskripte, ohne pytest
python3 ../.github/scripts/boot_test.py    # lädt jedes Cog ohne Discord
```

Beide laufen ohne Netzwerk und ohne Token. Der Boot-Lauf ist der
wertvollere: Er importiert jedes Cog, jede Routendatei und jede
Übersetzungstabelle. Was dort fehlt, fällt sonst erst im Betrieb auf —
meist als 500.

Die Workflow-Datei unter `.github/workflows/` ruft dasselbe auf, aber
**nur von Hand ausgelöst**. Es gibt bewusst keinen Auslöser bei jedem Push:
Der Bot läuft dauerhaft, und eine halb geprüfte Änderung im Hauptzweig ist
teurer als eine, die noch liegt.

## Deployment und Sicherheit

- Railway, Umgebungsvariablen und das Volume: [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)
- Anmeldung, Rechteprüfung, offene Punkte: [SECURITY.md](SECURITY.md)
