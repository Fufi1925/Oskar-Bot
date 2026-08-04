"""
Was zuletzt ausgeliefert wurde -- fuer den Tester-Reiter.

Die Eintraege kommen aus den Git-Commits. Eine von Hand gepflegte Liste
waere die naheliegende Alternative und genau deshalb falsch: sie wird
beim dritten Deploy vergessen, und dann steht dort etwas, das nicht
stimmt. Die Commits schreibt ohnehin jemand.

**Warum eine Datei und nicht `git log` zur Laufzeit:** im Docker-Image
gibt es kein ``.git``. Der Dockerfile kopiert nur ``bot/`` und
``dashboard/`` hinein. Deshalb wird die Historie beim Build in
``bot/deploy_history.json`` geschrieben; zur Laufzeit wird diese Datei
gelesen. Liegt sie nicht vor -- etwa lokal -- faellt der Code auf
``git log`` zurueck, damit die Entwicklung nicht anders funktioniert
als der Betrieb.

Aus einer Commit-Zeile wird dabei etwas, das ein Tester lesen kann:
``feat(speedrun): drei neue Vorlagen`` steht als **Neue Funktion** da,
Bereich *Speedrun*. Der Praefix nach Conventional Commits ist genau die
Angabe, die dafuer fehlt -- er muss nur uebersetzt werden.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(BOT_DIR)

# Beim Build erzeugt, siehe tools/freeze_history.py.
HISTORY_FILE = os.path.join(BOT_DIR, "deploy_history.json")

# Wie viele Eintraege der Reiter hoechstens zeigt.
MAX_ENTRIES = 40


# Der Commit-Praefix, uebersetzt.
#
# "feat" heisst fuer einen Tester nichts; "Neue Funktion" schon. Die
# Reihenfolge ist die Wichtigkeit, in der die Eintraege gruppiert
# werden.
_KINDS: dict[str, dict[str, str]] = {
    "feat": {"label": "Neue Funktion", "tone": "new"},
    "fix": {"label": "Fehler behoben", "tone": "fix"},
    "perf": {"label": "Schneller gemacht", "tone": "fix"},
    "refactor": {"label": "Umgebaut", "tone": "chore"},
    "docs": {"label": "Doku", "tone": "chore"},
    "test": {"label": "Tests", "tone": "chore"},
    "chore": {"label": "Aufräumen", "tone": "chore"},
    "style": {"label": "Darstellung", "tone": "chore"},
    "build": {"label": "Build", "tone": "chore"},
    "ci": {"label": "CI", "tone": "chore"},
}

# Der Bereich in Klammern, auf Deutsch. Was hier fehlt, wird
# unveraendert angezeigt -- lieber "anonchat" als gar nichts.
_SCOPES: dict[str, str] = {
    "speedrun": "Speedrun",
    "tickets": "Tickets",
    "ticket": "Tickets",
    "compose": "Eigene Nachricht",
    "templates": "Vorlagen",
    "dashboard": "Dashboard",
    "welcome": "Begrüßung",
    "premium": "Premium",
    "logging": "Logs",
    "logs": "Logs",
    "verify": "Verifizierung",
    "antinuke": "Anti-Nuke",
    "leveling": "Level-System",
    "counting": "Zählspiel",
    "music": "Musik",
    "emoji": "Emojis",
    "team": "Team",
    "api": "Schnittstelle",
}

_HEADER = re.compile(
    r"^(?P<kind>[a-z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r":\s*(?P<summary>.+)$"
)


def _parse_subject(subject: str) -> dict[str, Any]:
    """Aus ``feat(speedrun): drei Vorlagen`` etwas Lesbares machen."""

    match = _HEADER.match(subject.strip())
    if match is None:
        # Kein Conventional-Commit. Nicht verwerfen: ein Eintrag ohne
        # Etikett ist immer noch eine Information.
        return {
            "kind": "",
            "kind_label": "Änderung",
            "tone": "chore",
            "scope": "",
            "summary": subject.strip(),
            "breaking": False,
        }

    kind = match.group("kind").lower()
    meta = _KINDS.get(kind, {"label": kind, "tone": "chore"})
    raw_scope = (match.group("scope") or "").strip().lower()

    summary = match.group("summary").strip()
    # Erster Buchstabe gross -- Commit-Zusammenfassungen sind klein
    # geschrieben, und in einer Liste sieht das nach Fehler aus.
    if summary:
        summary = summary[0].upper() + summary[1:]

    return {
        "kind": kind,
        "kind_label": meta["label"],
        "tone": meta["tone"],
        "scope": _SCOPES.get(raw_scope, raw_scope),
        "summary": summary,
        "breaking": bool(match.group("breaking")),
    }


def _explain(entry: dict[str, Any], body: str) -> str:
    """Der kurze Satz unter dem Titel.

    Bei einer neuen Funktion will ein Tester wissen, *was* er
    ausprobieren soll -- die Commit-Zusammenfassung allein sagt das
    selten. Genommen wird der erste echte Absatz des Commit-Textes,
    gekuerzt; er erklaert in diesem Projekt durchgehend das Warum.
    """

    for block in (body or "").split("\n\n"):
        line = " ".join(block.split()).strip()
        if not line:
            continue
        # Fusszeilen und Aufzaehlungen ueberspringen: die lesen sich
        # ausserhalb des Commits nicht.
        if line.startswith(("Co-authored-by", "Signed-off-by", "*", "-", "#")):
            continue
        if len(line) < 25:
            continue
        # Abschnitts-Ueberschriften ueberspringen.
        #
        # Die Commits hier gliedern sich mit Zeilen in Grossbuchstaben
        # ("INVITE LINKS WERE THE MISSING PIECE"). Als Erklaerung
        # gelesen ist das eine Ueberschrift ohne Inhalt -- der Absatz
        # danach ist der, der etwas sagt.
        letters = [c for c in line if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
            continue
        return line[:320].rstrip() + ("…" if len(line) > 320 else "")
    return ""


def _from_git(limit: int) -> list[dict[str, Any]]:
    """Direkt aus dem Repo lesen -- nur lokal, im Image fehlt ``.git``."""

    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        return []

    sep = "\x1e"
    field = "\x1f"
    try:
        raw = subprocess.run(
            [
                "git", "log", f"-{limit}",
                f"--format=%H{field}%at{field}%s{field}%b{sep}",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []

    if raw.returncode != 0:
        return []

    entries: list[dict[str, Any]] = []
    for chunk in raw.stdout.split(sep):
        if not chunk.strip():
            continue
        parts = chunk.strip("\n").split(field)
        if len(parts) < 3:
            continue
        commit, at, subject = parts[0], parts[1], parts[2]
        body = parts[3] if len(parts) > 3 else ""
        entries.append(_build(commit, at, subject, body))
    return entries


def _build(commit: str, at: str, subject: str, body: str) -> dict[str, Any]:
    entry = _parse_subject(subject)
    entry["commit"] = commit[:7]
    try:
        entry["at"] = int(at)
    except (TypeError, ValueError):
        entry["at"] = 0
    entry["detail"] = _explain(entry, body)
    return entry


def _from_file() -> list[dict[str, Any]]:
    """Die beim Build eingefrorene Historie."""

    try:
        with open(HISTORY_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []

    raw = data.get("commits") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []

    entries = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entries.append(
            _build(
                str(item.get("commit") or ""),
                str(item.get("at") or 0),
                str(item.get("subject") or ""),
                str(item.get("body") or ""),
            )
        )
    return entries


def recent(limit: int = MAX_ENTRIES) -> dict[str, Any]:
    """Die Eintraege fuer den Tester-Reiter.

    Erst die eingefrorene Datei, dann ``git log``. Andersherum waere
    im Betrieb jeder Aufruf ein Prozessstart, der nichts findet.
    """

    limit = max(1, min(int(limit or MAX_ENTRIES), 100))

    entries = _from_file()
    source = "build"
    if not entries:
        entries = _from_git(limit)
        source = "git"

    entries = entries[:limit]

    return {
        "entries": entries,
        "source": source,
        # Der neueste Eintrag ist der Stand, der gerade laeuft.
        "deployed_at": entries[0]["at"] if entries else 0,
        "commit": entries[0]["commit"] if entries else "",
        # Damit der Reiter "3 neue Funktionen" schreiben kann, ohne
        # selbst zu zaehlen.
        "features": sum(1 for e in entries if e["kind"] == "feat"),
        "fixes": sum(1 for e in entries if e["kind"] == "fix"),
    }
