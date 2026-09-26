# Code-Analyse

Stand: September 2026, Zweig `main`, Commit `a08cfc6` und die Änderungen
danach. Alle Zahlen sind nachgemessen (Kommandos stehen jeweils dabei),
nicht geschätzt. Eine Zahl ohne Kommando dahinter ist in so einer Datei
diejenige, die als erste falsch wird.

---

## 1. Was das Projekt ist

Ein Discord-Bot mit angeschlossenem Web-Dashboard, zusammen in **einem**
Railway-Container hinter **einem** Port. FastAPI ist der öffentliche
Eingang und leitet alles Unbekannte an die Next.js-Instanz weiter; zwei
zusätzliche Bereiche (`/louckup`, `/lbost-shop`) sind als eigene
FastAPI-Anwendungen darunter gehängt.

```
Railway (1 Port, Standard 8080)
├─ university_bot.py        Bot + FastAPI
│   ├─ /api/v1/*            Schnittstelle fuer das Dashboard
│   ├─ /louckup             eigene App, eigene Sitzung  (pausiert)
│   ├─ /lbost-shop          eigene App, eigener Bot
│   └─ /…                   Proxy → Dashboard
├─ node server.js           Next.js 14 auf 127.0.0.1:3000
├─ phantom/run_bot.py       Ticket-Bot (nur mit Token)
└─ lbost-shop/run_bot.py    Shop-Bot    (nur mit Token)
```

Der Status-Bot ist ein **zweiter Railway-Service** — sonst könnte er den
Hauptbot nicht überwachen, wenn der nicht mehr antwortet.

---

## 2. Größe

| Was | Zahl | Wie gemessen |
|---|---|---|
| Dateien im Repo | 1.549 | `find . -type f -not -path './.git/*' -not -path '*/node_modules/*' \| wc -l` |
| Zeilen Python/TypeScript | ~286.000 | gleiches Muster mit `cat` und `wc -l` |
| Python-Dateien unter `bot/` | 484 | `find bot -name '*.py' \| wc -l` |
| `.tsx` unter `dashboard/` | 239 | `find dashboard -name '*.tsx' -not -path '*/node_modules/*' \| wc -l` |
| Cogs | 157 | `python3 ../.github/scripts/boot_test.py` |
| Prefix-Befehle / Schrägstrich-Befehle | 543 / 65 | ebenda |
| eigenständige Testskripte | 137 | `ls bot/tests/test_*.py \| wc -l` |
| Seiten des Server-Dashboards | 53 | `ls dashboard/app/dashboard/guild/\[guildId\]/ \| wc -l` |
| Reiter im Admin-Bereich | 37 | `grep -cE '^\s+\{ id: "' admin-content.tsx` |
| Datenbanken unter `db/` | über 60 | `grep -rhoE '"db/[a-z_0-9]+\.db"' bot --exclude-dir=tests \| sort -u \| wc -l` |

Die letzte Zeile ist bewusst eine Größenordnung und keine exakte Zahl: Ein
Teil der Treffer sind Namen, die im Code als Teilpfad stehen (`"np.db"`) und
erst zur Laufzeit mit dem Verzeichnis zusammengesetzt werden. Eine Zahl, die
man nicht sauber ermitteln kann, gehört nicht in eine Dokumentation.

---

## 3. Aufbau

| Schicht | Ort | Bemerkung |
|---|---|---|
| Bot-Kern | `bot/core/` | eine `universitybot`-Unterklasse von `discord.Client` |
| Cogs | `bot/cogs/` | 157, geladen über `bot/cogs/__init__.py` |
| HTTP-Schnittstelle | `bot/api/` | FastAPI, Router pro Bereich, `server.py` hängt sie an |
| Speicher | `bot/utils/*.py` | eine Datei pro Bereich, meist eine SQLite-Tabelle |
| Dashboard | `dashboard/app/` | Next.js App Router, `app/api/bot/[...path]/route.ts` als Proxy |
| Panels | `dashboard/components/dashboard/` | ein Baustein pro Reiter |

Die Teilung `utils/*.py` (Speicher) und `api/routes/*.py` (Zugriff) ist
durchgängig: Der Speicher kennt kein HTTP, die Route kennt kein SQL außer
über den Speicher. Dadurch lässt sich jeder Bereich ohne laufenden Bot
prüfen — was die Testskripte ausnutzen.

