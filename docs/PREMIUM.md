# Premium

Stand September 2026. Beschreibt, was der Code tut — nicht, was die
Webseite verspricht. Beide sollten dasselbe sagen; wenn sie es nicht tun,
ist dieses Dokument die Prüfung und die Webseite der Fehler.

---

## Ein Modell: Konto mit drei Serverplätzen

Premium hängt am **Discord-Konto**. Ein Konto bekommt **drei feste
Serverplätze** — es schaltet also nicht „alle Server, auf denen man Rechte
hat" frei, sondern genau die drei, die man zuweist.

```
Konto (Discord-ID)
 ├─ Laufzeit: 30, 90 oder 365 Tage
 └─ Platz 1, 2, 3  →  je eine Server-ID
```

Grund für die Plätze: Ein Bot mit Admin-Rechten auf vielen Servern und
einem Konto-Zugang wäre ein Werkzeug, das ein einziger gekaufter Zugang für
Dutzende Communities ändert. Die Grenze pro Server ist die eigentliche
Sicherheit, nicht die Preismechanik.

Gespeichert in `db/premium_membership.db` (braucht ein Railway-Volume,
sonst sind alle Zuweisungen nach jedem Deploy weg).

---

## Was eingeschaltet wird

Ein Server mit Platz bekommt:

| Bereich | Was Premium dort kann |
|---|---|
| Design | eigener Name, eigenes Profilbild, eigenes Banner für diesen Server |
| Backup | bis zu 10 Sicherungen, automatische Sicherung, Nachrichten mitsichern |
| Server-Statistik | Statistik-Sprachkanäle, häufiger aktualisiert |
| Mitglieder-Abruf | verifizierte Personen in Rollen holen (nur von Hand, mit Bestätigung) |
| Eigene Befehle | mehr Befehle, mehr Auslöser pro Befehl |
| Speedrun, Vorlagen, höhere Grenzen | die Bereiche, die schon vorher Premium-Limits hatten |

Entschieden wird das an **einer** Stelle: `feature_gates.is_premium_guild()`
und `can_configure_premium_guild()`. Ein Bereich, der daneben eine zweite
Abfrage baut, läuft bei der nächsten Änderung auseinander.

---

## Kaufen geht noch nicht

Es gibt **keine Zahlung**. Wer Premium will, stellt im Dashboard eine
Anfrage (`/dashboard/premium`), das Team bestätigt sie von Hand. Danach
startet die Laufzeit.

Warum so: Ein Beleg, der nirgends nachvollziehbar ist, erzeugt
Support-Fälle, die man nicht lösen kann. Solange die Testphase läuft, ist
die manuelle Bestätigung billiger als jede Halblösung mit Zahlungsanbieter.

Lizenz-Keys, wie sie der Template-Bot früher kannte, werden **nicht mehr
ausgegeben**. Die Tabelle `db/premium.db` bleibt lesen, damit bestehende
Einträge nicht verschwinden, und Admins können im Admin-Bereich weiter von
Hand vergeben (`POST /premium/accounts/grant`). Ein Feld zum Eingeben eines
Keys gibt es im Nutzer-Dashboard nicht mehr — ein Eingabefeld für Keys, die
niemand mehr ausstellt, ist eine Sackgasse mit Cursor.

---

## Was passiert, wenn es abläuft

Der Server verliert die Premium-Funktionen, **Einstellungen bleiben
stehen**. Das ist im Code so entschieden und im Admin-Dialog ausdrücklich
wählbar, wenn ein Admin Premium entzieht:

* „Premium entziehen, Einstellungen behalten" — Standard.
* „Premium-Einstellungen endgültig löschen" — löscht Design, Backups,
  Server-Statistik, eigene Befehle, Ticket-KI-Daten, Abruf-Daten und
  Speedrun-Daten dieses Servers.

Der Inhaber des Servers bekommt in beiden Fällen ein Fenster im Dashboard,
sonst merkt er den Wechsel erst, wenn etwas nicht mehr funktioniert.

---

## Was beim Umzug passiert ist

Vorher gab es zwei getrennte Produkte (`template_bot` und `main_bot`) und
daneben einen 7-Tage-Probezeitraum für Konten. Das Modell ist
zusammengelegt:

| Alt | Heute |
|---|---|
| Key pro Produkt einlösen | Anfrage, vom Team bestätigt |
| Konto hat Premium, gilt überall | Konto hat drei Plätze |
| 7-Tage-Probewoche über den Template-Bot | entfällt als eigener Weg |
| `product="template_bot"` / `"main_bot"` | ein Produkt; alte Aufrufe werden darauf abgebildet |

Beim ersten Start nach dem Deploy widerruft `premium_membership.ensure()`
alle alten `premium_keys` und leert `premium_guilds`. Wer vorher
Template-Premium hatte, hat danach keines — so beschlossen. Die Zeilen
bleiben in der Datenbank stehen (nur `revoked = 1`), damit sich nachvollziehen
lässt, wer wann was hatte.

---

## Prüfen

```bash
cd bot
python3 tests/test_premium_membership_v2.py
python3 tests/test_premium_seite.py
python3 tests/test_backup.py          # Grenzen am Backup-Beispiel
```

Die drei prüfen die Grenze (ein Platz pro Server, drei pro Konto,
Automatik nur mit Premium) gegen die echten Routen — nicht gegen
Textbausteine der Webseite.
