# Sicherheit

## Eine Lücke melden

**Bitte nicht als öffentliches Issue.** Ein offenes Issue beschreibt
Fremden genau, wie sie den laufenden Bot angreifen können, bevor die
Lücke geschlossen ist.

Stattdessen:

1. **Direktnachricht** an einen der Entwickler im
   [Support-Server](https://discord.gg/F3TedBAVZT), oder
2. **E-Mail** an die Adresse im Impressum der Website.

Hilfreich in der Meldung: was passiert, wie man es auslöst, und was
dadurch möglich wird. Ein Screenshot reicht oft.

Wir antworten, sobald wir es sehen. Das Projekt wird nebenbei
betrieben — rechne mit ein paar Tagen, nicht mit Minuten.

## Was in diesen Rahmen fällt

* Umgehen der Rechteprüfung im Dashboard (fremde Server sehen oder
  ändern)
* Zugriff auf die API ohne gültige Sitzung
* Ausführen von Befehlen ohne die nötigen Discord-Berechtigungen
* Auslesen von Daten anderer Server
* Alles, womit sich der Bot lahmlegen lässt

## Was nicht

* Fehlende Rate-Limits bei Discord selbst
* Probleme in Discord oder beim Hoster
* „Der Bot antwortet nicht" — das ist ein normaler Fehlerbericht
* Berichte aus automatischen Scannern ohne nachvollziehbaren Weg

## Wie das Projekt aufgebaut ist

Wer wissen will, wie Anmeldung, Rechteprüfung und die Feature-Flags
zusammenspielen: das steht in [SECURITY.md im Wurzelverzeichnis](../SECURITY.md).
Diese Datei hier regelt nur, **wie man eine Lücke meldet**.

## Was wir selbst tun

**Zugangsdaten stehen nie im Code.** Alles Geheime kommt aus
Umgebungsvariablen. `.gitignore` deckt `.env` in allen Varianten ab, und
der Verlauf wurde daraufhin durchsucht.

**Der API-Schlüssel erreicht den Browser nicht.** Anfragen aus dem
Dashboard laufen über einen Proxy (`/api/bot`), der den Schlüssel
serverseitig anhängt. `NEXT_PUBLIC_*` wird in die Seite eingebacken und
ist für jeden Besucher lesbar — deshalb entfernt `start.sh` beim Start
ausdrücklich `NEXT_PUBLIC_DASHBOARD_API_KEY`, falls jemand ihn setzt.

**Jede Anfrage wird gegen Discord geprüft.** Die Middleware verlangt
eine gültige Sitzung, der Proxy prüft zusätzlich pro Server, ob die
Person dort wirklich Rechte hat.

**Tests laufen bei jedem Push.** Siehe `.github/workflows/tests.yml`.

## Wenn doch etwas durchgerutscht ist

Steht ein Zugangsdatum versehentlich im Repo, reicht Löschen **nicht** —
es bleibt im Git-Verlauf. Dann gilt:

1. **Sofort widerrufen und neu erstellen** (Discord-Token, Client
   Secret, API-Schlüssel, GitHub-Token).
2. Erst danach aufräumen. Ein widerrufener Schlüssel im Verlauf ist
   harmlos, ein gültiger nicht.
