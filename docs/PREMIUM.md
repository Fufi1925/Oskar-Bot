# Premium-Keys

Lizenz-Keys für die Premium-Funktionen des Template-Bots.

## Wie es abläuft

1. Jemand kauft Premium im Discord.
2. Ein Team-Mitglied erstellt den Key im Dashboard unter
   **Admin → Premium**. Auf Wunsch schickt der Bot ihn **per DM**.
3. Der Käufer trägt den Key im Dashboard unter **Admin → Premium** ein.
   Beim Einlösen wird er fest an sein Discord-Konto gebunden.
4. Der Template-Bot fragt bei uns nach, ob dieses Konto Premium hat.

Der Key gilt für das **Discord-Konto**, nicht für einen Server. Wer ihn
eingelöst hat, hat Premium — egal auf welchem Server.

## Keys verwalten

Alles unter **Admin → Premium**. Die früheren `/key`-Befehle gibt es
nicht mehr: Lizenzen sind Abrechnung, das gehört an eine Stelle mit
Protokoll statt in einen Chat-Befehl, den nur drei Leute nutzen dürfen.

| Feld | Wirkung |
|---|---|
| Laufzeit in Tagen | `0` = unbegrenzt. Standard 30. |
| Discord-ID | Optional. Ist sie gesetzt, geht der Key per DM raus. |
| Notiz | Optional, z.B. eine Bestellnummer. |

Der erzeugte Key wird **einmal** angezeigt und lässt sich kopieren.
Danach ist er nur noch gehasht gespeichert.

Ob die DM angekommen ist, wird ehrlich gemeldet: `sent`, `dms_closed`,
`unknown_user` oder `failed`. Der Key existiert in jedem Fall — bei
einem Fehlschlag muss er von Hand weitergegeben werden.

In der Liste steht pro Key, wer ihn eingelöst hat (Name statt nur ID),
ob er aktiv, offen, abgelaufen oder gesperrt ist. Sperren lässt sich
**rückgängig machen**, damit ein Fehlklick nicht endgültig ist.

Die Laufzeit läuft **ab Einlösung**, nicht ab Erstellung. Ein Key, der
eine Woche ungelesen in der DM liegt, verliert dadurch nichts.

## Sperren wirkt sofort

Wird ein Key im Dashboard gesperrt, meldet der Hauptbot das dem
Template-Bot (`POST /internal/licence-revoked`). Der löscht daraufhin
**alle** lokalen Freischaltungen dieses Kontos aus seinem Volume und
leert seinen Zwischenspeicher — Premium ist dort also sofort weg, nicht
erst nach fünf Minuten.

Ohne `TEMPLATE_BOT_URL` entfällt nur die Sofortwirkung: der Widerruf
greift dann, sobald der Template-Bot das nächste Mal nachfragt. Das
Dashboard sagt dazu, welcher der beiden Fälle eingetreten ist.

> Hält jemand **zwei** gültige Lizenzen, wird beim Sperren einer davon
> nichts gemeldet — die andere gilt ja weiter.

## Die Premium-Rolle

Unter **Admin → Bot Config → Premium Role** eine Rollen-ID eintragen.
Wer eine gültige Lizenz hat, bekommt die Rolle auf dem Support-Server.

Abgeglichen wird alle 10 Minuten — nicht nur beim Einlösen. Eine Lizenz
*endet* auch, und dabei löst nichts ein Ereignis aus: ohne Timer würde
ein abgelaufener Kunde die Rolle für immer behalten.

Drei Dinge gehen dabei erfahrungsgemäß schief, und alle drei werden im
Dashboard getrennt gemeldet:

