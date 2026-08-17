# ╔══════════════════════════════════════════════════════════════════╗
# ║   Wann der Anti-Nuke ueberhaupt eingreifen darf                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Die Vorpruefung fuer alle siebzehn Anti-Nuke-Module.

Zwei Fragen, die vor jedem Eingriff zu beantworten sind:

  1. **Kann der Bot ueberhaupt?** Steht seine Rolle unter der des
     Angreifers, oder fehlt ihm das Recht zum Bannen, dann scheitert
     jeder Versuch -- und zwar laut.

  2. **Darf er?** Manche Konten sollen nie angefasst werden: der
     Server-Inhaber, der Bot selbst, der Partner-Bot beim Wiederaufbau
     und die vertrauten Bots aus ``TRUSTED_BOTS``.

Warum das nicht in jedem Modul einzeln steht
--------------------------------------------
Weil es siebzehnmal dasselbe waere. Die Module haben ihre Freigaben
schon jetzt kopiert -- jede Aenderung muesste an siebzehn Stellen
gemacht werden, und die achtzehnte wird vergessen. Ein Test zaehlt
deshalb nach, dass jedes Modul diese Datei benutzt.

── Warum bei fehlender Macht gar nichts passiert ────────────────────

Der Nutzer hat es ausdruecklich so gewollt: „wenn bot untern den
angreifer oder gelcihe rolle oder kein recht zu kicken bann tiouten
nie reagiren nie nix machdn".

Das ist auch technisch richtig. Bisher lief der Bot in den Ban, bekam
von Discord ein ``Forbidden`` und meldete dem Team „konnte nicht
eingreifen". Diese Meldung kam bei jedem einzelnen geloeschten Kanal
erneut -- bei einem Angriff mit vierzig Kanaelen also vierzigmal. Wer
die Rolle des Bots zu tief gehaengt hat, wird von seiner eigenen
Fehlkonfiguration zugespamt, waehrend der Angriff laeuft.

Ohne Macht ist Schweigen die ehrlichere Antwort: der Bot kann nichts
tun, also tut er nichts und behauptet auch nicht das Gegenteil.

── Warum Rollengleichstand mitzaehlt ────────────────────────────────

