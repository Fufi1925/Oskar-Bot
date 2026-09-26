# Was geändert wurde

Diese Datei beschreibt den Stand **September 2026**. Frühere Stände sind im
Git-Verlauf nachlesbar; was hier steht, ist an dem, was im Zweig `main`
liegt, überprüfbar.

---

## Die September-Welle

153 Commits zwischen dem 28. August und dem 24. September, 322 Dateien,
rund 46.000 geänderte Zeilen.

### Ein Premium, anders geschnitten

`bot/utils/premium_membership.py` (neu, 225 Zeilen) ersetzt das Modell
„Key pro Produkt":

* Premium hängt am **Konto** und gibt **drei feste Serverplätze**.
* Laufzeiten 30, 90 oder 365 Tage; `LIFETIME_EXPIRES_AT` steht für
  „dauerhaft" bereit, verkauft wird noch nicht.
* Anfragen laufen über das Dashboard und werden von Hand bestätigt —
  `premium_purchase_requests`.
* Beim ersten Start werden alte Bestände widerrufen: `premium_keys` auf
  `revoked = 1`, `premium_guilds` geleert. Wer vorher Template-Premium
  hatte, hat es nicht mehr. Das war so beschlossen, nicht ein Verlust.

Die Prüfstelle für „darf dieser Server das?" ist jetzt
`feature_gates.is_premium_guild()` / `can_configure_premium_guild()`. Design,
Backup, Server-Statistiken, Mitglieder-Abruf und Speedrun hängen alle daran —
eine Schwelle statt fünf.

### Neue Bereiche im Server-Dashboard

| Reiter | Was er kann |
|---|---|
| Eigene Befehle | Befehle ohne Programmieren: Auslöser, Einbettungen, Aktionen, höhere Premium-Grenze |
| Server-Statistik | Sprachkanäle mit Mitglieder-, Rollen- und Premium-Zahlen |
| Dashboard-Zugriff | Owner legt fest, welche Rollen und Personen das Server-Dashboard öffnen dürfen |
| Hilfe | Support direkt im Serverkontext, mit Zähler offener Anfragen in der Seitenleiste |
| Mitglieder-Abruf | Owner holt verifizierte Personen in Rollen — absichtlich nur von Hand, mit Bestätigungscode und eigenem Hilfekanal |
| Premium (pro Server) | Zeigt, was der Platz dieses Server gerade freischaltet |

### Admin-Bereich neu sortiert

37 Reiter in neun benannten Gruppen (Betrieb, Support, Server, Moderation,
Team, Community, Bot, Sicherheit, Produkte). Der Filter ist „fail closed":
Ein Reiter ohne Rechteeintrag ist für Team-Rollen unsichtbar statt sichtbar.

### Zwei isolierte Bereiche im selben Container

`/louckup` (Nachschlagen, eigener Login) und `/lbost-shop` (Shop mit eigener
Discord-App und eigenem Bot-Prozess). Beide mit eigener Sitzung, eigenem
Cookie-Pfad und eigener Datenbankdatei unter `$DATA_DIR`.

> **Louckup ruht.** Der Bereich ist fertig gebaut, aber pausiert. Er wird
> nicht weiterentwickelt und in Dokumentationen nur beschrieben, soweit für
> den Betrieb nötig.

### Weitere Änderungen

* **Anwendungsfirewall** mit eigenen Reiter: Regeln, Beobachten-vor-Sperren,
  Rücknahme, Audit-Protokoll, Ausnahmen für eigene Wege.
* **Verifizierung** läuft über Discord-OAuth statt über einen Vier-Code im Chat;
  Panel-Texte sind per Variablen anpassbar.
* **Konto-Seite** (neu, neun Bausteine): Sitzungen, Sicherheit, Aktivitäten,
  Datenschutz, Präferenzen, Bewerbungen, Support, Gefahrenzone — inkl.
  begründetem Löschungsfluss mit Rücknahmefrist und eigene Admin-Bearbeitung.
* **Support-Center** mit Ranglisten, Bewertungen und Danksagungs-Diagnose;
  Dashboard-Zugriff für Supporter nur mit Zustimmung der Person.
* **Community-Ideen** mit öffentlicher Liste, Abstimmung, Kommentaren und
  Belohnungen; Einlösung gibt Server-Premium.
* **Ticket-KI** als Pilot: Wissen aus dem Server aufbauen (Groq, mit
  Raten-Limit-Wiederholung und Abbruch alter Läufe beim Deploy).
* **Übersetzung**: Deutsch und Englisch für Dashboard und Website, Werkzeug
  zum Nachziehen unter `tools/`.
