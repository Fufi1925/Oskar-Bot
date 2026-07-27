# Prompt für die KI des Template-Bots

Kopiere alles zwischen „--- PROMPT START ---" und „--- PROMPT ENDE ---"
in die andere KI.

**Kurz zum Hintergrund**, damit du weißt, was du weitergibst: **University
Bot** kann den Template-Bot **nicht** selbst zu einem Server hinzufügen.
Discord hat dafür keine Schnittstelle — auch nicht mit Admin-Rechten. Der
OAuth-Ablauf verlangt zwingend einen eingeloggten Menschen, der im Browser
auf „Autorisieren" klickt. Das ist Absicht: sonst könnte ein übernommener
Bot beliebig viele weitere nachziehen, also genau einen Nuke bauen.

Stattdessen erzeugt University Bot einen Einladungslink mit einem
signierten `state`-Wert. Der Template-Bot liest den an seinem
OAuth-Redirect zurück und weiß dadurch: „dieser Server kommt von
University Bot".

Die Seite von University Bot ist fertig und läuft. Der Prompt beschreibt
nur die Gegenseite.

---

## --- PROMPT START ---

Du arbeitest an einem Discord-Bot („Template-Bot"), der fertige
Server-Templates einrichtet. Der Bot ist bereits fertig; es kommt **eine
neue Funktion** dazu.

### Was gebaut werden soll

Ein zweiter Bot namens **University Bot** schickt Server zu uns. Wenn ein
Server über University Bot hinzugefügt wurde, soll unser Bot das erkennen
und sein Template **automatisch** einrichten — ohne dass jemand einen
Befehl tippt. Kommt ein Server auf normalem Weg dazu, bleibt alles wie
bisher.

### Wie die Erkennung funktioniert

University Bot postet einen Einladungslink dieser Form:

```
https://discord.com/oauth2/authorize
  ?client_id=<UNSERE_CLIENT_ID>
  &permissions=8
  &scope=bot%20applications.commands
  &guild_id=<SERVER_ID>
  &disable_guild_select=true
  &state=<SIGNIERTER_TOKEN>
```

Der `state`-Wert ist das Entscheidende. Discord reicht ihn unverändert
durch und hängt ihn an **unsere OAuth-Redirect-URI** an:

```
https://unser-bot.example/oauth/callback?code=…&guild_id=…&state=…
```

**Wichtig:** `state` kommt **nicht** im `on_guild_join`-Event an. Discord
liefert es ausschließlich an die Redirect-URI. Wir brauchen also einen
kleinen Web-Endpunkt. Falls unser Bot noch keinen hat, muss einer dazu
(FastAPI, aiohttp, Flask — egal).

### Aufbau des Tokens

`state` hat die Form `<body>.<signature>`:

- **body**: URL-sicheres Base64 **ohne Padding** eines JSON-Objekts
- **signature**: URL-sicheres Base64 ohne Padding von
  `HMAC-SHA256(secret, body_als_ascii)`

Das JSON enthält:

```json
{
  "g":   "123456789012345678",   // Server-ID
  "u":   "987654321098765432",   // wer den Link angeklickt hat
  "t":   1785200000,              // Unix-Zeit der Ausstellung
  "src": "university-bot",        // muss exakt so lauten
  "guild_name": "Mein Server"     // optional
}
```

Das Secret steht bei beiden Bots in der Umgebungsvariable
`PARTNER_HANDSHAKE_SECRET`. Beide **müssen denselben Wert** haben.

### Prüfung — bitte genau in dieser Reihenfolge

1. `state` enthält genau einen Punkt, beide Teile sind nicht leer
2. Signatur mit `hmac.compare_digest` vergleichen (**nicht** mit `==`
   — sonst lässt sich die richtige Signatur über Laufzeitunterschiede
   Zeichen für Zeichen erraten)
3. JSON dekodieren
4. `src == "university-bot"` prüfen
5. Alter prüfen: `t > 0` **und** `time.time() - t <= 3600`

Schlägt irgendein Schritt fehl: Token **verwerfen**, den Server als ganz
normalen Beitritt behandeln. Nicht raten, nicht teilweise vertrauen.

**Warum die Signatur nicht optional ist:** Ohne sie könnte jeder
`?state=university-bot` an seinen eigenen Einladungslink hängen und
unseren Bot dazu bringen, einen fremden Server als „von University Bot"
zu behandeln.

**Warum `src` trotzdem geprüft wird:** Falls wir später weitere Partner
anbinden, teilen die sich unter Umständen ein Secret. Dann ist `src` das
Einzige, was sie auseinanderhält.

**Wenn `PARTNER_HANDSHAKE_SECRET` nicht gesetzt ist:** gilt **kein** Token
als gültig. Lieber gar keine Automatik als eine manipulierbare.

### Referenz-Implementierung der Prüfung

```python
import base64, hashlib, hmac, json, os, time

SECRET = os.getenv("PARTNER_HANDSHAKE_SECRET", "").encode()
SOURCE = "university-bot"
MAX_AGE = 3600


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def read_state(state: str) -> dict | None:
    """Verified payload, or None if it must not be trusted."""
    if not state or "." not in state or not SECRET:
        return None

    body, _, signature = state.partition(".")
    try:
        expected = _b64(hmac.new(SECRET, body.encode("ascii"),
                                 hashlib.sha256).digest())
        # compare_digest, not ==: constant time.
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_unb64(body).decode("utf-8"))
    except Exception:
        return None

    if payload.get("src") != SOURCE:
        return None

    issued = int(payload.get("t", 0))
    if issued <= 0 or time.time() - issued > MAX_AGE:
        return None

    return payload
```

### Der Ablauf, den du bauen sollst

**1. OAuth-Callback-Endpunkt**

```
GET /oauth/callback?code=…&guild_id=…&state=…
```

- `read_state(state)` aufrufen
- bei Erfolg: `guild_id` in einem kurzlebigen Speicher vormerken
  (ein Dict im Arbeitsspeicher reicht — nach einer Stunde ist der Eintrag
  ohnehin wertlos, und ihn beim Neustart zu verlieren ist sicherer, als
  einen veralteten zu verwenden)
- dem Nutzer eine kurze Bestätigungsseite zeigen

**2. `on_guild_join`**

```python
@bot.event
async def on_guild_join(guild):
    handoff = pending.pop(guild.id, None)
    if handoff is None:
        return                      # normaler Beitritt, nichts tun
    await apply_template(guild, handoff)
```

**3. Das Wettrennen abfangen**

Der Callback kann **vor** `on_guild_join` eintreffen oder **danach** —
beide Reihenfolgen kommen in der Praxis vor und beide müssen
funktionieren. Trifft `on_guild_join` zuerst ein, ist der Eintrag noch
nicht da. Ein einfacher Weg: bei fehlendem Eintrag zweimal im Abstand von
je 2 Sekunden erneut nachsehen, bevor du aufgibst.

**4. Template anwenden**

- Rechte **zuerst** prüfen: `manage_channels`, `manage_roles`. Fehlen sie,
  poste eine verständliche Meldung, statt in eine Ausnahme zu laufen.
- Zwischen den Erstellungen `await asyncio.sleep(...)` einbauen. Discord
  begrenzt Kanal- und Rollenerstellung hart; ohne Pause bricht die
  Einrichtung mittendrin ab und hinterlässt einen halb fertigen Server.
- Grenzen beachten: **500 Kanäle** und **250 Rollen** pro Server. Vorher
  rechnen, nicht beim Anlegen scheitern.
- Am Ende eine Zusammenfassung posten: was angelegt wurde, was nicht, und
  warum nicht.

**5. Nicht doppelt einrichten**

Merke dir pro Server **dauerhaft** (Datenbank, nicht Arbeitsspeicher),
dass das Template schon lief. Wird der Bot entfernt und wieder
hinzugefügt, soll er nicht ein zweites Mal alles anlegen. Ein Befehl zum
bewussten Wiederholen ist in Ordnung.

### Was du **nicht** versuchen sollst

- **Keinen Bot per API einladen.** Geht nicht, es gibt keinen Endpunkt
  dafür. Wer das behauptet, irrt sich.
- **Kein `==` für den Signaturvergleich.**
- **Kein Vertrauen ohne Secret.** Fehlt es, ist die Automatik aus.
- **Keine Massenerstellung ohne Pausen.**

### Umgebungsvariablen

```
PARTNER_HANDSHAKE_SECRET=<derselbe Wert wie bei University Bot>
OAUTH_REDIRECT_URI=https://unser-bot.example/oauth/callback
DISCORD_CLIENT_ID=<unsere Client-ID>
DISCORD_CLIENT_SECRET=<unser Client-Secret>
```

Die Redirect-URI muss **exakt so** im Discord Developer Portal unter
OAuth2 → Redirects eingetragen sein, sonst lehnt Discord die
Autorisierung ab.

### Tests, die ich sehen will

- ein gültiges Token wird angenommen
- eine gefälschte Signatur wird abgelehnt
- ein ausgetauschter Body unter gültiger Signatur wird abgelehnt
- ein korrekt signiertes Token mit **anderem `src`** wird abgelehnt
- ein Token älter als eine Stunde wird abgelehnt
- ohne `PARTNER_HANDSHAKE_SECRET` wird **jedes** Token abgelehnt
- `on_guild_join` vor dem Callback funktioniert genauso wie umgekehrt
- ein Server ohne Handoff wird nicht angefasst
- ein zweiter Beitritt richtet nicht erneut ein

## --- PROMPT ENDE ---

---

## Was du auf der Seite von University Bot noch setzen musst

In Railway unter **Variables**:

| Variable | Wert |
|---|---|
| `PARTNER_BOT_CLIENT_ID` | Die Client-ID des Template-Bots |
| `PARTNER_HANDSHAKE_SECRET` | Ein langes Zufalls-Secret |

Dasselbe Secret muss beim Template-Bot stehen. Erzeugen zum Beispiel mit:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Solange `PARTNER_BOT_CLIENT_ID` fehlt, blendet University Bot den Bereich
„Template-Bot hinzufügen" im Dashboard einfach aus.

### Wo der Wert im Code steht

`bot/utils/partner_bot.py`:

```python
SOURCE = "university-bot"
```

Änderst du diesen String, musst du ihn im Prompt oben mitändern —
ansonsten lehnt der Template-Bot jeden Link ab.