- keine Rolle eingestellt
- dem Bot fehlt „Rollen verwalten"
- die Rolle steht **über** der Bot-Rolle — Discord verweigert das

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
| `PARTNER_BOT_CLIENT_ID` | Hauptbot | Client-ID des Template-Bots, für den Einladungslink. |
| `TEMPLATE_BOT_URL` | Hauptbot | Adresse des Template-Bots. Ohne sie wirkt ein Widerruf erst nach ~5 Minuten. |
| `PREMIUM_ROLE_ID` | Hauptbot (optional) | Rolle für Premium-Nutzer. Auch im Dashboard einstellbar. |
| `HOME_GUILD_ID` | Hauptbot | Support-Server. Standard: `1530378233579704370`. |

> ⚠️ **`PREMIUM_KEY_PEPPER` muss vor dem ersten Key gesetzt sein und darf
> danach nie geändert werden.** Eine Änderung macht *alle* bisherigen
> Keys ungültig. Das Dashboard weigert sich, solange der Wert fehlt.

Einen Pepper erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Schnittstelle für den Template-Bot

> **Eingebaut.** Der Template-Bot fragt seit
> [`9c5a3e3`](https://github.com/Fufi1925/University-Template) selbst nach
> (`core/licence.py`). Es müssen dort nur noch `MAIN_BOT_URL` und
> `PREMIUM_PARTNER_TOKEN` gesetzt werden.
>
> Bleiben beide leer, gilt dort weiterhin nur der alte Master-Key.

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

> **Kein Dashboard-Key nötig.** Die restliche API verlangt
> `Authorization: Bearer <DASHBOARD_API_KEY>`. Dieser eine Endpunkt nicht:
> der Template-Bot ist ein anderes Programm und hat keinen Grund, den
> Dashboard-Schlüssel zu kennen. Er authentifiziert sich ausschließlich
> mit `X-Partner-Token`.
>
> Die Ausnahme ist eng gefasst — nur `GET`, nur `/premium/check/…`, und nur
> bei passendem Token. Jede andere Route braucht weiterhin den
> Dashboard-Schlüssel.

**Statuscodes**

| Code | Bedeutung |
|---|---|
| `200` | Antwort wie oben. |
| `401` | Token fehlt oder ist falsch. |
| `503` | `PREMIUM_PARTNER_TOKEN` ist beim Hauptbot nicht gesetzt. |

**So ist es im Template-Bot umgesetzt** (`core/licence.py`, gekürzt)

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

Zwei Eigenschaften, an denen dort alles hängt:

- **Zwischenspeichern.** Antworten gelten 5 Minuten. Ein Aufruf pro Klick
  wäre zu langsam — Discord verwirft Interaktionen nach 3 Sekunden.
- **Im Zweifel nein.** Netzwerkfehler, 401, 503, unlesbare Antwort: alles
  bedeutet „kein Premium". Ein Ausfall darf niemanden freischalten.

Der Template-Bot prüft **zuerst seinen lokalen Store** (Master-Key) und
erst danach hier. Eine bestehende Freischaltung gilt also weiter, auch
wenn der Hauptbot gerade nicht erreichbar ist.

## Was das Dashboard zeigt

**Seitenleiste → Premium** (für jeden angemeldeten Nutzer, nicht nur für
Admins — wer einen Key gekauft hat, ist kein Teammitglied):

- **University Bot Premium** — „Coming Soon"
- **Template-Bot Premium** — Status und Eingabefeld

Zusätzlich unter **Admin → Premium** dieselben zwei Karten, darunter für
das Team die Liste der ausgegebenen Keys mit Sperr-Knopf. Dort stehen nur
Hashes, nie die Keys selbst.

## Sicherheit

- Keys liegen gehasht in `db/premium.db`, nicht im Klartext.
- Beim Einlösen setzt der Dashboard-Proxy die Konto-ID **aus der
  Sitzung**. Eine ID aus dem Browser wird ignoriert, sonst könnte man
  Premium auf ein fremdes Konto buchen.
- `/premium/check/...` ist über das Dashboard **nicht** erreichbar —
  sonst könnte jeder eingeloggte Browser fremde Konten abfragen.
- Das Partner-Token wird mit `hmac.compare_digest` verglichen, damit die
  Laufzeit nichts über die richtigen Zeichen verrät.