---

## 4. Wo die Qualität liegt

**Stark:**

* **Rechte an einer Stelle.** Jede Server-Aktion geht durch den Proxy, und
  der prüft Sitzung, Serverzugriff und Methode. Ein `verifyGuildAccess` im
  Layout einer Seite ist zusätzlich, nicht stattdessen.
* **Der Admin-Bereich filtert sichtbar *und* prüft.** Kein
  Rechteeintrag im Frontend heißt: Reiter weg. Eine API, die der Proxy
  nicht kennt, heißt: 404. Beides zusammen verhindert den klassischen
  Fehler „Knopf sichtbar, Klick fehlerhaft".
* **Tests, die hinlangen.** 137 Skripte, davon viele gegen echte Routen
  über eine ASGI-App, nicht gegen Textbausteine. Fast jedes neue Modul des
  Septembers hat einen eigenen Test bekommen (18 Module, 22 Tests).
* **Isolierte Bereiche sind wirklich getrennt.** Eigene Cookies auf eigenem
  Pfad, eigene Datenbanken, eigene App-Instanzen.
* **Ehrliche Texte.** Wo etwas nicht geht, steht warum — etwa bei der
  Bot-Bio im Design-Reiter oder bei den ausgegrauten Kaufknöpfen.

**Schwach:**

* **Ein Teil der neuen Panels ist minifiziert.** Beispiele für die längste
  Zeile pro Datei:
  `dashboard/components/home/world-paths.ts` 167.888 Zeichen (Geometrie,
  ok), `support-rankings-admin.tsx` 4.364, `custom-commands-panel.tsx`
  3.411, `premium-requests-admin.tsx` 3.136 (sechs Zeilen für die ganze
  Komponente), `firewall-panel.tsx` 2.668.
  Funktionsmäßig in Ordnung, aber Diff, Review und Kommentar fehlen. Der
  Rest des Repos erklärt in einer Zeile über einem Block, *warum* er so
  gebaut ist; diese Dateien können das nicht.
* **Zwei Marken-Quellen, bis vor kurzem drei Namen.** Jetzt regelt
  `bot/tests/test_marke.py` das; die Regel steht in `SECURITY.md` nicht,
  sondern in den beiden Quelldateien selbst.
* **Eine Testliste, die nicht läuft.** CI gibt es nur zum manuellen
  Auslösen — bewusst — aber seit der September-Welle sind 38 Testdateien
  rot und niemand hat sie nachgezogen. Details unten.
* **`eval()` in `bot/cogs/commands/autorole.py`** (vier Stellen).
  Nach wie vor der offenste Punkt im Repo, siehe `SECURITY.md` Abschnitt 10.

---

## 5. Prüflauf und sein Zustand

```bash
cd bot
python3 tests/run_all.py
```

Ergebnis bei diesem Stand: **38 von 137 Dateien schlagen fehl.** Zweimal
nachgemessen — in einem sauberen Arbeitszweig von `a08cfc6` ohne die
Änderungen dieser Dokumentation und mit ihnen. Beide Listen sind gleich,
es ist also nichts dazugekommen.

Die Ursache ist meist nicht kaputte Funktion, sondern ein Test, der das
Modell vor der September-Umstellung beschreibt: zwei getrennte
Premium-Produkte, die Bereichezahl der Doku-Seite, ein Pfad, der nur aus
der Repo-Wurzel stimmt. Das ist trotzdem ein Problem — eine Suite, die
dauerhaft rot ist, sagt nichts mehr, und wer sie laufen lässt, gewöhnt
sich an Fehler.

| Datei | Grund |
|---|---|
| `test_docs_seite.py` | die Doku-Seite nennt 45 Bereiche, es sind mehr |
| `test_firewall.py` | liest `bot/api/server.py` aus dem aktuellen Verzeichnis und läuft nur aus der Wurzel |
| `test_dashboard_save_bars.py` | die fünf neuen Reiter fehlen in der Ausnahmeliste |
| `test_premium_seite.py` | prüft Preise und die Zehn-Punkte-Tabelle der alten Seite |
| `test_ideas.py` | erwartet die „Owner-only"-Regel an einer anderen Stelle |
| 33 weitere | dieselbe Ursache: Prüfung gegen den Stand vor der Umstellung |