* **Startseite neu**: Sternenhimmel-Held, Globus mit Besucherzahlen,
  Glas-Navigation, Theme-Umschalter (hell/dunkel, gemerkt im Browser).

---

## Auf Zuruf behoben

* **Der Bot-Name.** Er heißt **University Bot** und wird nicht übersetzt.
  Live stand er in drei Formen da: „Universitätsbot" aus einer
  Railway-Variable, „universitybot X" als Rest einer Umbenennung in
  `bot/utils/config.py` und „UniversityBot Devs" in 190 Kommentarzeilen.
  Jetzt gibt es je Seite eine Quelle (`dashboard/lib/brand.ts`,
  `MARKE` in `bot/utils/config.py`), die Schreibweisen auf den einen Namen
  zurückführt, und die Übersetzungstabelle schreibt den Namen nicht mehr um.
  `bot/tests/test_marke.py` hält das fest.
* **Seitentitel.** „ - Ultimate Discord Bot" ist weg; Unterseiten bekommen
  ihren Namen vorangestellt, damit die Suche sie trennen kann.
* **Fußzeile und Ideen-Antwort** nennen jetzt durchgehend denselben Team-Namen.
* **Testpfad.** `test_dashboard_save_bars.py` suchte das Dashboard über den
  Ordnernamen `Oskar-Bot` — lief lokal, wäre in einer anderen Auscheckung
  still auf den Ersatzpfad gefallen. Rechnet jetzt aus der Wurzel.

---

## Doku

* `README.md`, `SECURITY.md`, `CHANGES.md`, `RAILWAY_DEPLOYMENT.md`,
  `docs/PREMIUM.md` und `CODE_ANALYSE.md` auf diesen Stand gebracht.
* `SUMMARY_UNDERSTANDING.md` entfernt — die Analyse desselben alten Stands
  ist jetzt in `CODE_ANALYSE.md`, und zwei Dateien, die dasselbe behaupten,
  laufen auseinander.
* `bot/README.md` und `dashboard/README.md`: die ASCII-Kopfzeilen mit dem
  alten Projektnamen sind durch eine kurze, echte Beschreibung ersetzt,
  und die YouTube-Verweise hatten ein Leerzeichen in der URL — sie
  funktionierten nie.
* `statusbot/ENV.md`: eine Zeile mit einem einzelnen Buchstaben war beim
  Editieren übrig geblieben.

---

## Bekannte Punkte, die nicht neu sind

Nachgemessen an einem sauberen Arbeitszweig von `a08cfc6` (also **ohne**
diese Doku-Arbeit) und mit ihr: **38 Testdateien schlagen in beiden Läufen
fehl, die Liste ist identisch.** Es ist also nichts dazugekommen. Diese
Dateien beschreiben das alte Modell oder einen zu engen Prüfer, nicht
kaputte Funktion — bewusst nicht stillschweigend umgeschrieben:

| Datei | Grund |
|---|---|
| `test_ideas.py` | erwartet „Owner-only" an einer anderen Stelle und einen Startseiten-Text, den die neue Startseite so nicht schreibt |
| `test_dashboard_save_bars.py` | die fünf neuen Reiter fehlen in der Ausnahmeliste |
| `test_firewall.py` | liest `bot/api/server.py` aus dem aktuellen Ordner und läuft nur aus der Wurzel |
| `test_docs_seite.py` | die Doku-Seite nennt 45 Bereiche, es sind mehr |
| 33 weitere Dateien | Prüfung gegen Umbauten, die die September-Welle gebracht hat |

Dazu die offenen Sicherheitspunkte in [SECURITY.md](SECURITY.md), Abschnitt 10 —
vor allem `eval()` in `autorole.py` und die ausständigen Zugangsdaten.

### Ein Test, der nur hier rot ist

`test_speedrun_templates.py` vergleicht die Schrittliste des Speedruns mit
der **echten** Vorlagen-Registry des Template-Bots aus dem Nachbarordner
`../University-Template`. Fehlt der Ordner, überspringt der Test.

In diesem Workspace liegt er (Branch `arena/019ffd1a-university-template`),
und zwei fest verdrahtete Erwartungen sind dort überholt: `rp` baut jetzt
Rollen-Vergabe, `business` jetzt Tickets. Der andere, allgemeinere Prüfschritt
des Tests ist grün — die Schrittliste folgt den neuen Fähigkeiten also
richtig. Nur die Beispielliste im Test müsste nachgezogen werden, und das ist
eine Entscheidung über den Template-Bot, keine Nebenwirkung dieser Doku.
