"""
Wo ein Befehl zu Hause ist: Slash, Prefix, Dashboard.

Hintergrund
-----------
Das ``/``-Menue war mit 73 Namen und 129 aufrufbaren Befehlen so voll,
dass die Einrichtungs-Befehle die eigentliche Bedienung zugedeckt
haben. Discord erlaubt 100 globale Befehle -- viel Luft war nicht mehr.

Die Einrichtung ist deshalb aus dem ``/``-Menue verschwunden
(``with_app_command=False``). Sie bleibt vollstaendig als
Prefix-Befehl erhalten; nur der Weg ueber ``/`` faellt weg, weil ein
Formular mit zwoelf Feldern im Dashboard schlicht besser aufgehoben
ist.

Damit ``>help`` das erklaeren kann statt es zu verschweigen, steht hier
an einer Stelle, welcher Befehl zu welcher Dashboard-Seite gehoert.

Warum eine Liste und keine Erkennung zur Laufzeit
-------------------------------------------------
Ob ein Befehl im ``/``-Menue steht, laesst sich am Objekt ablesen
(``command.app_command``). Ob es dafuer eine *Dashboard-Seite* gibt,
nicht -- das weiss nur, wer beide Seiten kennt. Die Zuordnung wird
deshalb hier gepflegt und von ``tests/test_slash_cleanup.py``
gegengeprueft: jeder Eintrag muss einen echten Befehl treffen, und
jeder aus dem Menue genommene Befehl muss einen Eintrag haben.
"""

from __future__ import annotations

# Befehlsname (oberste Ebene) -> Reiter im Dashboard.
#
# Der Reiter ist der Pfad unter /dashboard/guild/<id>/. Ein leerer Wert
# heisst: es gibt eine Seite, aber keinen eigenen Unterpfad.
DASHBOARD_TAB: dict[str, str] = {
    "automod": "automod",
    "log": "logging",
    "greet": "welcome",
    "verification": "verification",
    "setup": "customroles",      # customrole-Gruppe
    "nightmode": "nightmode",
    "filter": "automod",         # Filter sind Teil der Automod-Seite
    "createrr": "reactionroles",
    "dmrr": "reactionroles",
    "whitelist": "antinuke",
    "whitelisted": "antinuke",
    "whitelistreset": "antinuke",
    "unwhitelist": "antinuke",
}

# Aus dem /-Menue genommen, aber ohne eigene Dashboard-Seite.
#
# Sie stehen hier getrennt, damit die Hilfe nicht auf eine Seite
# verlinkt, die es nicht gibt -- ein toter Link ist schlimmer als kein
# Hinweis. Fuer sie heisst es schlicht: geht per Prefix.
NO_DASHBOARD_PAGE: frozenset[str] = frozenset({
    "media",       # Media-Kanaele haben keine eigene Seite
    "extraowner",  # Besitzer-Verwaltung laeuft ueber das Admin-Panel
})

# Alles, was aus dem /-Menue genommen wurde.
SETUP_COMMANDS: frozenset[str] = frozenset(DASHBOARD_TAB) | NO_DASHBOARD_PAGE


def root_name(command) -> str:
    """Der oberste Name eines Befehls -- ``log setup`` wird zu ``log``."""

    return command.qualified_name.split(" ", 1)[0]


def is_setup_command(command) -> bool:
    """Gehoert dieser Befehl zur Einrichtung?"""

    return root_name(command) in SETUP_COMMANDS


def has_slash(command) -> bool:
    """Steht dieser Befehl im ``/``-Menue?

    Geprueft wird das Objekt selbst, nicht eine von Hand gepflegte
    Liste -- die liefe beim naechsten neuen Befehl auseinander.

    Gelesen wird ``with_app_command``. Der naheliegende Weg,
    ``command.app_command is not None``, geht **nicht**: discord.py
    setzt das Feld bei einem abgeschalteten Hybrid-Befehl nicht auf
    ``None``, sondern auf ``MISSING`` -- und ``MISSING is not None``
    ist wahr. Genau daran ist die erste Fassung dieser Funktion
    gescheitert; sie meldete fuer jeden Befehl ``True``.

    Unterbefehle erben die Entscheidung von ihrer Gruppe: ihr eigenes
    Flag bleibt auf ``True``, obwohl die Gruppe nicht angemeldet ist.
    Deshalb entscheidet der oberste Befehl.

    Ein reiner Prefix-Befehl (``commands.command``) hat das Feld gar
    nicht -- dann ist die Antwort ebenfalls nein.
    """

    root = command
    while getattr(root, "parent", None) is not None:
        root = root.parent

    return bool(getattr(root, "with_app_command", False))


def dashboard_hint(command, guild_id: int | str) -> str:
    """Ein Satz fuer die Hilfe, oder "" wenn es nichts zu sagen gibt."""

    if not is_setup_command(command):
        return ""

    name = root_name(command)
    tab = DASHBOARD_TAB.get(name)
    if tab is None:
        return "Nur als Prefix-Befehl — im `/`-Menü nimmt er nur Platz weg."

    try:
        from utils.links import guild_dashboard_url

        url = guild_dashboard_url(guild_id, tab)
    except Exception:  # noqa: BLE001 - die Hilfe darf daran nie scheitern
        url = ""

    if url:
        return f"Einfacher im Dashboard: [{tab}]({url})"
    return f"Einfacher im Dashboard, Reiter „{tab}“."


def surface_badge(command) -> str:
    """Kurzzeichen fuer Listen: wo laesst sich der Befehl aufrufen?"""

    return "`/` + Prefix" if has_slash(command) else "nur Prefix"
