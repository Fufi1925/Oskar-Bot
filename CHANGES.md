# Was geändert wurde

## Oktober: LBoost Shop von Grund auf nachgezählt

Der Shop-Bereich (`lbost-shop/`) hatte schon alle sieben Module aus der
Wunschliste — Tickets, Moderation, Welcome/Leave, Reaction Roles,
Automation, Logging, Giveaways. Also erst gemessen, dann geflickt, dann
das ergänzt, was der Hauptbot kann und der Shop nicht.

Vier echte Fehler, vorher gemessen (Skript unter `/home/user/repro/`, jede Zahl nachgeprüft):

* **Verbindungsleck.** `with sqlite3.connect(...) as conn` committet,
  schließt aber nie. 150 Konfigurationslesungen waren 150 offene
  Datei-Deskriptoren — und der Bot liest die Konfiguration bei jedem
  Event. Jetzt ein Kontextmanager mit Pool pro Thread, garantiertes
  `commit()` und `busy_timeout`. Messung nach dem Fix: +0 Deskriptoren
  bei 800 Lesungen.
* **Die Content-Security-Policy hat das halbe Dashboard abgeschaltet.**
  `style-src 'self'` ohne `unsafe-inline` verbietet auch `style`-Attribute
  — und genau darin standen Fortschrittsbalken und Diagrammhöhen.
  Chromium meldete 30 Verstöße, der Balken war so breit wie sein Rahmen,
  alle 14 Diagrammbalken 4 px hoch. Behoben ohne Aufweichung: 201
  generierte Klassen (`.ub-fill-0` … `.ub-h-100`). Nachgemessen: 0
  Verstöße, 264 px bei 29 %, ungleiche Balkenhöhen.
* **Der Bot hat den Verlaufsgraphen gefüllt.** Laufzeit-Schreiben
  (nächster Sendelauf) landeten in `feature_audit` und damit im
  „14-Tage-Verlauf“ des Servers; die Tabelle wuchs ungebremst. Jetzt
  `audit=False` für Laufzeit, Zustand in einer eigenen Tabelle,
  Aufräumlauf beim Start (45 Tage).
* **Verlorenes Update.** Der Automations-Worker las die Konfiguration,
  fügte `next_run` ein und schrieb das Ganze zurück. Traf das auf ein
  parallel gespeichertes Formular, war die Änderung des Nutzers weg —
  im Test vorher reproduziert (`extra` war `None`, erwartet `1`).

Was der Hauptbot konnte und der Shop nicht, ist jetzt drin — in eigener
Implementierung, weil der Bereich bewusst nichts importiert:

* `lbost_shop_app/regeln.py` als *eine* Regelstelle für Platzhalter,
  Fragen, Kürzungen und Kanalnamen. Dashboard-Vorschau und Bot rufen
  dieselbe Funktion auf; ein Test prüft die Gleichheit und dass der Bot
  keine eigenen Defaults mehr hat.
* Ticket-Begrüßung, Überschrift und Bestätigung waren im Bot bereits
  vorgesehen (`ticket_title`, `ticket_message`) aber im Formular nicht
  vorhanden — also gar nicht settingbar. Jetzt drin, mit den fünf
  Platzhaltern des Hauptbots.
* Bis zu fünf **Formularfragen** vor dem Öffnen (kurz / Absatz / Bild),
  Antworten hängen im Ticket — wie im Hauptbot, inklusive Modal vor
  `defer()`.
* **Live-Vorschau** im Ticket-Formular: entprellt 500 ms, eine Anfrage pro
  Tippkaskade (gemessen), rechnet im Bot, speichert nichts. Fremde
  Felder melden sich als „Feld unbekannt", statt still den alten Stand
  zu zeigen.
