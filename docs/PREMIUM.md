# Premium-Keys

Lizenz-Keys für die Premium-Funktionen des Template-Bots.

## Wie es abläuft

1. Jemand kauft Premium im Discord.
2. Ein Team-Mitglied erstellt mit `/key create` auf dem Support-Server
   einen Key. Der Bot schickt ihn **per DM** — nie in den Kanal.
3. Der Käufer trägt den Key im Dashboard unter **Admin → Premium** ein.
   Beim Einlösen wird er fest an sein Discord-Konto gebunden.
4. Der Template-Bot fragt bei uns nach, ob dieses Konto Premium hat.

Der Key gilt für das **Discord-Konto**, nicht für einen Server. Wer ihn
eingelöst hat, hat Premium — egal auf welchem Server.

## Befehle

| Befehl | Wirkung |
|---|---|
| `/key create [days] [note]` | Neuer Key. `days=0` heißt unbegrenzt, Standard 30. |
| `/key revoke <key>` | Key sperren. Wirkt auch, wenn er schon eingelöst wurde. |

Beide nur auf dem Support-Server und nur für Konten in `OWNER_IDS`.

Die Laufzeit läuft **ab Einlösung**, nicht ab Erstellung. Ein Key, der
eine Woche ungelesen in der DM liegt, verliert dadurch nichts.

## Wichtig: Keys sind nicht wiederherstellbar

Keys werden **nur gehasht** gespeichert (HMAC-SHA256 mit Pepper). Die DM
ist die einzige Kopie. Geht sie verloren, muss der Key gesperrt und ein
neuer erstellt werden — auch wir können ihn nicht auslesen.

Das ist Absicht: Ein Key, den man aus der Datenbank lesen kann, ist ein
Key, den jeder lesen kann, der an die Datenbank kommt.

## Nötige Variablen

| Variable | Wo | Zweck |
|---|---|---|
| `PREMIUM_KEY_PEPPER` | Hauptbot | Zufälliger Wert, mit dem Keys gehasht werden. |
| `PREMIUM_PARTNER_TOKEN` | Hauptbot **und** Template-Bot | Gemeinsames Geheimnis für die Abfrage. |
| `HOME_GUILD_ID` | Hauptbot | Support-Server. Standard: `1530378233579704370`. |

> ⚠️ **`PREMIUM_KEY_PEPPER` muss vor dem ersten Key gesetzt sein und darf
> danach nie geändert werden.** Eine Änderung macht *alle* bisherigen
> Keys ungültig. `/key create` weigert sich, solange der Wert fehlt.

Einen Pepper erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Schnittstelle für den Template-Bot

Der Template-Bot ist ein eigenes Programm. Er muss selbst nachfragen —
wir können sein Premium nicht von außen freischalten.

**Anfrage**

```http
GET https://<hauptbot-host>/api/v1/premium/check/<discord_user_id>
X-Partner-Token: <PREMIUM_PARTNER_TOKEN>
```

**Antwort**

```json
{
  "user_id": "1303627964734246944",
  "product": "template_bot",
  "premium": true,
  "expires_at": 1788132016,
  "lifetime": false
}
```

- `premium` — das Einzige, worauf es ankommt.
- `expires_at` — Unix-Zeit, oder `null` bei unbegrenzt.
- `lifetime` — `true`, wenn der Key nie abläuft.

Abgelaufene und gesperrte Keys liefern `premium: false`.

**Statuscodes**

| Code | Bedeutung |
|---|---|
| `200` | Antwort wie oben. |
| `401` | Token fehlt oder ist falsch. |
| `503` | `PREMIUM_PARTNER_TOKEN` ist beim Hauptbot nicht gesetzt. |

**Beispiel (Python, discord.py)**

```python
import os
import aiohttp

MAIN_BOT_URL = os.getenv("MAIN_BOT_URL", "").rstrip("/")
TOKEN = os.getenv("PREMIUM_PARTNER_TOKEN", "")


async def has_premium(user_id: int) -> bool:
    """
    Whether this Discord account has premium.

    Fails closed: if the main bot is unreachable nobody is granted
    premium by accident. Cache this — do not call it on every message.
    """
    if not MAIN_BOT_URL or not TOKEN:
        return False
    url = f"{MAIN_BOT_URL}/api/v1/premium/check/{user_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"X-Partner-Token": TOKEN},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status != 200:
                    return False
                return bool((await response.json()).get("premium"))
    except Exception:
        return False
```

Zwei Hinweise für die Einbindung:

- **Zwischenspeichern.** Ein Aufruf pro Nachricht wäre ein Fehler; ein
  paar Minuten Cache reichen völlig.
- **Im Zweifel nein.** Ist der Hauptbot nicht erreichbar, darf das nicht
  versehentlich Premium freischalten.

## Was das Dashboard zeigt

**Admin → Premium**, zwei Karten:

- **University Bot Premium** — „Coming Soon", kein Eingabefeld. Für den
  Hauptbot gibt es noch nichts zu verkaufen.
- **Template-Bot Premium** — Status und das Feld zum Einlösen.

Darunter für das Team die Liste der ausgegebenen Keys mit Sperr-Knopf.
Dort stehen nur Hashes, nie die Keys selbst.

## Sicherheit

- Keys liegen gehasht in `db/premium.db`, nicht im Klartext.
- Beim Einlösen setzt der Dashboard-Proxy die Konto-ID **aus der
  Sitzung**. Eine ID aus dem Browser wird ignoriert, sonst könnte man
  Premium auf ein fremdes Konto buchen.
- `/premium/check/...` ist über das Dashboard **nicht** erreichbar —
  sonst könnte jeder eingeloggte Browser fremde Konten abfragen.
- Das Partner-Token wird mit `hmac.compare_digest` verglichen, damit die
  Laufzeit nichts über die richtigen Zeichen verrät.