**Ein Sonderfall, weil er eine Fallgrube zeigt.**
`test_speedrun_templates.py` vergleicht die Schrittliste des Speedruns mit
der echten Vorlagen-Registry des Template-Bots im Nachbarordner
`../University-Template`. Liegt der nicht daneben — in einer isolierten
Auscheckung also und in jedem Prüflauf ohne das zweite Repo — **überspringt
der Test** und meldet Erfolg. Er sagt das auch in der Ausgabe
(`skip (University-Template liegt nicht daneben)`), aber `run_all.py` zählt
ihn danach als grün.

Mit dem Template-Repo daneben meldet er zwei Abweichungen: `rp` baut jetzt
Rollen-Vergabe und `business` Tickets, die fest verdrahtete
Erwartungsliste im Test verneint beides. Der allgemeine Prüfschritt
desselben Tests ist grün — die Schrittliste folgt den neuen Fähigkeiten
also korrekt. Nachzuziehen wäre nur die Beispielliste, und das ist eine
Entscheidung über den Template-Bot, keine Nebenwirkung dieser Doku.

Die Lehre für alle künftigen Fälle dieser Art: Ein Test, der sein
Gegenstück nicht findet, darf überspringen — aber „übersprungen" und
„bestanden" sind in der Summe zwei verschiedene Aussagen, und die Suite
sollte sie auseinanderhalten.

Die Richtung für die Behebung der übrigen 38 ist nicht „Tests löschen",
sondern: erst entscheiden, ob die Prüfung noch etwas wert ist — und sie
dann auf das heutige Modell setzen.

---

## 6. Muster, die sich wiederholen (und die man kennen sollte)

Aus den Korrekturen der letzten Monate, alle schon einmal dagewesen:

1. **Kommentare werden mitgesucht.** Eine Suche nach einem Wort in einer
   Datei trifft auch die Erklärung, warum das Wort nicht da sein darf.
   Erst Kommentare entfernen, dann suchen.
2. **„Wort kommt vor" statt „Wirkung da".** Ein Test, der `premium` in
   einer Datei findet, bleibt grün, wenn die Bedingung auf `true` steht.
   Wirksam wird nur, was die Benutzung erwischt.
3. **Derselbe Text an zwei Stellen.** Ein Ersetzen, das nur ein Vorkommen
   erwischt, lässt den Test grün.
4. **Ersetzungsläufe erwischen den Test selbst.** Beim Bereinigen des
   Markennamens wurde ausgerechnet der Test umgeschrieben, der die alte
   Schreibweise verbieten sollte. Deshalb baut
   `test_marke.py` den gesuchten String aus Teilen zusammen.
5. **`CREATE TABLE IF NOT EXISTS` ändert nichts an einer bestehenden
   Tabelle.** Neue Spalten brauchen `ALTER TABLE`, sonst läuft der Code
   lokal und stirbt auf jeder bestehenden Installation.
6. **JS-Zahlen und Discord-IDs.** IDs sind größer als
   `Number.MAX_SAFE_INTEGER` — sie gehören als Zeichenkette durch die
   ganze Kette.

---

## 7. Wenn man etwas ergänzt

Neuer Reiter im Server-Dashboard, sechs Stellen — eine davon zu vergessen
bedeutet einen roten Test oder einen toten Link:

1. `dashboard/app/dashboard/guild/[guildId]/<neuer-reiter>/page.tsx`
2. Seitenleiste: `dashboard/app/dashboard/layout.tsx`
3. Reiterleiste und Suche: `dashboard/components/guild-tabs.tsx`
4. `bot/tests/test_dashboard_save_bars.py` (Speicherleiste oder Ausnahme)
5. `bot/tests/test_templates.py` (Ausnahme, wenn es keine Einstellung gibt)
6. Zahl der Bereiche auf `dashboard/app/docs/page.tsx`

Neuer Reiter im Admin-Bereich, sieben Stellen in `admin-content.tsx`:
Panel-Import, Icon-Import, `TabId`, `tabs`-Liste, `TAB_GROUPS`,
`TAB_PERMISSION` (fehlender Eintrag = Reiter unsichtbar), Render-Zeile.