* Bot-Herzschlag statt festgeschriebenem „Online"-Schild, Verwarnungs-
  liste im Moderations-Reiter mit Einzellöschung, Admin-Panel mit
  Sitzungen („alle abmelden"), Freigabeliste und Änderungsverlauf.

Zuverlässigkeit und Sicherheit nebenbei: Rechtecheck vor `delete()` und
`timeout()` (ein fehlendes Recht warf und stoppte den AutoMod für den
ganzen Server), Rollenprüfung vor `add_roles`, Giveaway-Gewinner nur aus
Anwesenden, ein Abschluss pro Wettbewerb, Ratelimit-Wörterbuch räumt auf,
Zahlen-/URL-/Farb-/JSON-Grenzen im Formular und beim Import,
Discord-Lesungen gecacht, GZip und ein Jahres-Cache mit Versions-Suffix
auf den statischen Dateien.

Das Sprach-Menü oben rechts war eine Attrappe: Es schrieb nur „EN“ in die
Beschriftung. Statt einer halben Übersetzung ist der Platz jetzt der
echte Bot-Status; eine DE/EN-Umschaltung folgt, wenn die Texte des
Hauptdashboards mitgezogen werden.

Nachgemessen: 7 Testdateien grün (`lbost-shop/tests/run_all.py`), davon eine,
die den Bot-Code wirklich ablaufen lässt (`test_shop_botlauf.py`: Modal vor
`defer()`, Kanalname, Platzhalter, Rechte am Kanal, Transkript, Spam-Serie,
Giveaway-Abschluss, Herzschlag),
`ruff --select=E9,F` sauber, Chromium-Durchgang über 11 Seiten bei
1360 px und 4 Mobilseiten bei 390 px: 0 px Überlauf, 0 JS-Fehler,
0 CSP-Verstöße. **32 Mutationen, 32 gefangen** — jede Sicherung hat
einen Test, der verschwindet, wenn man sie herausnimmt. Drei Prüfungen
waren beim ersten Anlauf vakuum-grün (eine Testbehauptung, die der
Produktionspfad nie liest, eine Zeilenzählung ohne Sortieranker und ein
Filter ohne Beobachtungsgröße) und wurden nachgeschärft.

Zwei Tests mussten mitgehen, weil sich das Produkt geändert hat — nicht
umgekehrt: `test_lbost_shop.py` prüft jetzt den Statusknopf statt des
Sprachmenüs und das volle Admin-Panel statt „noch keine Einstellungen“;
`test_lbost_shop_flow.py` verlangt im Admin-Panel die echten Zahlen
(freigegebenes Konto und gespeicherter Modulverlauf).

Noch offen, weil der Zugriffsschlüssel kein `workflow`-Recht hat: der neue
CI-Job für den Bereich (`.github/workflows/tests.yml`). Er liegt als
`lbost-shop-ci-job.patch` im Arbeitsverzeichnis und braucht zwei Minuten,
sobald der Token im GitHub-Settings auf „Workflows: read and write“ steht —
oder du kopierst den Job von Hand in die Datei.`

---

## Oktober: Ticket-Vorschau rechnet der Bot

Der Reiter für erweiterte Ticket-Einstellungen (Begrüßungstitel, -text,
Bestätigung, Formularfragen) war gleichzeitig von zwei Seiten gebaut
worden. Zusammengeführt auf dem Stand von `main`, weil dessen Modell das
reichhaltigere ist: Fragen mit Typ (kurz, Absatz, Bild), echten
Pflichtfeldern und Kategoriebezug.

Die zwei Stücke, die der Zusammenbau gebracht hat:

* **`POST /tickets/<gild>/panels/<id>/vorschau`** — das Formular zeigte
  vorher den getipften Text samt Platzhaltern. Jetzt holt es
  sich den gerenderten Text vom Bot, entprellt beim Tippen, und zeigt
  dazu die Fragen, die die Kategorie wirklich bekommt. Ohne Premium wird nicht
  nachgerechnet: die Felder sind dann gesperrt, ein Entwurf wäre also
  ohnehin nicht bedienbar.
* **Eine Regel, zwei Nutzer** — `setze_woerter()` und
  `fragen_fuer_kategorie()` liegen in `bot/api/ticket_panels.py`. Der
  Cog ruft sie beim Schreiben ins Ticket, die Vorschau beim Anzeigen.
  Vorher standen die Marker zweimal: einmal im Cog, einmal als
  Anzeige-Behauptung im Formular.

Nachgemessen: `tests/test_ticket_erweitert.py` (neu) gegen die echten
Routen; 21 Mutationen, 21 gefangen, Baum nach jedem Eingriff byteweise
zurückgesetzt. Zwei der Prüfungen waren beim ersten Anlauf zu lasch —
`guildId={guildId}` und `/vorschau` stehen mehrfach in ihren Dateien,
die Pruefung war auf den Block zu verengen, nicht auf die Zeichenkette.

Die Cog-Zahl in README und CODE_ANALYSE war von mir auf 155 geschrieben
worden (ein veralteter Messwert aus dem vorherigen Stand); gemessen sind
157 Cogs / 543 Präfix-Befehle / 65 Schrägstrich-Befehle, `boot_test` mit
`RESULT_FAILED 0`.

---


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