Discord verbietet Eingriffe nicht nur gegen Hoehere, sondern auch
gegen Gleichrangige. ``role_a > role_b`` ist bei gleicher Position
falsch -- genau deshalb wird hier verglichen und nicht bloss auf
``>=`` geprueft.
"""

from __future__ import annotations

from utils import partner_bot

#: Die Umgebungsvariable mit den vertrauten Bots.
TRUSTED_ENV = "TRUSTED_BOTS"


def trusted_bot_ids() -> frozenset[int]:
    """Alle vertrauten Bot-IDs.

    Drei Quellen, und `trusted_bots.all_ids` fuehrt sie zusammen:

      1. **Fest eingebaut** -- Hauptbot, Template-Bot, Statusbot. Nicht
         entfernbar: der Template-Bot baut nach einem Angriff Server
         wieder auf, was aussieht wie ein Nuke.
      2. **`TRUSTED_BOTS`** -- die Umgebungsvariable, komma-getrennt.
      3. **Die Liste im Admin-Dashboard** -- damit ein Bot ohne Deploy
         dazukommen kann.

    Bewusst **ohne** Zwischenspeicher: ein neu eingetragener Bot waere
    sonst erst nach einem Neustart geschuetzt, und genau darum ging es
    bei der Dashboard-Liste. Der Aufruf liest eine kleine SQLite-Datei;
    das passiert nur, wenn ohnehin gerade ein Angriff geprueft wird.
    """
    from utils import trusted_bots

    return trusted_bots.all_ids()


def reset_cache() -> None:
    """Frueher noetig, heute ein Nichtstuer.

    `trusted_bot_ids` hat keinen Zwischenspeicher mehr. Die Funktion
    bleibt, weil Tests sie rufen -- und weil ein Aufruf, der ins Leere
    laeuft, harmloser ist als ein Importfehler.
    """
    return None


def is_trusted_bot(user_or_id) -> bool:
    """Steht dieses Konto in ``TRUSTED_BOTS``?

    Gedacht fuer bekannte Bots wie MEE6 oder Dyno, die auf vielen
    Servern Rollen vergeben und Kanaele anlegen -- also genau das tun,
    was der Anti-Nuke als Angriff liest.

    **Die Liste gilt global.** Sie kann nur der Betreiber setzen, nicht
    ein Server-Inhaber. Das ist Absicht: wer sie pro Server pflegen
    duerfte, koennte den eigenen Zweitbot eintragen und damit den
    Schutz aushebeln.
    """
    if user_or_id is None:
        return False
    kennung = getattr(user_or_id, "id", user_or_id)
    try:
        return int(kennung) in trusted_bot_ids()
    except (TypeError, ValueError):
        return False


def is_exempt(guild, executor, bot_user_id: int | None = None) -> bool:
    """Soll dieses Konto grundsaetzlich in Ruhe gelassen werden?

    Fasst die vier Freigaben zusammen, die bisher in jedem Modul
    einzeln standen: Server-Inhaber, der Bot selbst, der Partner-Bot
    und die vertrauten Bots.

    Nicht enthalten sind die serverabhaengigen Freigaben
    (``extraowners`` und ``whitelisted_users``) -- die brauchen einen
    Datenbankzugriff und bleiben in den Modulen.
    """
    if executor is None:
        return False

    kennung = getattr(executor, "id", executor)

    if guild is not None and kennung == getattr(guild, "owner_id", None):
        return True
    if bot_user_id is not None and kennung == bot_user_id:
        return True
    if partner_bot.is_partner(executor):
        return True
    return is_trusted_bot(executor)


def can_act_on(guild, executor) -> bool:
    """Kann der Bot gegen dieses Konto ueberhaupt vorgehen?

    Prueft drei Dinge, und alle drei muessen stimmen:

      1. **Das Recht.** Ohne ``ban_members`` oder ``kick_members``
         scheitert jeder Versuch.
      2. **Die Rangfolge.** Discord laesst einen Eingriff nur zu, wenn
         die eigene hoechste Rolle **ueber** der des Ziels steht.
         Gleichstand reicht nicht.
      3. **Den Server-Inhaber.** Gegen ihn geht nichts, egal welche
         Rechte der Bot hat.

    Gibt ``False`` zurueck, heisst das: nichts versuchen. Nicht
    „vorsichtig versuchen" -- der Versuch scheitert garantiert und
    erzeugt nur eine Fehlermeldung pro Ereignis.
    """
    if guild is None or executor is None:
        return False

    ich = getattr(guild, "me", None)
    if ich is None:
        return False

    rechte = getattr(ich, "guild_permissions", None)
    if rechte is None:
        return False
    if not (getattr(rechte, "ban_members", False)
            or getattr(rechte, "kick_members", False)):
        return False

    kennung = getattr(executor, "id", executor)
    if kennung == getattr(guild, "owner_id", None):
        return False

    # Ein Mitglied des Servers? Wer nicht mehr da ist, hat keine
    # Rollen -- gegen den laesst sich trotzdem ein Bann aussprechen.
    mitglied = executor
    if not hasattr(mitglied, "top_role"):
        holen = getattr(guild, "get_member", None)
        mitglied = holen(kennung) if callable(holen) else None
        if mitglied is None:
            return True

    meine = getattr(ich, "top_role", None)
    seine = getattr(mitglied, "top_role", None)
    if meine is None or seine is None:
        return False

    # `>` und nicht `>=`: bei gleicher Position verweigert Discord.
    try:
        return meine > seine
    except TypeError:
        return False


def should_skip(guild, executor, bot_user_id: int | None = None) -> bool:
    """Die eine Frage, die jedes Modul stellt.

    ``True`` heisst: aussteigen, ohne etwas zu tun und ohne etwas zu
    melden.

    Fasst beide Gruende zusammen -- „darf nicht" (Freigabe) und „kann
    nicht" (Rangfolge oder fehlendes Recht). Fuer das Modul sind sie
    dasselbe: in beiden Faellen passiert nichts.
    """
    if is_exempt(guild, executor, bot_user_id):
        return True
    return not can_act_on(guild, executor)


# ══════════════════════════════════════════════════════════════════════
#  Einzelne Wachen an- und abschalten
# ══════════════════════════════════════════════════════════════════════

#: Wo die Schalter liegen. Dieselbe Datei wie der Hauptschalter.
_MODULE_DB = "db/anti.db"


async def action_enabled(guild_id: int, action: str) -> bool:
    """Laeuft diese eine Wache auf diesem Server?

    ``action`` ist einer der vierzehn Schluessel aus
    ``api/routes/antinuke.py`` -- ``chdl`` fuer Kanal-Loeschungen,
    ``rldl`` fuer Rollen und so weiter.

    **Fehlt die Zeile, gilt AN.** Das ist der Zustand, den jeder
    Server bisher hatte: es gab nur einen Gesamtschalter, und wer den
    umlegte, wollte alles. Ein Update darf keinem Server
    stillschweigend den Schutz nehmen -- der Fehler faellt erst auf,
    wenn er ausgenutzt wurde.

    Gibt bei jedem Fehler ``True`` zurueck. Eine kaputte oder
    gesperrte Datenbank darf nicht dazu fuehren, dass der Anti-Nuke
    aufhoert zu arbeiten.
    """
    try:
        import aiosqlite

        async with aiosqlite.connect(_MODULE_DB) as db:
            async with db.execute(
                "SELECT enabled FROM antinuke_modules"
                " WHERE guild_id = ? AND action = ?",
                (int(guild_id), str(action)),
            ) as cursor:
                zeile = await cursor.fetchone()
    except Exception:  # noqa: BLE001
        return True

    if zeile is None:
        return True
    return bool(zeile[0])
